// 제안 카드 규칙(모의 v2) · 숨기기 · 기록 순서 · 기억 바꾸기 — suggestion_cards.md 8절 시험 1 · 3 · 4 · 5 · 8 · 9 · 10, PL-16 H2 · H4 · M2 · M3
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { HttpError } from '../errors.ts';
import { createMockApi } from '../mockClient.ts';
import type { ProvisionalDashboardResponse } from '../provisional.ts';
import type { TaskId } from '../types.ts';
import { computeSuggestions, hideRow, nextMorningMs, type HideRow, type SuggestionInput } from './agentPanelRules.ts';

const here = dirname(fileURLToPath(import.meta.url));
const V2 = (JSON.parse(readFileSync(resolve(here, 'dashboard.v2.json'), 'utf8')) as { response: ProvisionalDashboardResponse }).response;
const AS_OF = Date.parse(V2.as_of); // 2026-11-06 10:42 KST
const H = 3600_000;

function input(patch: Partial<SuggestionInput> = {}, data: ProvisionalDashboardResponse = V2): SuggestionInput {
  return { data, nowMs: AS_OF, remindTime: '08:30', awaitDays: 3, snoozedUntilMs: () => null, hides: new Map(), ...patch };
}
const keys = (i: SuggestionInput) => computeSuggestions(i).map((c) => c.key);
const T = (n: number) => n as TaskId;

test('모의 v2(11/6 10:42): 아침 요약 · 기한 지남 2 · 임박 2 · 응답 대기, 이 순서로 6장', () => {
  const cards = computeSuggestions(input());
  assert.deepEqual(
    cards.map((c) => c.key),
    ['morning:2026-11-06', 'overdue:task:1', 'overdue:task:2', 'due_soon:task:5', 'due_soon:task:3', 'no_reply:waiting'],
  );
  assert.equal(cards[0]!.title, '오늘 챙길 업무 14건, 그중 오늘 마감 2건이에요.');
  assert.equal(cards[1]!.title, "이서준 책임님 '1팀 보안 점검 조치 계획 회신' 기한이 D+2 경과했습니다.");
  assert.equal(cards[3]!.title, "최유진 책임님 '주간 보고 자료 제출' 기한이 오늘 17:00이에요. 초안을 써 둘까요?");
  // 시험 5: 응답 대기 한 장에 제목들, 버튼은 [응답 대기 보기]만(재촉 T14는 준비 전)
  const nr = cards[5]!;
  assert.equal(nr.title, '보낸 요청 2건에 3일 넘게 답이 없어요.');
  assert.deepEqual(nr.detail, ['서버 증설 견적 요청드립니다', '통합 테스트 일정 회신 부탁드립니다']);
  assert.deepEqual(nr.buttons.map((b) => b.action), ['T06']);
  // 회신 · 요청 · 검토 메일은 [초안 보기]가 주 버튼, 메뉴는 업무 아님 · 숨기기
  assert.deepEqual(cards[1]!.buttons.map((b) => [b.label, b.action, b.primary]), [['회신 작성', 'T07', true], ['연기', 'T05', false], ['완료 처리', 'T03', false]]);
  assert.deepEqual(cards[1]!.menu.map((b) => b.kind), ['action', 'hide']);
  assert.equal(cards[1]!.via, 'suggestion:overdue');
  // 일정 참석(meeting)은 모의 데이터에 메일 성격이 없어 띄우지 않는다
  assert.ok(!cards.some((c) => c.rule === 'meeting'));
});

test('기한 임박은 24시간 안만(내일 12:00 업무 9는 25시간 뒤라 아님), 아침 요약은 정오 전까지', () => {
  assert.ok(!keys(input()).includes('due_soon:task:9'));
  assert.ok(keys(input({ nowMs: AS_OF + 2 * H })).includes('due_soon:task:9'));
  assert.ok(!keys(input({ nowMs: AS_OF + 2 * H })).some((k) => k.startsWith('morning')));
});

test('시험 3: 기한이 지났고 상급자인 업무는 기한 지남 카드 한 장만, 상급자 카드는 2시간 지나야', () => {
  assert.ok(!keys(input()).some((k) => k.startsWith('priority_sender')));
  const data = structuredClone(V2);
  data.contacts.find((c) => c.email === 'serin.oh@cne.example')!.is_superior = true;
  const k = keys(input({}, data));
  assert.ok(k.includes('priority_sender:task:10')); // 11/5 15:30에 받음
  assert.ok(!k.includes('priority_sender:task:8')); // 10:02에 받아 40분 → 아직
  assert.ok(!k.includes('priority_sender:task:1')); // 이서준(상급자)은 기한 지남이 먼저
  const card = computeSuggestions(input({}, data)).find((c) => c.key === 'priority_sender:task:10')!;
  assert.equal(card.title, '오세린 사원님 메일 수신 후 19시간 경과했습니다.');
});

