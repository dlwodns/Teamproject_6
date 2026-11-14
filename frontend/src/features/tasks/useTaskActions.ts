// 업무 상태 바꾸기 — 모든 화면(대시보드 · 메일 · 완료 시트 · 에이전트)이 이 함수만 부른다(components.md 5.1).
// 서버를 화면마다 따로 부르면 되돌리기 토스트 · 실패 처리 · 다시 불러오기가 화면마다 달라지므로 한곳에 모은다.
//
// 서버 요청 · 화면 먼저 바꾸기 · 실패 시 되돌리기 · 다시 불러오기(FE-13)에 FE-4(이재운)가 토스트를 붙였다.
// - opts.toast가 참(기본)이면 성공 토스트([되돌리기] 8초) · '되돌렸어요' · 실패 토스트([다시 시도])를 여기서 띄운다.
//   부른 화면은 실패 안내를 따로 띄우지 않는다(두 번 뜨지 않게). 문구와 규칙은 lib/toastPolicy.ts.
// - opts.toast가 거짓이면 성공 · 실패 모두 띄우지 않는다. 자기 결과 줄 · [실행 취소]가 있는 화면(에이전트 카드 · 제안 카드 · 기록)이 쓴다.
//
// 판단(어느 요청을 쓸지, 캐시를 어떻게 바꿀지)은 아래 보통 함수로 떼어 node --test로 시험한다(FE-D18).
import { useQueryClient, type QueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';
import { api } from '../../api/client.ts';
import type { ActionResult, ActionSource, ApiClient, BulkPreviewRequest, StatusChange, UndoResult } from '../../api/contract.ts';
import { queryKeys } from '../../api/queries.ts';
import type { DashboardSource, TaskId, TaskStatus } from '../../api/types.ts';
import { changedToast, countTasks, failureToast, UNDONE_TITLE, type TaskChange } from '../../lib/toastPolicy.ts';
import { useToast } from '../../ui/toastApi.ts';

export interface TaskActionOptions {
  /** 누가 불렀는지(BE-4 기록용): 업무 줄 버튼 · 완료 시트 · 에이전트 */
  source?: ActionSource;
  /** 토스트를 띄울지(기본 참). 거짓이면 성공 · 실패 토스트를 모두 띄우지 않는다(자기 결과 줄 · [실행 취소]가 있는 화면) */
  toast?: boolean;
  /** 어느 화면에서 눌렀는지(PL-16 action_log via). 제안 카드는 카드의 via(`suggestion:due_soon`). 서버에 그대로 보낸다 */
  via?: string;
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
  if (change.via !== undefined) request.via = change.via;
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
  const toast = useToast();
  return useMemo(() => createTaskActions({ api, queryClient, toast }), [queryClient, toast]);
}

/** createTaskActions가 쓰는 것. 시험에서는 가짜 api · 토스트와 진짜 QueryClient를 넣는다 */
export interface TaskActionDeps {
  api: Pick<ApiClient, 'patchTaskStatus' | 'bulkPreview' | 'executeAction' | 'undoAction'>;
  queryClient: QueryClient;
  toast: ReturnType<typeof useToast>;
}

/** 훅의 몸통: 화면 먼저 바꾸기 · 실패 시 되돌리기 · 다시 불러오기 · 토스트. React 없이 시험할 수 있게 보통 함수로 둔다 */
export function createTaskActions({ api, queryClient, toast }: TaskActionDeps): TaskActions {
  /** 버튼 하나짜리 토스트. 버튼을 누르면 그 토스트를 닫고(두 번 누르지 않게) 동작한다 */
  function showWithAction(opts: Parameters<typeof toast.show>[0], run: () => void): void {
    const id = toast.show({
      ...opts,
      onAction: () => {
        toast.close(id);
        run();
      },
    });
  }

  function notifyFailure(what: TaskChange | 'undo', error: unknown, retry: () => void): void {
    const copy = failureToast(what, error);
    if (copy.retry) showWithAction({ kind: 'error', title: copy.title, description: copy.description }, retry);
    else toast.show({ kind: 'error', title: copy.title, description: copy.description });
  }

  async function change(taskIds: readonly TaskId[], statusChange: StatusChange, opts: TaskActionOptions | undefined): Promise<ActionResult> {
    // 진행 중인 다시 불러오기가 먼저 바꾼 화면을 옛 값으로 덮지 않게 멈춘다
    await queryClient.cancelQueries({ queryKey: queryKeys.dashboard });
    const before = queryClient.getQueryData<DashboardSource>(queryKeys.dashboard);
    queryClient.setQueryData<DashboardSource>(queryKeys.dashboard, (cur) => cur && withTaskStatuses(cur, taskIds, statusChange.status));
    const what = statusChange.status as TaskChange;
    const withToast = opts?.toast !== false;
    try {
      const result = await runStatusChange(api, taskIds, statusChange);
      if (withToast) {
        const copy = changedToast(what, countTasks(taskIds), result.actionId);
        const actionId = result.actionId;
        if (copy.undoable && actionId !== null) {
          showWithAction({ kind: 'undo', title: copy.title }, () => void undo(actionId, opts).catch(() => {}));
        } else {
          toast.show({ kind: 'info', title: copy.title });
        }
      }
      return result;
    } catch (e) {
      if (before) queryClient.setQueryData<DashboardSource>(queryKeys.dashboard, (cur) => cur && restoreTaskStatuses(cur, before, taskIds));
      if (withToast) notifyFailure(what, e, () => void change(taskIds, statusChange, opts).catch(() => {}));
      throw e; // 부른 화면은 줄을 되돌리는 등 자기 할 일만 하고, 안내는 위 토스트가 맡는다
    } finally {
      // 성공이든 실패든 서버 값으로 다시 맞춘다(집계 숫자 · 완료 시각은 서버 값이 기준). 제안 카드 · 기록도 업무 상태로 정해진다.
      // 시간 초과(15초)로 실패해도 서버는 이미 처리했을 수 있어서, 이 다시 불러오기가 화면을 서버와 맞춘다
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
      void queryClient.invalidateQueries({ queryKey: queryKeys.agent });
    }
  }

  async function undo(actionId: number, opts?: TaskActionOptions): Promise<UndoResult> {
    const withToast = opts?.toast !== false;
    try {
      const result = await api.undoAction(actionId);
      if (withToast) toast.show({ kind: 'info', title: UNDONE_TITLE });
      return result;
    } catch (e) {
      if (withToast) notifyFailure('undo', e, () => void undo(actionId, opts).catch(() => {}));
      throw e;
    } finally {
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
      void queryClient.invalidateQueries({ queryKey: queryKeys.agent }); // 기억 변경 되돌리기도 같은 요청이다
    }
  }

  const actions: TaskActions = {
    complete: (taskIds, opts) => change(taskIds, { status: 'done', ...sourceOf(opts) }, opts),
    snooze: (taskIds, untilMs, opts) => change(taskIds, { status: 'snoozed', snoozedUntilMs: untilMs, ...sourceOf(opts) }, opts),
    exclude: (taskIds, opts) => change(taskIds, { status: 'excluded', ...sourceOf(opts) }, opts),
    undo,
  };
  return actions;
}

function sourceOf(opts: TaskActionOptions | undefined): { source?: ActionSource; via?: string } {
  return {
    ...(opts?.source === undefined ? {} : { source: opts.source }),
    ...(opts?.via === undefined ? {} : { via: opts.via }),
  };
}
