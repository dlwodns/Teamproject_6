// 에이전트 흐름 전체(V-16 · V-17 · 시연 ①②③⑥)를 모의 서버(createMockApi)의 runAgentCommand에 붙여 돌린다. 화면 부품 없이 상태만 본다.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { AgentCommandRequest, AgentResult, ApiClient } from '../../api/contract.ts';
import { AGENT_UNAVAILABLE_TEXT, AgentUnavailableError, HttpError } from '../../api/errors.ts';
import { createMockApi } from '../../api/mockClient.ts';
import type { DashboardSource, MailId, TaskId } from '../../api/types.ts';
import { STOPPED_UNSURE_TEXT } from './agentSteps.ts';
import { createAgentSession, localDeadline, PREVIEW_TTL_MS, type Outcome, type Run, type SessionDeps } from './agentSession.ts';
import { EXPIRED_TEXT } from './agentText.ts';

interface Harness {
  session: ReturnType<typeof createAgentSession>;
  api: ApiClient;
  data: () => Promise<DashboardSource>;
  selected: MailId[];
  requests: AgentCommandRequest[];
  refreshes: number;
  clock: { offsetMs: number };
}

async function setup(over: Partial<SessionDeps> = {}): Promise<Harness> {
  const api = createMockApi({ latencyMs: 0, agentDelayMs: { rule: 0, model: 0 } });
  const h: Harness = {
    session: createAgentSession(),
    api,
    data: () => api.getDashboard(),
    selected: [],
    requests: [],
    refreshes: 0,
    clock: { offsetMs: 0 },
  };
  h.session.setDeps({
    runCommand: (req, signal) => {
      h.requests.push(req);
      return api.runAgentCommand(req, signal);
    },
    execute: (previewId, taskIds) => api.executeAction(previewId, taskIds),
    undo: (id) => api.undoAction(id),
    refresh: () => {
      h.refreshes++;
    },
    selectedMailIds: () => h.selected,
    now: () => Date.now() + h.clock.offsetMs,
    ...over,
  });
  return h;
}

