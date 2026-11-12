import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createHttpActionsApi, createMockActionsApi, selectTaskActionsApi, toActionOutcome } from './actions.ts';
import { ConfigError, ContractError, HttpError, NetworkError } from './errors.ts';
import type { TaskId } from './types.ts';

const id = (n: number) => n as TaskId;

test('응답 변환: action_id · tasks의 id · status만 남긴다', () => {
  const out = toActionOutcome({
    action_id: 7,
    tasks: [{ id: 3, status: 'done', done_at: '2026-10-20T09:00:00+09:00', snoozed_until: null, status_changed_at: null }],
  });
  assert.deepEqual(out, { actionId: 7, tasks: [{ id: 3, status: 'done' }] });
  assert.deepEqual(toActionOutcome({ action_id: null, tasks: [] }), { actionId: null, tasks: [] });
});

test('응답 변환: 형식이 다르면 ContractError', () => {
  for (const bad of [null, {}, { action_id: '7', tasks: [] }, { action_id: 1, tasks: {} }, { action_id: 1, tasks: [{ id: 1, status: 'archived' }] }, { action_id: 1, tasks: [{ id: '1', status: 'done' }] }]) {
    assert.throws(() => toActionOutcome(bad), ContractError);
  }
});

function fakeFetch(respond: (url: string, init: RequestInit) => Response | Promise<Response>) {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  const fn = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return respond(url, init);
  }) as unknown as typeof fetch;
  return { fn, calls };
}

test('HTTP: 완료는 PATCH /tasks/{id}에 status만 보내고, 되돌리기는 POST /actions/{id}/undo', async () => {
  const { fn, calls } = fakeFetch(() => Response.json({ action_id: 9, undone_action_id: 8, tasks: [{ id: 3, status: 'pending' }] }));
  const api = createHttpActionsApi('/api', fn);
  await api.setTaskStatus(id(3), 'done');
  await api.undo(8);
  assert.equal(calls[0]!.url, '/api/tasks/3');
  assert.equal(calls[0]!.init.method, 'PATCH');
  assert.deepEqual(JSON.parse(String(calls[0]!.init.body)), { status: 'done' }); // backend는 정의되지 않은 칸을 422로 막는다(#44)
  assert.equal(calls[1]!.url, '/api/actions/8/undo');
  assert.equal(calls[1]!.init.method, 'POST');
  assert.equal(calls[1]!.init.body, undefined);
});

test('HTTP: 상태 코드 오류는 HttpError, 연결 실패는 NetworkError, JSON이 아니면 ContractError', async () => {
  await assert.rejects(createHttpActionsApi('/api', fakeFetch(() => new Response('', { status: 409 })).fn).undo(1), (e) => e instanceof HttpError && e.status === 409);
  await assert.rejects(
    createHttpActionsApi('/api', fakeFetch(() => Promise.reject(new TypeError('fetch failed'))).fn).setTaskStatus(id(1), 'done'),
    NetworkError,
  );
  await assert.rejects(createHttpActionsApi('/api', fakeFetch(() => new Response('<html>', { status: 200 })).fn).undo(1), ContractError);
});

test('모의: 완료 → 되돌리기 → 원래 상태, 되돌리기는 한 번만', async () => {
  const api = createMockActionsApi();
  api.reset([{ id: id(1), status: 'pending' }, { id: id(2), status: 'snoozed' }]);
  const done = await api.setTaskStatus(id(2), 'done');
  assert.deepEqual(done.tasks, [{ id: 2, status: 'done' }]);
  assert.notEqual(done.actionId, null);
  const back = await api.undo(done.actionId!);
  assert.deepEqual(back.tasks, [{ id: 2, status: 'snoozed' }]); // 나중에였던 업무는 나중에로 돌아간다
  await assert.rejects(api.undo(done.actionId!), (e) => e instanceof HttpError && e.status === 409);
});

test('모의: 이미 그 상태면 기록 없음(actionId null), 없는 업무는 404', async () => {
  const api = createMockActionsApi();
  api.reset([{ id: id(1), status: 'done' }]);
  assert.equal((await api.setTaskStatus(id(1), 'done')).actionId, null);
  await assert.rejects(api.setTaskStatus(id(99), 'done'), (e) => e instanceof HttpError && e.status === 404);
});

test('모의: 다시 불러오면(reset) 바꾼 상태와 기록을 버린다', async () => {
  const api = createMockActionsApi();
  api.reset([{ id: id(1), status: 'pending' }]);
  const done = await api.setTaskStatus(id(1), 'done');
  api.reset([{ id: id(1), status: 'pending' }]);
  assert.notEqual((await api.setTaskStatus(id(1), 'done')).actionId, null); // 다시 완료할 수 있다
  await assert.rejects(api.undo(done.actionId!), (e) => e instanceof HttpError && e.status === 404);
});

test('설정 오류면 모든 호출이 그 오류로 실패한다(모의로 몰래 바꾸지 않음)', async () => {
  const api = selectTaskActionsApi({ VITE_API_MODE: 'real' });
  await assert.rejects(api.setTaskStatus(id(1), 'done'), ConfigError);
  await assert.rejects(api.undo(1), ConfigError);
  assert.ok('reset' in selectTaskActionsApi({}));
  assert.ok(!('reset' in selectTaskActionsApi({ VITE_API_MODE: 'http' })));
});
