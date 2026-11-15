import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { ActionResult, ApiClient } from '../../api/contract.ts';
import { createMockApi } from '../../api/mockClient.ts';
import type { DashboardSource, MailId, Task, TaskId } from '../../api/types.ts';
import { QueryClient } from '@tanstack/react-query';
import { HttpError, NetworkError } from '../../api/errors.ts';
import { queryKeys } from '../../api/queries.ts';
import { UNDONE_TITLE } from '../../lib/toastPolicy.ts';
import type { ShowToastOptions } from '../../ui/toastApi.ts';
import {
  createTaskActions,
  planStatusCall,
  restoreTaskStatuses,
  runStatusChange,
  withTaskStatuses,
  type TaskActionDeps,
} from './useTaskActions.ts';

const T = (n: number) => n as TaskId;

test('1건은 PATCH, 2건 이상은 미리보기, 겹친 id는 한 번, 빈 목록은 던진다', () => {
  assert.deepEqual(planStatusCall([T(1), T(1)], { status: 'done', source: 'button' }), { kind: 'single', id: 1, change: { status: 'done', source: 'button' } });
  assert.deepEqual(planStatusCall([T(1), T(2)], { status: 'snoozed', snoozedUntilMs: 5 }), {
    kind: 'bulk',
    request: { taskIds: [1, 2], status: 'snoozed', snoozedUntilMs: 5 },
  });
  assert.throws(() => planStatusCall([], { status: 'done' }), RangeError);
});

test('runStatusChange: 여러 건은 미리보기 → 실행을 이어 부른다', async () => {
  const calls: string[] = [];
  const result: ActionResult = { actionId: 9, tasks: [] };
  const fake: Pick<ApiClient, 'patchTaskStatus' | 'bulkPreview' | 'executeAction'> = {
    patchTaskStatus: async (id) => (calls.push(`patch ${id}`), result),
    bulkPreview: async (r) => (calls.push(`preview ${r.taskIds.join(',')}`), { previewId: 'p1', expiresAtMs: 0, status: r.status, snoozedUntilMs: null, targets: [] }),
    executeAction: async (id) => (calls.push(`execute ${id}`), result),
  };
  assert.equal(await runStatusChange(fake, [T(3)], { status: 'done' }), result);
  await runStatusChange(fake, [T(3), T(4)], { status: 'excluded' });
  assert.deepEqual(calls, ['patch 3', 'preview 3,4', 'execute p1']);
});

test('runStatusChange를 모의 서버에: 결과와 되돌리기 id', async () => {
  const api = createMockApi({ latencyMs: 0 });
  const r = await runStatusChange(api, [T(1), T(2)], { status: 'done' });
  assert.equal(r.actionId, 1);
  assert.deepEqual(r.tasks.map((t) => t.status), ['done', 'done']);
});

function source(statuses: Task['status'][]): DashboardSource {
  return {
    origin: { kind: 'mock', dataset: 't', version: 't' },
    asOfMs: 0,
    contacts: [],
    mails: [],
    tasks: statuses.map((status, i) => ({ id: T(i + 1), mailId: 1 as MailId, text: '', dueAtMs: null, status, seenAtMs: null })),
  };
}

test('화면 먼저 바꾸기와 실패 시 그 업무만 되돌리기', () => {
  const before = source(['pending', 'pending', 'snoozed']);
  const optimistic = withTaskStatuses(before, [T(1), T(3)], 'done');
  assert.deepEqual(optimistic.tasks.map((t) => t.status), ['done', 'pending', 'done']);
  assert.equal(optimistic.tasks[1], before.tasks[1]); // 안 바뀐 줄은 같은 객체
  // 그사이 다른 변경(2번 제외)이 들어온 뒤 실패 → 1 · 3번만 원래대로, 2번은 남는다
  const meanwhile = withTaskStatuses(optimistic, [T(2)], 'excluded');
  const rolled = restoreTaskStatuses(meanwhile, before, [T(1), T(3)]);
  assert.deepEqual(rolled.tasks.map((t) => t.status), ['pending', 'excluded', 'snoozed']);
});

// ── 훅 몸통(createTaskActions): 가짜 api · 토스트로 토스트가 언제 · 몇 번 뜨는지 본다(FE-4) ──

