// 에이전트 흐름 전체(V-16 · V-17 · 시연 ①②③⑥)를 모의 서버(createMockApi)에 붙여 돌린다. 화면 부품 없이 상태만 본다.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { ApiClient } from '../../api/contract.ts';
import { createMockApi } from '../../api/mockClient.ts';
import type { DashboardSource, TaskId } from '../../api/types.ts';
import { runStatusChange } from '../tasks/useTaskActions.ts';
import { planCommand, type PlanContext, type PlanResponse } from './agentMock.ts';
import { createAgentSession, type Outcome, type Run, type SessionDeps } from './agentSession.ts';

interface Harness {
  session: ReturnType<typeof createAgentSession>;
  api: ApiClient;
  data: () => DashboardSource;
  selected: string[];
}

async function setup(plan: (text: string, ctx: PlanContext, signal: AbortSignal) => Promise<PlanResponse> = async (t, c) => planCommand(t, c)): Promise<Harness> {
  const api = createMockApi({ latencyMs: 0 });
  let data = await api.getDashboard();
  const refresh = async <T>(p: Promise<T>): Promise<T> => {
    const r = await p;
    data = await api.getDashboard();
    return r;
  };
  const h: Harness = { session: createAgentSession(), api, data: () => data, selected: [] };
  const deps: SessionDeps = {
    requestPlan: plan,
    getData: () => data,
    selectedMailIds: () => h.selected,
    complete: (ids) => refresh(runStatusChange(api, ids, { status: 'done', source: 'agent' })),
    snooze: (ids, until) => refresh(runStatusChange(api, ids, { status: 'snoozed', snoozedUntilMs: until, source: 'agent' })),
    undo: (id) => refresh(api.undoAction(id)),
    now: () => Date.now(),
    paceMs: 0,
  };
  h.session.setDeps(deps);
  return h;
}

/** 조건이 맞을 때까지 비동기 일을 흘려 보낸다 */
async function until(cond: () => boolean, label = '조건'): Promise<void> {
  for (let i = 0; i < 200; i++) {
    if (cond()) return;
    await new Promise((r) => setImmediate(r));
  }
  assert.fail(`${label}이(가) 끝내 맞지 않았다`);
}

function lastRun(h: Harness): Run {
  const runs = h.session.getState().entries.filter((e): e is Run => e.kind === 'run');
  return runs[runs.length - 1]!;
}

function outcome<T extends Outcome['type']>(r: Run, type: T): Extract<Outcome, { type: T }> {
  assert.equal(r.outcome?.type, type, JSON.stringify(r.outcome));
  return r.outcome as Extract<Outcome, { type: T }>;
}

const statusOf = (h: Harness, id: number) => h.data().tasks.find((t) => t.id === (id as TaskId))?.status;

test('V-16 → V-17: 김 팀장 3건 확인 → 완료 → 4단계 완료, 이어서 "방금 거 취소해"는 확인 없이 되돌린다', async () => {
  const h = await setup();
  const { session } = h;
  assert.equal(session.submit('김 팀장님 건 다 처리했어'), true);
  assert.equal(session.submit('또 보내기'), false); // 진행 중에는 받지 않는다
  await until(() => lastRun(h).outcome?.type === 'confirm', '확인 카드');
  let r = lastRun(h);
  assert.deepEqual(r.steps, ['understand', 'target', 'confirm', 'exec']);
  assert.deepEqual(r.status, ['done', 'done', 'wait', 'pending']);
  const card = outcome(r, 'confirm');
  assert.equal(card.question, '김민준 팀장님 업무 3건을 완료로 바꿀까요?');
  assert.equal(session.getState().focus?.target, `agent-confirm-${r.id}`);
  assert.match(session.getState().announcement, /^확인이 필요해요/);
  assert.equal(statusOf(h, 3), 'pending'); // 확인 전에는 아무것도 바꾸지 않는다

  assert.equal(session.confirm(r.id, []), false); // 체크를 다 풀면 실행하지 않는다
  session.confirm(r.id, card.targets.map((t) => t.id));
  await until(() => lastRun(h).phase === 'done', '완료');
  r = lastRun(h);
  assert.deepEqual(r.status, ['done', 'done', 'done', 'done']);
  const result = outcome(r, 'result');
  assert.equal(result.title, '3건을 완료로 바꿨어요');
  assert.ok(result.actionId !== null);
  assert.deepEqual(result.interpretation, ["'김 팀장님'을 김민준 팀장(사업2팀)으로 해석했어요."]);
  assert.deepEqual([3, 9, 12].map((id) => statusOf(h, id)), ['done', 'done', 'done']);
  assert.equal(session.getState().busy, false);
  assert.equal(session.getState().lastAction?.count, 3);

  session.submit('방금 거 취소해');
  await until(() => lastRun(h).phase === 'done', '되돌리기');
  const undoRun = lastRun(h);
  assert.deepEqual(undoRun.steps, ['understand', 'target', 'exec']); // 확인 단계 없음
  assert.equal(outcome(undoRun, 'notice').title, '방금 바꾼 3건을 되돌렸어요');
  assert.deepEqual([3, 9, 12].map((id) => statusOf(h, id)), ['pending', 'pending', 'pending']);
  // 앞 결과 카드의 [실행 취소]는 '되돌렸어요'로 바뀐다
  const first = h.session.getState().entries.find((e): e is Run => e.kind === 'run' && e.id === r.id)!;
  assert.equal(outcome(first, 'result').undo, 'done');
  assert.equal(session.getState().lastAction, null);

  // 한 번 되돌린 뒤 또 "취소해"는 되돌릴 것이 없다(대상 찾기 실패)
  session.submit('방금 거 취소해');
  await until(() => lastRun(h).phase === 'fail', '되돌릴 것 없음');
  assert.deepEqual(lastRun(h).status, ['done', 'fail', 'skip']);
});

