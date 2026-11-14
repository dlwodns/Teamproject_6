import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { ActionResult, ApiClient } from '../../api/contract.ts';
import { createMockApi } from '../../api/mockClient.ts';
import type { DashboardSource, MailId, Task, TaskId } from '../../api/types.ts';
import { planStatusCall, restoreTaskStatuses, runStatusChange, withTaskStatuses } from './useTaskActions.ts';

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