function rig(patch: (n: number) => Promise<ActionResult>, undoAction: () => Promise<unknown> = async () => ({ actionId: 1, tasks: [] })) {
  const shown: (ShowToastOptions & { id: string })[] = [];
  const closed: string[] = [];
  const calls = { patch: 0, undo: 0 };
  const queryClient = new QueryClient();
  queryClient.setQueryData(queryKeys.dashboard, source(['pending', 'pending']));
  const deps: TaskActionDeps = {
    api: {
      patchTaskStatus: () => patch(++calls.patch),
      bulkPreview: async () => assert.fail('1건은 미리보기를 부르지 않는다'),
      executeAction: async () => assert.fail('1건은 실행을 부르지 않는다'),
      undoAction: async () => (calls.undo++, undoAction()) as never,
    },
    queryClient,
    toast: {
      show: (o) => {
        const id = `t${shown.length + 1}`;
        shown.push({ ...o, id });
        return id;
      },
      close: (id) => void closed.push(id),
    },
  };
  const statuses = () => queryClient.getQueryData<DashboardSource>(queryKeys.dashboard)!.tasks.map((t) => t.status);
  return { actions: createTaskActions(deps), shown, closed, calls, statuses };
}

const ok = (actionId: number | null): ActionResult => ({ actionId, tasks: [] });
const settle = () => new Promise((r) => setTimeout(r, 0));

test('성공: 되돌리기 토스트 하나, 누르면 그 토스트를 닫고 되돌린 뒤 "되돌렸어요"', async () => {
  const r = rig(async () => ok(7));
  await r.actions.complete([T(1)], { source: 'button' });
  assert.equal(r.shown.length, 1);
  assert.equal(r.shown[0]!.kind, 'undo');
  assert.deepEqual(r.statuses(), ['done', 'pending']);
  r.shown[0]!.onAction!();
  await settle();
  assert.deepEqual(r.closed, ['t1']);
  assert.equal(r.calls.undo, 1);
  assert.deepEqual(r.shown.map((t) => t.title), [r.shown[0]!.title, UNDONE_TITLE]);
});

test('이미 그 상태(actionId null): 정보 토스트만, 되돌리기 버튼 없음', async () => {
  const r = rig(async () => ok(null));
  await r.actions.exclude([T(1)]);
  assert.equal(r.shown.length, 1);
  assert.equal(r.shown[0]!.kind, 'info');
  assert.equal(r.shown[0]!.onAction, undefined);
});

test('toast: false면 성공 · 실패 모두 토스트 없음(에이전트 카드 등 자기 안내가 있는 화면)', async () => {
  const good = rig(async () => ok(3));
  await good.actions.complete([T(1)], { toast: false });
  const bad = rig(async () => {
    throw new NetworkError('끊김');
  });
  await assert.rejects(bad.actions.complete([T(1)], { toast: false }), NetworkError);
  assert.equal(good.shown.length + bad.shown.length, 0);
  assert.deepEqual(bad.statuses(), ['pending', 'pending']); // 실패하면 줄은 원래대로
});

test('연결 실패: 줄을 되돌리고 오류 토스트 하나 + [다시 시도], 누르면 닫고 한 번만 다시 보낸다', async () => {
  const r = rig(async (n) => {
    if (n === 1) throw new NetworkError('끊김');
    return ok(9);
  });
  await assert.rejects(r.actions.complete([T(1)]), NetworkError); // 부른 화면도 실패를 안다
  assert.deepEqual(r.statuses(), ['pending', 'pending']);
  assert.equal(r.shown.length, 1);
  assert.equal(r.shown[0]!.kind, 'error');
  r.shown[0]!.onAction!();
  await settle();
  assert.deepEqual(r.closed, ['t1']);
  assert.equal(r.calls.patch, 2);
  assert.equal(r.shown[1]!.kind, 'undo'); // 다시 보낸 것이 성공하면 되돌리기 토스트
});

test('409 같은 다시 보내도 안 되는 실패: 오류 토스트에 [다시 시도] 없음', async () => {
  const r = rig(async () => {
    throw new HttpError(409, 'conflict');
  });
  await assert.rejects(r.actions.snooze([T(1)], 1000), HttpError);
  assert.equal(r.shown.length, 1);
  assert.equal(r.shown[0]!.onAction, undefined);
});

test('되돌리기 실패: 오류 토스트 + [다시 시도], toast: false면 없음', async () => {
  const r = rig(async () => ok(1), async () => {
    throw new NetworkError('끊김');
  });
  await assert.rejects(r.actions.undo(5), NetworkError);
  await assert.rejects(r.actions.undo(5, { toast: false }), NetworkError);
  assert.equal(r.shown.length, 1);
  assert.equal(r.shown[0]!.kind, 'error');
  assert.equal(typeof r.shown[0]!.onAction, 'function');
});
