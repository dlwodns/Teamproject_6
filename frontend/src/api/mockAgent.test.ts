// 모의 runAgentCommand가 backend executor.py(BE-11 #50)처럼 AgentResult를 돌려주는지 — 시연 문장 기준(모의 데이터 v2, 11/6(금) 10:42).
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { AgentResult } from './contract.ts';
import { AgentUnavailableError, HttpError } from './errors.ts';
import { authorName, introName, nameMatches } from './mock/agentExecutor.ts';
import { MOCK_DELAY_MS } from './mock/agentPlanner.ts';
import { createMockApi } from './mockClient.ts';
import type { MailId, TaskId } from './types.ts';

const fast = () => createMockApi({ latencyMs: 0, agentDelayMs: { rule: 0, model: 0 } });
type Api = ReturnType<typeof fast>;

async function statuses(api: Api, ids: number[]): Promise<string[]> {
  const d = await api.getDashboard();
  return ids.map((id) => d.tasks.find((t) => t.id === id)!.status);
}

const ids = (r: AgentResult) => r.targets.map((t) => t.id as number);

test('② 김 팀장님 건 다 처리했어 → 확인 3건(미리보기만) → 실행 → 완료, ③ 방금 거 취소해 → 되돌림, 한 번 더 → 되묻기', async () => {
  const api = fast();
  const r = await api.runAgentCommand({ text: '김 팀장님 건 다 처리했어' });
  assert.equal(r.kind, 'confirm');
  assert.equal(r.title, '업무 3건을 완료로 변경하시겠습니까?');
  assert.equal(r.action, 'T03');
  assert.equal(r.actionName, '일괄_완료');
  assert.equal(r.source, 'agent_rule');
  assert.deepEqual(ids(r).sort((a, b) => a - b), [3, 9, 12]);
  assert.ok(r.targets.every((t) => t.mailId === 3 || t.mailId === 9));
  assert.deepEqual(r.notes, ["'김 팀장'을(를) 김민준 팀장으로"]);
  assert.ok(r.previewId);
  assert.ok(r.expiresAtMs! > Date.now()); // 벽시계 기준이라 화면이 지금 시각과 견줄 수 있다
  assert.deepEqual(await statuses(api, [3, 9, 12]), ['pending', 'pending', 'pending']); // 확인 전에는 바꾸지 않는다

  const ex = await api.executeAction(r.previewId!, r.targets.map((t) => t.id));
  assert.ok(ex.actionId !== null);
  assert.deepEqual(await statuses(api, [3, 9, 12]), ['done', 'done', 'done']);
  await assert.rejects(api.executeAction(r.previewId!), (e: unknown) => e instanceof HttpError && e.status === 409);

  const u = await api.runAgentCommand({ text: '방금 거 취소해' });
  assert.equal(u.kind, 'done');
  assert.equal(u.title, '3건의 처리를 취소했습니다');
  assert.equal(u.action, 'T04');
  assert.deepEqual(u.notes, [`행동 #${ex.actionId}(T03)를 되돌림`]);
  assert.ok(u.actionId !== null);
  assert.deepEqual(await statuses(api, [3, 9, 12]), ['pending', 'pending', 'pending']);

  const again = await api.runAgentCommand({ text: '방금 거 취소해' });
  assert.equal(again.kind, 'ask');
  assert.equal(again.title, '방금 취소한 작업을 다시 적용할지, 그 이전 작업도 취소할지 알려 주십시오');
  assert.deepEqual(again.notes, [`방금 행동 #${ex.actionId}을(를) 취소했습니다`]);
  assert.deepEqual(await statuses(api, [3, 9, 12]), ['pending', 'pending', 'pending']);
});

test('확인 카드에서 1건 체크를 풀고 실행하면 남긴 것만 바뀐다. 대상 밖 · 빈 목록은 422', async () => {
  const api = fast();
  const r = await api.runAgentCommand({ text: '김 팀장님 건 다 처리했어' });
  await assert.rejects(api.executeAction(r.previewId!, [99 as TaskId]), (e: unknown) => e instanceof HttpError && e.status === 422);
  await assert.rejects(api.executeAction(r.previewId!, []), (e: unknown) => e instanceof HttpError && e.status === 422);
  await api.executeAction(r.previewId!, [3, 9] as TaskId[]);
  assert.deepEqual(await statuses(api, [3, 9, 12]), ['done', 'done', 'pending']);
});