test('V-17: 모르는 문장 → 명령 이해 실패 + 지원하지 않는 요청 + 예시 3개, 바뀐 것 없음', async () => {
  const h = await setup();
  h.session.submit('점심 메뉴 추천해줘');
  await until(() => lastRun(h).phase !== 'running', '끝');
  const r = lastRun(h);
  assert.equal(r.phase, 'fail');
  assert.equal(r.source, 'model');
  assert.deepEqual(r.status, ['fail', 'skip', 'skip']);
  const o = outcome(r, 'unsupported');
  assert.equal(o.title, '지원하지 않는 요청이에요');
  assert.equal(o.examples.length, 3);
  assert.equal(h.session.getState().announcement, '지원하지 않는 요청이에요');
});

test('1건 상태 변경(견적 미루기)은 확인 없이 바로 실행, 확인 단계는 건너뜀 · 결과 카드 [실행 취소]', async () => {
  const h = await setup();
  h.session.submit('견적 건 내일 아침으로 미뤄');
  await until(() => lastRun(h).phase === 'done', '완료');
  const r = lastRun(h);
  assert.deepEqual(r.status, ['done', 'done', 'skip', 'done']);
  const o = outcome(r, 'result');
  assert.equal(o.title, '1건을 11/7(토) 08:30까지 미뤘어요');
  assert.equal(statusOf(h, 2), 'snoozed');
  await h.session.undoResult(r.id);
  assert.equal(outcome(lastRun(h), 'result').undo, 'done');
  assert.equal(statusOf(h, 2), 'pending');
  assert.equal(h.session.getState().lastAction, null);
});

test('이거 완료: 고른 메일(3번)의 미처리 2건 → 확인 카드, [취소]하면 바뀐 것 없이 끝', async () => {
  const h = await setup();
  h.selected = ['3'];
  h.session.submit('이거 완료');
  await until(() => lastRun(h).outcome?.type === 'confirm', '확인 카드');
  const r = lastRun(h);
  h.session.cancelConfirm(r.id);
  const done = lastRun(h);
  assert.equal(done.phase, 'cancelled');
  assert.equal(done.outcome, null);
  assert.deepEqual(done.status, ['done', 'done', 'skip', 'skip']);
  assert.equal(h.session.getState().focus?.target, 'input');
  assert.equal(statusOf(h, 3), 'pending');
});

test('[중지]: 명령 이해 중이면 멈추고 바뀐 것 없음. 늦게 온 응답은 무시한다', async () => {
  let release: (p: PlanResponse) => void = () => {};
  const h = await setup((t, c, signal) => new Promise((resolve, reject) => {
    release = () => resolve(planCommand(t, c));
    signal.addEventListener('abort', () => reject(signal.reason), { once: true });
  }));
  h.session.submit('김 팀장님 건 다 처리했어');
  assert.equal(h.session.stop(), true);
  const r = lastRun(h);
  assert.equal(r.phase, 'stopped');
  assert.deepEqual(r.status, ['skip', 'skip', 'skip']);
  assert.equal(h.session.getState().announcement, '중지했어요. 바뀐 것은 없어요');
  release(planCommand('x', { now: '2026-11-06T10:42:00', selected_mail_ids: [], last_result_ids: [] }));
  await new Promise((r2) => setImmediate(r2));
  assert.equal(lastRun(h).phase, 'stopped');
  assert.equal(h.session.getState().busy, false);
});

test('① 오늘 요약 · ⑥ 답장 없는 메일 · 회신 초안: 확인 없이 3단계, 무응답 결과는 다음 명령의 직전 결과로 남는다', async () => {
  const h = await setup();
  h.session.submit('오늘 뭐 해야 돼?');
  await until(() => lastRun(h).phase === 'done');
  assert.match(outcome(lastRun(h), 'summary').title, /^긴급 \d+건이에요$/);

  h.session.submit('답장 안 온 메일 있어?');
  await until(() => lastRun(h).phase === 'done');
  assert.equal(outcome(lastRun(h), 'awaiting').items.length, 2);
  assert.deepEqual(h.session.getState().lastResultIds, ['1001', '1002']);

  h.selected = ['3'];
  h.session.submit('이 메일 회신 초안 써줘');
  await until(() => lastRun(h).phase === 'done');
  const d = outcome(lastRun(h), 'draft');
  assert.equal(d.mailId, 3);
  assert.deepEqual(lastRun(h).status, ['done', 'done', 'done']);
});

test('실행이 실패하면 실행 단계에서 펼친 채 멈추고 lastAction을 남기지 않는다', async () => {
  const h = await setup();
  h.session.setDeps({
    requestPlan: async (t, c) => planCommand(t, c),
    getData: h.data,
    selectedMailIds: () => [],
    complete: async () => {
      throw new Error('서버 오류');
    },
    snooze: async () => {
      throw new Error('서버 오류');
    },
    undo: async () => {
      throw new Error('서버 오류');
    },
    now: () => Date.now(),
    paceMs: 0,
  });
  h.session.submit('견적 건 내일 아침으로 미뤄');
  await until(() => lastRun(h).phase !== 'running');
  const r = lastRun(h);
  assert.equal(r.phase, 'fail');
  assert.deepEqual(r.status, ['done', 'done', 'skip', 'fail']);
  assert.equal(outcome(r, 'error').title, '바꾸지 못했어요');
  assert.equal(h.session.getState().lastAction, null);
});
