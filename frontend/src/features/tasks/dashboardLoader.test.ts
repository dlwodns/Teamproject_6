import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { DashboardApi } from '../../api/client.ts';
import type { DashboardSource, MailId, TaskId } from '../../api/types.ts';
import { createSilentRefresher, startDashboardLoad, type DashboardState } from './dashboardLoader.ts';

const source = (tasks: number): DashboardSource => ({
  origin: { kind: 'mock', dataset: 'test', version: tag(tasks) },
  asOfMs: 0,
  contacts: [],
  mails: [{ id: 1 as MailId, sourceId: 'M-1', direction: 'received', sender: 'a@example.com', subject: '', receivedAtMs: 0, category: '요청' }],
  tasks: Array.from({ length: tasks }, (_, i) => ({ id: (i + 1) as TaskId, mailId: 1 as MailId, text: 't', dueAtMs: null, status: 'pending' as const, seenAtMs: null })),
});
const tag = (n: number) => `tasks-${n}`;
const settle = () => new Promise((r) => setTimeout(r, 0));

/** AbortSignal을 무시하고, 테스트가 정한 순서대로 끝나는 API 대역 */
function manualApi() {
  const pending: Array<{ resolve: (s: DashboardSource) => void; reject: (e: unknown) => void }> = [];
  const api: DashboardApi = {
    getDashboardSource: () => new Promise((resolve, reject) => pending.push({ resolve, reject })),
  };
  return { api, pending };
}

test('요청 A → 요청 B → B 완료 → A 완료: 최종 상태는 B', async () => {
  const { api, pending } = manualApi();
  const states: DashboardState[] = [];
  const cancelA = startDashboardLoad(api, (s) => states.push(s));
  cancelA(); // reload: effect 정리로 A 취소
  startDashboardLoad(api, (s) => states.push(s));
  pending[1]!.resolve(source(2)); // B 완료
  await settle();
  pending[0]!.resolve(source(5)); // A가 늦게 성공
  await settle();
  const last = states.at(-1)!;
  assert.equal(last.kind, 'ready');
  assert.equal(last.kind === 'ready' && last.origin.kind === 'mock' && last.origin.version, tag(2));
  assert.equal(states.filter((s) => s.kind === 'ready').length, 1); // A의 결과는 한 번도 반영되지 않음
});

test('취소된 요청의 늦은 실패도 최신 상태를 덮지 않는다', async () => {
  const { api, pending } = manualApi();
  const states: DashboardState[] = [];
  startDashboardLoad(api, (s) => states.push(s))();
  startDashboardLoad(api, (s) => states.push(s));
  pending[1]!.resolve(source(1));
  await settle();
  pending[0]!.reject(new Error('늦은 실패'));
  await settle();
  assert.equal(states.at(-1)!.kind, 'ready');
});

test('취소되지 않은 요청의 실패 · 집계 오류는 오류 상태', async () => {
  const { api, pending } = manualApi();
  const states: DashboardState[] = [];
  startDashboardLoad(api, (s) => states.push(s));
  const bad = source(2);
  bad.tasks[1] = { ...bad.tasks[1]!, id: 1 as TaskId }; // 업무 id 중복 → 집계에서 ContractError
  pending[0]!.resolve(bad);
  await settle();
  assert.equal(states.at(-1)!.kind, 'error');
});


// ── 조용한 다시 불러오기(FE-4) ──

test('조용한 다시 불러오기: 나중에 시작한 요청만 반영한다', async () => {
  const { api, pending } = manualApi();
  const applied: DashboardSource[] = [];
  const r = createSilentRefresher(api, () => [], (src) => applied.push(src));
  r.refresh(); // A
  r.refresh(); // B
  pending[1]!.resolve(source(2));
  await settle();
  pending[0]!.resolve(source(5)); // A가 늦게 도착
  await settle();
  assert.equal(applied.length, 1);
  assert.equal(applied[0]!.origin.kind === 'mock' && applied[0]!.origin.version, tag(2));
});

test('조용한 다시 불러오기: 아직 응답을 기다리는 체크는 받은 값으로 되살리지 않는다', async () => {
  const { api, pending } = manualApi();
  const applied: DashboardSource[] = [];
  const r = createSilentRefresher(api, () => [{ id: 2 as TaskId, status: 'done' }], (src) => applied.push(src));
  r.refresh();
  pending[0]!.resolve(source(3)); // 서버는 아직 2번을 pending으로 줌
  await settle();
  assert.deepEqual(applied[0]!.tasks.map((t) => t.status), ['pending', 'done', 'pending']);
});

test('조용한 다시 불러오기: 실패하거나 정리(dispose)된 뒤 온 응답은 화면을 바꾸지 않는다', async () => {
  const { api, pending } = manualApi();
  const applied: DashboardSource[] = [];
  const r = createSilentRefresher(api, () => [], (src) => applied.push(src));
  r.refresh();
  pending[0]!.reject(new Error('네트워크'));
  await settle();
  r.refresh();
  r.dispose(); // 다시 불러오기 시작 · 화면 이탈
  pending[1]!.resolve(source(1));
  await settle();
  assert.equal(applied.length, 0);
});