test('시험 4: 임박 카드를 숨겨도 기한이 지나면 지남 카드가 바로 뜬다. 숨김은 다음 R-아침까지', () => {
  const hides = new Map<string, HideRow>([['due_soon:task:3', hideRow('due_soon:task:3', input())]]);
  assert.equal(hides.get('due_soon:task:3')!.untilMs, Date.parse('2026-11-07T08:30:00+09:00'));
  assert.ok(!keys(input({ hides })).includes('due_soon:task:3'));
  assert.ok(keys(input({ hides, nowMs: Date.parse('2026-11-06T18:10:00+09:00') })).includes('overdue:task:3'));
  // 그 시각까지 1시간도 안 남으면 그다음 날
  assert.equal(nextMorningMs(Date.parse('2026-11-07T08:00:00+09:00'), '08:30'), Date.parse('2026-11-08T08:30:00+09:00'));
});

test('응답 대기 숨김: 그때 기다리던 메일만 남으면 계속 숨김, 새 메일이 기다림에 들어오면 다시 뜬다', () => {
  const hides = new Map([['no_reply:waiting', hideRow('no_reply:waiting', input())]]);
  assert.ok(!keys(input({ hides })).includes('no_reply:waiting'));
  const data = structuredClone(V2);
  data.awaiting!.push({ mail_id: 1003, subject: '새 요청', to: '누군가', sent_at: '2026-11-02T09:00:00+09:00', days: 4 });
  assert.ok(keys(input({ hides }, data)).includes('no_reply:waiting'));
});

test('시험 10: 미처리 0건 · 응답 대기 0건이면 카드 없음', () => {
  const data = structuredClone(V2);
  for (const t of data.tasks) t.status = 'done';
  data.awaiting = [];
  assert.deepEqual(computeSuggestions(input({}, data)), []);
});

test('시험 8: 접힌 목록은 3장 + 더 보기 수, 시험 2 · 9: 카드 [완료]는 via를 남기고 되돌리면 카드가 돌아온다', async () => {
  const api = createMockApi({ latencyMs: 0 });
  const list = await api.getSuggestions(3);
  assert.deepEqual([list.suggestions.length, list.more, list.total], [3, 3, 6]);
  assert.equal(list.generatedAtMs >= AS_OF, true);
  const r = await api.patchTaskStatus(T(5), { status: 'done', via: 'suggestion:due_soon' });
  assert.ok(!(await api.getSuggestions(50)).suggestions.some((c) => c.key === 'due_soon:task:5'));
  const h = await api.getActionHistory(7);
  assert.deepEqual([h.items[0]!.state, h.items[0]!.viaLabel, h.items[0]!.canUndo], ['done', '제안 카드(기한 임박)', true]);
  assert.equal(h.items[0]!.text, "'주간 보고 자료 제출' 업무를 완료 처리했습니다");
  await api.undoAction(r.actionId!);
  assert.ok((await api.getSuggestions(50)).suggestions.some((c) => c.key === 'due_soon:task:5'));
  await assert.rejects(api.patchTaskStatus(T(5), { status: 'done', via: 'Suggestion:X!' }), (e) => e instanceof HttpError && e.status === 422);
});

test('숨기기 API: 형식이 틀린 키는 422, 숨긴 카드는 목록에서 빠지고 접힌 수가 준다', async () => {
  const api = createMockApi({ latencyMs: 0 });
  await assert.rejects(api.hideSuggestion('bogus'), (e) => e instanceof HttpError && e.status === 422);
  const r = await api.hideSuggestion('overdue:task:1');
  assert.equal(r.hiddenUntilMs, Date.parse('2026-11-07T08:30:00+09:00'));
  const list = await api.getSuggestions(3);
  assert.deepEqual([list.total, list.more], [5, 2]);
  assert.ok(!list.suggestions.some((c) => c.key === 'overdue:task:1'));
});