test('이거 완료: 고른 메일의 미처리 1건이면 확인 없이 바로(D37) + 되돌리기 가능, 고른 메일이 없으면 되묻기', async () => {
  const api = fast();
  const r = await api.runAgentCommand({ text: '이거 완료', selectedMailIds: [1 as MailId] });
  assert.equal(r.kind, 'done');
  assert.equal(r.title, '1건을 완료로 변경했습니다');
  assert.deepEqual(ids(r), [1]);
  assert.deepEqual(r.notes, ['선택한 메일 1통']);
  assert.deepEqual(await statuses(api, [1]), ['done']);
  await api.undoAction(r.actionId!);
  assert.deepEqual(await statuses(api, [1]), ['pending']);

  const ask = await api.runAgentCommand({ text: '이거 완료' });
  assert.equal(ask.kind, 'ask');
  assert.equal(ask.title, '어떤 업무인지 알려 주세요(보낸 사람 · 분류 · 기간 · 메일 선택)');
});

test('견적 건 내일 아침으로 미뤄: 미처리 · 나중에 둘 다 대상(resolve.py OPEN) → 2건 확인, 1건만 남겨 실행', async () => {
  const api = fast();
  const r = await api.runAgentCommand({ text: '견적 건 내일 아침으로 미뤄' });
  assert.equal(r.kind, 'confirm');
  assert.equal(r.title, '업무 2건을 11/07 08:30까지 연기하시겠습니까?');
  assert.deepEqual(ids(r).sort((a, b) => a - b), [2, 21]);
  const ex = await api.executeAction(r.previewId!, [2 as TaskId]);
  assert.equal(ex.tasks[0]?.snoozedUntilMs, Date.parse('2026-11-07T08:30:00+09:00'));
  assert.deepEqual(await statuses(api, [2]), ['snoozed']);

  const when = await api.runAgentCommand({ text: '견적 건 나중에 다시 알려줘' });
  assert.equal(when.kind, 'ask');
  assert.equal(when.title, '다시 알림 받을 시각을 알려 주십시오');
});

test('직전 결과(last_result_ids)는 메일 id: "그 2건 완료 처리해"는 그 메일들의 업무', async () => {
  const api = fast();
  const r = await api.runAgentCommand({ text: '그 2건 완료 처리해', lastResultIds: [3 as MailId] });
  assert.equal(r.kind, 'confirm');
  assert.deepEqual(ids(r).sort((a, b) => a - b), [3, 12]);
});

test('미처리 조회(T02) → query, 없는 사람 → empty', async () => {
  const api = fast();
  const q = await api.runAgentCommand({ text: '김 팀장님 건 뭐 남았어?' });
  assert.equal(q.kind, 'query');
  assert.equal(q.title, '미처리 업무가 3건 있습니다');
  const none = await api.runAgentCommand({ text: '홍 부장님 건 다 처리했어' });
  assert.equal(none.kind, 'empty');
  assert.equal(none.title, '해당하는 미처리 업무가 없습니다');
});

test('FE 제안 kind(모의만): ① 오늘 뭐 해야 돼? → summary, 답장 안 온 메일 → awaiting, 회신 초안 → draft', async () => {
  const api = fast();
  const s = await api.runAgentCommand({ text: '오늘 뭐 해야 돼?' });
  assert.equal(s.kind, 'summary');
  assert.equal(s.action, 'T01');
  assert.match(s.title, /^긴급 업무가 \d+건 있습니다$/);
  assert.ok(s.summary && s.summary.items.length > 0 && s.summary.items.length <= 5);
  assert.match(s.summary!.hint ?? '', /^그 밖에 미처리 \d+건 · 확인사항 \d+건/);

  const a = await api.runAgentCommand({ text: '답장 안 온 메일 있어?' });
  assert.equal(a.kind, 'awaiting');
  assert.deepEqual(a.awaiting?.map((x) => x.days), [4, 3]);

  const d = await api.runAgentCommand({ text: '이 메일 회신 초안 써줘', selectedMailIds: [3 as MailId] });
  assert.equal(d.kind, 'draft');
  assert.equal(d.draft?.to, '김민준 팀장');
  assert.ok(d.draft?.text.includes('계약서 수정본 검토 · 승인'));
});