/** 조건이 맞을 때까지 비동기 일을 흘려 보낸다 */
async function until(cond: () => boolean, label = '조건'): Promise<void> {
  for (let i = 0; i < 300; i++) {
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

async function statuses(h: Harness, ids: number[]): Promise<string[]> {
  const d = await h.data();
  return ids.map((id) => d.tasks.find((t) => t.id === (id as TaskId))!.status);
}

test('V-16 → V-17: 김 팀장 3건 확인 → 실행 → 4단계 완료, "방금 거 취소해"는 서버가 바로 되돌리고, 한 번 더 말하면 되묻는다', async () => {
  const h = await setup();
  const { session } = h;
  assert.equal(session.submit('김 팀장님 건 다 처리했어'), true);
  await until(() => lastRun(h).outcome?.type === 'confirm', '확인 카드');
  let r = lastRun(h);
  assert.deepEqual(r.steps, ['understand', 'target', 'confirm', 'exec']);
  assert.deepEqual(r.status, ['done', 'done', 'wait', 'pending']);
  assert.equal(r.notes.understand, 'T03 일괄_완료 · 규칙');
  assert.equal(r.notes.target, '대상 3건');
  const card = outcome(r, 'confirm');
  assert.equal(card.title, '업무 3건을 완료로 변경하시겠습니까?');
  assert.equal(session.getState().focus?.target, `agent-confirm-${r.id}`);
  assert.match(session.getState().announcement, /^확인이 필요합니다/);
  assert.deepEqual(await statuses(h, [3, 9, 12]), ['pending', 'pending', 'pending']); // 확인 전에는 아무것도 바꾸지 않는다

  assert.equal(session.confirm(r.id, []), false); // 체크를 다 풀면 실행하지 않는다
  session.confirm(r.id, card.targets.map((t) => t.id));
  await until(() => lastRun(h).phase === 'done', '완료');
  r = lastRun(h);
  assert.deepEqual(r.status, ['done', 'done', 'done', 'done']);
  const result = outcome(r, 'result');
  assert.equal(result.title, '3건을 완료 처리했습니다');
  assert.ok(result.actionId !== null);
  assert.ok(result.targets.every((t) => t.status === 'done'));
  assert.deepEqual(await statuses(h, [3, 9, 12]), ['done', 'done', 'done']);
  assert.ok(h.refreshes >= 1); // ['dashboard']를 다시 불러온다
  assert.deepEqual([...session.getState().lastResultIds].sort(), [3, 9]); // 직전 결과는 메일 id
  assert.equal(session.getState().busy, false);

  session.submit('방금 거 취소해');
  await until(() => lastRun(h).phase === 'done', '되돌리기');
  const undoRun = lastRun(h);
  assert.deepEqual(h.requests[1]?.lastResultIds?.slice().sort(), [3, 9]);
  assert.deepEqual(undoRun.steps, ['understand', 'target', 'exec']); // 확인 단계 없음
  assert.equal(outcome(undoRun, 'result').title, '3건의 처리를 취소했습니다');
  assert.deepEqual(await statuses(h, [3, 9, 12]), ['pending', 'pending', 'pending']);
  // 앞 결과 카드의 [실행 취소]는 '취소했습니다'로 바뀐다
  const first = session.getState().entries.find((e): e is Run => e.kind === 'run' && e.id === r.id)!;
  assert.equal(outcome(first, 'result').undo, 'done');

  // 방금 한 것이 되돌리기면 그 전 것을 조용히 되돌리지 않고 되묻는다(executor.py _undo)
  session.submit('방금 거 취소해');
  await until(() => lastRun(h).phase === 'fail', '되묻기');
  assert.equal(outcome(lastRun(h), 'unsupported').title, '방금 취소한 작업을 다시 적용할지, 그 이전 작업도 취소할지 알려 주십시오');
  assert.deepEqual(lastRun(h).status, ['fail', 'skip', 'skip']);
});

test('확인 카드에서 1건 체크를 풀고 실행하면 남긴 것만 바뀌고, 결과 카드 제목 · 대상도 그 수로', async () => {
  const h = await setup();
  h.session.submit('김 팀장님 건 다 처리했어');
  await until(() => lastRun(h).outcome?.type === 'confirm');
  const r = lastRun(h);
  const card = outcome(r, 'confirm');
  const keep = card.targets.filter((t) => t.id !== 12).map((t) => t.id);
  assert.equal(h.session.confirm(r.id, keep), true);
  await until(() => lastRun(h).phase === 'done');
  const o = outcome(lastRun(h), 'result');
  assert.equal(o.title, '2건을 완료 처리했습니다');
  assert.deepEqual(o.targets.map((t) => t.id).sort(), [3, 9]);
  assert.deepEqual(await statuses(h, [3, 9, 12]), ['done', 'done', 'pending']);
});

test('이거 완료: 고른 메일 1건 → 확인 없이 바로(D37), 확인 단계는 건너뜀 · 결과 카드 [실행 취소]', async () => {
  const h = await setup();
  h.selected = [1 as MailId];
  h.session.submit('이거 완료');
  await until(() => lastRun(h).phase === 'done');
  assert.deepEqual(h.requests[0]?.selectedMailIds, [1]);
  const r = lastRun(h);
  assert.deepEqual(r.status, ['done', 'done', 'skip', 'done']);
  const o = outcome(r, 'result');
  assert.equal(o.title, '1건을 완료로 변경했습니다');
  assert.deepEqual(o.notes, ['선택한 메일 1통']);
  assert.deepEqual(await statuses(h, [1]), ['done']);
  await h.session.undoResult(r.id);
  assert.equal(outcome(lastRun(h), 'result').undo, 'done');
  assert.deepEqual(await statuses(h, [1]), ['pending']);
});

test('견적 건 내일 아침으로 미뤄: 2건 확인(나중에 포함) → 1건만 남겨 실행 → "1건을 11/07 08:30까지 미뤘어요"', async () => {
  const h = await setup();
  h.session.submit('견적 건 내일 아침으로 미뤄');
  await until(() => lastRun(h).outcome?.type === 'confirm');
  const r = lastRun(h);
  assert.equal(outcome(r, 'confirm').title, '업무 2건을 11/07 08:30까지 연기하시겠습니까?');
  h.session.confirm(r.id, [2 as TaskId]);
  await until(() => lastRun(h).phase === 'done');
  assert.equal(outcome(lastRun(h), 'result').title, '1건을 11/07 08:30까지 연기했습니다');
  assert.deepEqual(await statuses(h, [2]), ['snoozed']);
});

test('[취소]하면 바뀐 것 없이 끝, 입력칸으로 포커스', async () => {
  const h = await setup();
  h.selected = [3 as MailId];
  h.session.submit('이거 완료');
  await until(() => lastRun(h).outcome?.type === 'confirm');
  h.session.cancelConfirm(lastRun(h).id);
  const done = lastRun(h);
  assert.equal(done.phase, 'cancelled');
  assert.deepEqual(done.status, ['done', 'done', 'skip', 'skip']);
  assert.equal(h.session.getState().focus?.target, 'input');
  assert.deepEqual(await statuses(h, [3, 12]), ['pending', 'pending']);
});

test('확인 시간이 지나면 실행하지 않고 "확인 시간이 경과했습니다", 실행이 409여도 같은 안내', async () => {
  const h = await setup();
  h.session.submit('김 팀장님 건 다 처리했어');
  await until(() => lastRun(h).outcome?.type === 'confirm');
  h.clock.offsetMs = 10 * 60_000; // 미리보기 5분이 지났다
  const r = lastRun(h);
  assert.equal(h.session.confirm(r.id, outcome(r, 'confirm').targets.map((t) => t.id)), false);
  assert.equal(lastRun(h).phase, 'fail');
  assert.equal(outcome(lastRun(h), 'notice').title, EXPIRED_TEXT);
  assert.deepEqual(await statuses(h, [3, 9, 12]), ['pending', 'pending', 'pending']);

  const h2 = await setup({ execute: async () => Promise.reject(new HttpError(409, '만료된 미리보기입니다')) });
  h2.session.submit('김 팀장님 건 다 처리했어');
  await until(() => lastRun(h2).outcome?.type === 'confirm');
  h2.session.confirm(lastRun(h2).id, [3 as TaskId]);
  await until(() => lastRun(h2).phase === 'fail');
  assert.equal(outcome(lastRun(h2), 'notice').title, EXPIRED_TEXT);
});

test('V-17: 점심 메뉴 추천해줘 → 명령 이해 실패(엑사원) + 지원하지 않는 요청 + 예시 3개', async () => {
  const h = await setup();
  h.session.submit('점심 메뉴 추천해줘');
  await until(() => lastRun(h).phase !== 'running');
  const r = lastRun(h);
  assert.equal(r.phase, 'fail');
  assert.equal(r.source, 'agent_model');
  assert.equal(r.notes.understand, '엑사원');
  assert.deepEqual(r.status, ['fail', 'skip', 'skip']);
  const o = outcome(r, 'unsupported');
  assert.equal(o.title, '지원하지 않는 요청입니다');
  assert.equal(o.examples.length, 3);
  assert.equal(h.session.getState().announcement, '지원하지 않는 요청입니다');
});

test('실제 서버의 T01(준비 중) unsupported는 그대로 보이고 "서버에 이 기능이 아직 없어요"로 안내한다', async () => {
  const notReady: AgentResult = {
    kind: 'unsupported',
    action: 'T01',
    actionName: '오늘_요약',
    source: 'agent_rule',
    title: "'오늘_요약'은(는) 아직 준비 중입니다",
    targets: [],
    notes: [],
    actionId: null,
    previewId: null,
    expiresAtMs: null,
  };
  const h = await setup({ runCommand: async () => notReady });
  h.session.submit('오늘 뭐 해야 돼?');
  await until(() => lastRun(h).phase !== 'running');
  const o = outcome(lastRun(h), 'unsupported');
  assert.equal(o.title, "'오늘_요약'은(는) 아직 준비 중입니다");
  assert.match(o.hint, /^서버에 아직 없는 기능입니다/);
});

test('① 오늘 요약 · ⑥ 답장 없는 메일 · 회신 초안(FE 제안, 모의): 확인 없이 3단계, 무응답 결과는 다음 명령의 직전 결과', async () => {
  const h = await setup();
  h.session.submit('오늘 뭐 해야 돼?');
  await until(() => lastRun(h).phase === 'done');
  const s = outcome(lastRun(h), 'summary');
  assert.match(s.title, /^긴급 업무가 \d+건 있습니다$/);
  assert.ok(s.summary.items.length > 0);

  h.session.submit('답장 안 온 메일 있어?');
  await until(() => lastRun(h).phase === 'done');
  assert.equal(outcome(lastRun(h), 'awaiting').items.length, 2);
  assert.deepEqual(h.session.getState().lastResultIds, [1001, 1002]);

  h.selected = [3 as MailId];
  h.session.submit('이 메일 회신 초안 써줘');
  await until(() => lastRun(h).phase === 'done');
  assert.equal(outcome(lastRun(h), 'draft').draft.mailId, 3);
  assert.deepEqual(lastRun(h).status, ['done', 'done', 'done']);
});

test('[중지]: 요청 중이면 멈추되 "바뀐 것은 없어요"를 약속하지 않는다. 확인 대기 중 중지는 바뀐 것 없음', async () => {
  let release: () => void = () => {};
  const h = await setup({
    runCommand: (req, signal) =>
      new Promise<AgentResult>((resolve, reject) => {
        release = () => void createMockApi({ latencyMs: 0, agentDelayMs: { rule: 0, model: 0 } }).runAgentCommand(req).then(resolve);
        signal.addEventListener('abort', () => reject(signal.reason), { once: true });
      }),
  });
  h.session.submit('김 팀장님 건 다 처리했어');
  assert.equal(h.session.stop(), true);
  let r = lastRun(h);
  assert.equal(r.phase, 'stopped');
  assert.equal(r.unsure, true);
  assert.deepEqual(r.status, ['skip', 'skip', 'skip']);
  assert.equal(h.session.getState().announcement, STOPPED_UNSURE_TEXT);
  release();
  await new Promise((r2) => setTimeout(r2, 5));
  assert.equal(lastRun(h).phase, 'stopped'); // 늦게 온 응답은 무시한다
  assert.equal(h.session.getState().busy, false);

  const h2 = await setup();
  h2.session.submit('김 팀장님 건 다 처리했어');
  await until(() => lastRun(h2).outcome?.type === 'confirm');
  assert.equal(h2.session.stop(), true);
  r = lastRun(h2);
  assert.equal(r.unsure, false);
  assert.equal(h2.session.getState().announcement, '취소했습니다. 변경된 내용은 없습니다');
});

test('503(AI를 쓸 수 없음)은 고정 문구 + 바뀐 것 없음, 실행 연결 실패는 처리 여부를 약속하지 않는다', async () => {
  const h = await setup({ runCommand: async () => Promise.reject(new AgentUnavailableError()) });
  h.session.submit('오늘 뭐 해야 돼?');
  await until(() => lastRun(h).phase !== 'running');
  const o = outcome(lastRun(h), 'error');
  assert.equal(o.title, AGENT_UNAVAILABLE_TEXT);
  assert.equal(o.hint, '변경된 내용은 없습니다.');
  assert.deepEqual(lastRun(h).status, ['fail', 'skip', 'skip']);

  const h2 = await setup({ execute: async () => Promise.reject(new TypeError('Failed to fetch')) });
  h2.session.submit('김 팀장님 건 다 처리했어');
  await until(() => lastRun(h2).outcome?.type === 'confirm');
  h2.session.confirm(lastRun(h2).id, [3 as TaskId]);
  await until(() => lastRun(h2).phase === 'fail');
  assert.deepEqual(lastRun(h2).status, ['done', 'done', 'done', 'fail']);
  assert.equal(outcome(lastRun(h2), 'error').hint, '처리 여부를 업무 목록에서 확인해 주십시오.');
});

test('확인 마감은 브라우저 시계로 잰다 — 서버가 시연 시각으로 과거 · 미래에 있어도 받은 때부터 5분 (#62 리뷰)', () => {
  const now = Date.UTC(2026, 10, 14, 6, 0);
  assert.equal(localDeadline(null, now), null);
  assert.equal(localDeadline(now + 60_000, now), now + 60_000); // 같은 시계: 서버 값 그대로
  assert.equal(localDeadline(Date.UTC(2026, 9, 19, 9, 5), now), now + PREVIEW_TTL_MS); // 서버가 과거(시연 시각)
  assert.equal(localDeadline(now + 3 * 86_400_000, now), now + PREVIEW_TTL_MS); // 서버가 미래
});

test('11-19 되묻기에 후보 업무가 오면(T16 여러 건) 고를 목록으로 싣고, 고른 업무로 같은 말을 다시 보낸다', async () => {
  const t = (id: number) => ({ id: id as TaskId, mailId: (100 + id) as MailId, text: `업무 ${id}`, status: 'pending' as const, snoozedUntilMs: null });
  const ask: AgentResult = {
    kind: 'ask', action: 'T16', actionName: '기한_변경', source: 'agent_rule', title: '업무 2건이 해당합니다. 하나를 골라 주십시오',
    targets: [t(1), t(2)], notes: [], actionId: null, previewId: null, expiresAtMs: null,
  };
  const reqs: AgentCommandRequest[] = [];
  const h = await setup({ runCommand: async (req) => (reqs.push(req), ask) });
  h.session.submit('김 팀장 건 기한 금요일로 바꿔줘');
  await until(() => lastRun(h).phase !== 'running');
  assert.deepEqual(outcome(lastRun(h), 'unsupported').choices?.map((c) => c.id), [1, 2]);
  h.session.submit(lastRun(h).text, { taskIds: [2 as TaskId], selectedMailIds: [] });
  await until(() => reqs.length === 2);
  assert.equal(reqs[1]!.text, '김 팀장 건 기한 금요일로 바꿔줘');
  assert.deepEqual(reqs[1]!.taskIds, [2]);
});


test('11-20 동시에 보내기: 앞 명령이 진행 중이어도 다음 명령을 받고, 각자 끝나며, 하나를 중지해도 다른 명령은 그대로', async () => {
  let release: () => void = () => {};
  const gate = new Promise<void>((r) => (release = r));
  const api = createMockApi({ latencyMs: 0, agentDelayMs: { rule: 0, model: 0 } });
  const h = await setup({
    runCommand: async (req, signal) => {
      if (req.text === '느린 명령') await gate;
      return api.runAgentCommand(req, signal);
    },
  });
  assert.equal(h.session.submit('느린 명령'), true);
  assert.equal(h.session.getState().busy, true);
  assert.equal(h.session.submit('미처리 업무 보여줘'), true); // 진행 중에도 받는다
  const runs = () => h.session.getState().entries.filter((e): e is Run => e.kind === 'run');
  await until(() => runs()[1]!.phase === 'done', '두 번째 명령이 먼저 끝남');
  assert.equal(runs()[0]!.phase, 'running');
  assert.equal(h.session.getState().busy, true); // 아직 하나가 돈다
  assert.equal(h.session.stop(runs()[0]!.id), true); // 그 명령만 중지
  assert.equal(runs()[0]!.phase, 'stopped');
  assert.equal(runs()[1]!.phase, 'done');
  assert.equal(h.session.getState().busy, false);
  release();
});

test('11-20 기록 → 그때 대화: 실행 기록 id로 대화 카드를 찾고, 끝난 대화는 탭 저장소에 남아 새로 만들어도 되살아난다', async () => {
  const store = new Map<string, string>();
  const storage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v), removeItem: (k: string) => void store.delete(k) };
  const api = createMockApi({ latencyMs: 0, agentDelayMs: { rule: 0, model: 0 } });
  const deps = {
    runCommand: (req: Parameters<typeof api.runAgentCommand>[0], signal: AbortSignal) => api.runAgentCommand(req, signal),
    execute: (p: string, ids: readonly TaskId[]) => api.executeAction(p, ids),
    undo: (id: number) => api.undoAction(id),
    refresh: () => {},
    selectedMailIds: () => [],
    now: () => Date.now(),
  };
  const s = createAgentSession(storage);
  s.setDeps(deps);
  s.submit('김 팀장님 건 다 처리했어');
  const runs = () => s.getState().entries.filter((e): e is Run => e.kind === 'run');
  await until(() => runs()[0]?.outcome?.type === 'confirm', '확인 카드');
  const id = runs()[0]!.id;
  s.confirm(id, (runs()[0]!.outcome as Extract<Outcome, { type: 'confirm' }>).targets.map((t) => t.id));
  await until(() => runs()[0]!.phase === 'done', '실행');
  const actionId = (runs()[0]!.outcome as Extract<Outcome, { type: 'result' }>).actionId;
  assert.equal(s.runForHistory(actionId, null), id);
  assert.equal(s.runForHistory(999_999, null), null); // 버튼 · 다른 화면에서 한 일
  s.focusRun(id);
  assert.equal(s.getState().focus?.target, `agent-card-${id}`);

  const again = createAgentSession(storage); // 새로고침
  assert.deepEqual(again.getState().entries.map((e) => e.id), s.getState().entries.map((e) => e.id));
  assert.equal(again.runForHistory(actionId, null), id);
  again.reset();
  assert.equal(createAgentSession(storage).getState().entries.length, 0);
});