test('기록 순서(H1 · H4): 확인 기다림이 맨 위, 그다음 최근 것부터. 되돌리면 되돌림 + 다시 하기, 다시 하면 완료로', async () => {
  const api = createMockApi({ latencyMs: 0 });
  const a = await api.patchTaskStatus(T(1), { status: 'done' });
  const b = await api.patchTaskStatus(T(2), { status: 'excluded', via: 'suggestion:overdue' });
  await api.bulkPreview({ taskIds: [T(7), T(8)], status: 'done' });
  let h = (await api.getActionHistory(7)).items;
  assert.deepEqual(h.map((i) => i.state), ['waiting', 'done', 'done']);
  assert.equal(h[0]!.text, '업무 2건 완료 — 확인을 기다려요');
  assert.equal(h[1]!.actionId, b.actionId);
  assert.equal(h[1]!.text, "'3차 견적서 수정본 송부' 업무를 목록에서 뺐어요(업무 아님)");
  const undo = await api.undoAction(a.actionId!);
  h = (await api.getActionHistory(7)).items;
  const row = h.find((i) => i.actionId === a.actionId)!;
  assert.deepEqual([row.state, row.canUndo, row.redoActionId], ['undone', false, undo.actionId]);
  await api.undoAction(undo.actionId); // 다시 하기
  const again = (await api.getActionHistory(7)).items.find((i) => i.actionId === a.actionId)!;
  assert.deepEqual([again.state, again.canUndo], ['done', true]);
});

test('에이전트가 아는 것(M2 · M3): 상급자를 끄면 목록 · 상급자 카드에서 빠지고, 기록에 남고 되돌릴 수 있다', async () => {
  const api = createMockApi({ latencyMs: 0 });
  const m = await api.getAgentMemory();
  assert.deepEqual([m.me.name, m.me.position, m.me.department, m.me.mailingLists], ['이준호', '팀장', '1팀', []]);
  assert.equal(m.learnFromMail, true);
  assert.deepEqual(m.people.map((p) => [p.name, p.isSuperior, p.isFavorite, p.usedBy]), [
    ['김민준', false, true, ['메일 분류']],
    ['이서준', true, false, ['제안 카드', '메일 분류']],
  ]);
  const lee = m.people[1]!;
  assert.equal(lee.origin.text, '처음 설정에서 넣었어요');
  // 같은 값이면 기록 없음
  assert.equal((await api.patchAgentMemoryPerson(lee.contactId, { isSuperior: true })).actionId, null);
  const ch = await api.patchAgentMemoryPerson(lee.contactId, { isSuperior: false });
  assert.ok(ch.actionId !== null);
  assert.ok(!ch.memory.people.some((p) => p.contactId === lee.contactId));
  const h = (await api.getActionHistory(7)).items[0]!;
  assert.deepEqual([h.text, h.viaLabel, h.canUndo], ['중요한 사람 표시를 바꿨어요', '에이전트가 아는 것', true]);
  await api.undoAction(ch.actionId!);
  const back = (await api.getAgentMemory()).people.find((p) => p.contactId === lee.contactId)!;
  assert.equal(back.isSuperior, true);
  assert.match(back.origin.text, /^11\/6 화면에서 취소했습니다$/);
  await assert.rejects(api.patchAgentMemoryPerson(999, { isFavorite: true }), (e) => e instanceof HttpError && e.status === 404);
});

test('M3: 상급자로 정하면 그분 업무에 상급자 카드가 생기고, 끄면 사라진다', async () => {
  const api = createMockApi({ latencyMs: 0 });
  const dash = await api.getDashboard();
  const serin = dash.contacts.findIndex((c) => c.email === 'serin.oh@cne.example') + 1;
  await api.patchAgentMemoryPerson(serin, { isSuperior: true });
  assert.ok((await api.getSuggestions(50)).suggestions.some((c) => c.key === 'priority_sender:task:10'));
  await api.patchAgentMemoryPerson(serin, { isSuperior: false });
  assert.ok(!(await api.getSuggestions(50)).suggestions.some((c) => c.key === 'priority_sender:task:10'));
});

test('내 정보: 배포 목록 주소 검사 · 소문자 · 같은 주소 합치기, 빈 글자는 null, 메일 기억하기 끄기', async () => {
  const api = createMockApi({ latencyMs: 0 });
  await assert.rejects(api.patchAgentMemoryMe({ mailingLists: [{ address: 'a b@x', kind: 'team' }] }), (e) => e instanceof HttpError && e.status === 422);
  const r = await api.patchAgentMemoryMe({
    position: '  ',
    mailingLists: [
      { address: 'Team1@CNE.example', kind: 'team' },
      { address: 'team1@cne.example', kind: 'role' },
    ],
  });
  assert.deepEqual(r.memory.me.mailingLists, [{ address: 'team1@cne.example', kind: 'team' }]);
  assert.equal(r.memory.me.position, null);
  const h = (await api.getActionHistory(7)).items[0]!;
  assert.equal(h.text, '내 정보(직책 · 팀 · 배포 목록)를 바꿨어요');
  assert.equal((await api.patchAgentSettings({ learnFromMail: false })).learnFromMail, false);
  assert.equal((await api.getAgentMemory()).learnFromMail, false);
});