test('점심 메뉴 추천해줘 → 엑사원 경로(기본 3초 넘게 기다림) 뒤 unsupported, 바뀐 것 없음', async () => {
  assert.ok(MOCK_DELAY_MS.model >= 3000 && MOCK_DELAY_MS.rule < 1000);
  const api = createMockApi({ latencyMs: 0, agentDelayMs: { rule: 0, model: 40 } });
  const t0 = Date.now();
  const r = await api.runAgentCommand({ text: '점심 메뉴 추천해줘' });
  assert.ok(Date.now() - t0 >= 35);
  assert.equal(r.kind, 'unsupported');
  assert.equal(r.title, '지원하지 않는 요청입니다');
  assert.equal(r.source, 'agent_model');
  assert.equal(r.action, null);
});

test('기다리는 중 중지하면 아무것도 바꾸지 않는다 · ?mock=error는 503(AgentUnavailableError) · 빈 글자 422', async () => {
  const api = createMockApi({ latencyMs: 0, agentDelayMs: { rule: 50, model: 50 } });
  const c = new AbortController();
  const p = api.runAgentCommand({ text: '이거 완료', selectedMailIds: [1 as MailId] }, c.signal);
  setTimeout(() => c.abort('stop'), 5);
  await assert.rejects(p);
  assert.deepEqual(await statuses(api, [1]), ['pending']);

  await assert.rejects(createMockApi({ latencyMs: 0, preview: 'error' }).runAgentCommand({ text: '오늘 뭐 해야 돼?' }), AgentUnavailableError);
  await assert.rejects(fast().runAgentCommand({ text: '   ' }), (e: unknown) => e instanceof HttpError && e.status === 422);
});

test('T17 사람 조회(AI-44): 연락처 · 메일의 쓴 사람으로 찾고, 이름만으로도 찾고, 본인은 본인이라고 답한다', async () => {
  const api = fast();
  const p = await api.runAgentCommand({ text: '김민준 팀장 누구였지' });
  assert.equal(p.kind, 'person');
  assert.equal(p.person?.email, 'minjun.kim@cne.example');
  assert.ok(p.person?.mails.some((m) => m.mailId === 3));
  assert.match(p.title, /^김민준 팀장님이 쓴 메일이 \d+통/);
  const g = await api.runAgentCommand({ text: '민준 팀장 누구였지' }); // 이름만
  assert.equal(g.person?.email, 'minjun.kim@cne.example');
  // 이준호 팀장 = 모의 사용자 본인 → 다른 사람 메일에 이름이 나온 메일
  const n = await api.runAgentCommand({ text: '이준호 팀장이 나한테 뭐라고 했었지' });
  assert.equal(n.kind, 'query');
  assert.match(n.title, /^이준호님 본인입니다/);
  assert.ok(n.mails?.some((m) => m.mailId === 1));
  assert.equal(introName('이준호 팀장님, 안녕하세요. 보안팀 이서준입니다.'), '이서준');
  assert.equal(introName('안녕하세요\n사업단PMO 임소희 책임입니다.'), '임소희');
  assert.equal(introName('회의 안내입니다.'), null);
  assert.equal(authorName('자료 보내 드립니다.\n\n문규남 드림'), '문규남');
  assert.equal(authorName('네\n보낸 사람: 임소희\n사업단PMO 임소희 책임입니다.'), null); // 인용된 앞 메일은 보지 않는다
  assert.ok(nameMatches('임 책임', '임소희', '책임') && nameMatches('소희', '임소희', null) && !nameMatches('희', '임소희', null));
});
