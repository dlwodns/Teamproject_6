// 업무 상태 바꾸기 — 모든 화면(대시보드 · 메일 · 완료 시트 · 에이전트)이 이 함수만 부른다(components.md 5.1).
// 서버를 화면마다 따로 부르면 되돌리기 토스트 · 실패 처리 · 다시 불러오기가 화면마다 달라지므로 한곳에 모은다.
//
// [담당 나눔] 지금은 FE-13 기반의 '토스트 없는 기본 구현'이다: 서버 요청 · 화면 먼저 바꾸기 · 실패 시 되돌리기 · 다시 불러오기만 한다.
// 완료 · 되돌리기 토스트('완료로 바꿨어요 [되돌리기]' 8초), '되돌렸어요', 실패 문구('바꾸지 못함 [다시 시도]')는
// FE-4(담당 이재운)가 이 파일의 같은 함수 안에 붙인다. 그래서 opts.toast는 지금 받기만 하고 쓰지 않는다.
// 화면 쪽은 지금부터 complete(ids, { source, toast })처럼 최종 모양으로 부르면 FE-4 뒤에 고칠 것이 없다.
//
// 판단(어느 요청을 쓸지, 캐시를 어떻게 바꿀지)은 아래 보통 함수로 떼어 node --test로 시험한다(FE-D17).
import { useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';
import { api } from '../../api/client.ts';
import type { ActionResult, ActionSource, ApiClient, BulkPreviewRequest, StatusChange, UndoResult } from '../../api/contract.ts';
import { queryKeys } from '../../api/queries.ts';
import type { DashboardSource, TaskId, TaskStatus } from '../../api/types.ts';

export interface TaskActionOptions {
  /** 누가 불렀는지(BE-4 기록용): 업무 줄 버튼 · 완료 시트 · 에이전트 */
  source?: ActionSource;
  /** 되돌리기 토스트를 띄울지(기본 참). 자기 [실행 취소]가 있는 에이전트 결과 카드는 false. FE-4 전까지는 쓰지 않는다 */
  toast?: boolean;
}

export interface TaskActions {
  complete(taskIds: readonly TaskId[], opts?: TaskActionOptions): Promise<ActionResult>;
  snooze(taskIds: readonly TaskId[], untilMs: number, opts?: TaskActionOptions): Promise<ActionResult>;
  exclude(taskIds: readonly TaskId[], opts?: TaskActionOptions): Promise<ActionResult>;
  undo(actionId: number, opts?: TaskActionOptions): Promise<UndoResult>;
}

// ── 판단(시험 대상) ──

export type StatusCallPlan =
  | { kind: 'single'; id: TaskId; change: StatusChange }
  | { kind: 'bulk'; request: BulkPreviewRequest };

/**
 * 1건은 바로 바꾸고(PATCH), 2건 이상은 미리보기 → 실행으로 보낸다(BE-4 · D37). 같은 id가 겹치면 한 번으로 센다.
 * 빈 목록은 화면 버그라 조용히 넘기지 않고 던진다.
 */
export function planStatusCall(taskIds: readonly TaskId[], change: StatusChange): StatusCallPlan {
  const ids = [...new Set(taskIds)];
  if (ids.length === 0) throw new RangeError('바꿀 업무가 없다');
  if (ids.length === 1) return { kind: 'single', id: ids[0]!, change };
  const request: BulkPreviewRequest = { taskIds: ids, status: change.status };
  if (change.snoozedUntilMs !== undefined) request.snoozedUntilMs = change.snoozedUntilMs;
  return { kind: 'bulk', request };
}

/**
 * 계획대로 서버를 부른다. 여러 건은 미리보기를 받자마자 실행한다: 이 함수를 부르는 시점이 이미 사용자가 확인한 뒤다
 * (확인창 · 에이전트 확인 카드가 미리보기 대상을 직접 보여 줘야 하면 api.bulkPreview를 따로 부르고 executeAction만 넘긴다).
 */
export async function runStatusChange(
  client: Pick<ApiClient, 'patchTaskStatus' | 'bulkPreview' | 'executeAction'>,
  taskIds: readonly TaskId[],
  change: StatusChange,
): Promise<ActionResult> {
  const plan = planStatusCall(taskIds, change);
  if (plan.kind === 'single') return client.patchTaskStatus(plan.id, plan.change);
  const preview = await client.bulkPreview(plan.request);
  return client.executeAction(preview.previewId);
}

/** 화면 먼저 바꾸기: 캐시의 해당 업무 상태만 바꾼 새 원자료(나머지 객체는 그대로 재사용) */
export function withTaskStatuses(source: DashboardSource, taskIds: readonly TaskId[], status: TaskStatus): DashboardSource {
  const ids = new Set(taskIds);
  return { ...source, tasks: source.tasks.map((t) => (ids.has(t.id) && t.status !== status ? { ...t, status } : t)) };
}

/**
 * 실패하면 그 업무들만 바꾸기 전 상태로 돌린다. 캐시 전체를 옛 값으로 덮으면 그사이 끝난 다른 변경까지 지워지므로
 * 이번에 건드린 업무만 되돌린다.
 */
export function restoreTaskStatuses(current: DashboardSource, before: DashboardSource, taskIds: readonly TaskId[]): DashboardSource {
  const ids = new Set(taskIds);
  const was = new Map(before.tasks.filter((t) => ids.has(t.id)).map((t) => [t.id, t.status]));
  return {
    ...current,
    tasks: current.tasks.map((t) => {
      const status = was.get(t.id);
      return status !== undefined && status !== t.status ? { ...t, status } : t;
    }),
  };
}

// ── 훅 ──

export function useTaskActions(): TaskActions {
  const queryClient = useQueryClient();

  return useMemo(() => {
    async function change(taskIds: readonly TaskId[], statusChange: StatusChange): Promise<ActionResult> {
      // 진행 중인 다시 불러오기가 먼저 바꾼 화면을 옛 값으로 덮지 않게 멈춘다
      await queryClient.cancelQueries({ queryKey: queryKeys.dashboard });
      const before = queryClient.getQueryData<DashboardSource>(queryKeys.dashboard);
      queryClient.setQueryData<DashboardSource>(queryKeys.dashboard, (cur) => cur && withTaskStatuses(cur, taskIds, statusChange.status));
      try {
        return await runStatusChange(api, taskIds, statusChange);
      } catch (e) {
        if (before) queryClient.setQueryData<DashboardSource>(queryKeys.dashboard, (cur) => cur && restoreTaskStatuses(cur, before, taskIds));
        throw e; // 실패 문구는 FE-4가 여기서 띄운다. 지금은 부른 화면이 받는다
      } finally {
        // 성공이든 실패든 서버 값으로 다시 맞춘다(집계 숫자 · 완료 시각은 서버 값이 기준)
        void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
      }
    }

    const actions: TaskActions = {
      complete: (taskIds, opts) => change(taskIds, { status: 'done', ...sourceOf(opts) }),
      snooze: (taskIds, untilMs, opts) => change(taskIds, { status: 'snoozed', snoozedUntilMs: untilMs, ...sourceOf(opts) }),
      exclude: (taskIds, opts) => change(taskIds, { status: 'excluded', ...sourceOf(opts) }),
      async undo(actionId) {
        try {
          return await api.undoAction(actionId);
        } finally {
          void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
        }
      },
    };
    return actions;
  }, [queryClient]);
}

function sourceOf(opts: TaskActionOptions | undefined): { source?: ActionSource } {
  return opts?.source === undefined ? {} : { source: opts.source };
}
