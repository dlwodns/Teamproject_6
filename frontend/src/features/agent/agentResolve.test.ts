import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createMockApi } from '../../api/mockClient.ts';
import type { Contact, DashboardSource, MailId } from '../../api/types.ts';
import { planCommand, type PlanContext } from './agentMock.ts';
import { needsConfirm, replyDraftPath, resolvePlan, resolveSender, withEul, withEuro, withI, type Resolution } from './agentResolve.ts';

const ctx = (over: Partial<PlanContext> = {}): PlanContext => ({ now: '2026-11-06T10:42:00', selected_mail_ids: [], last_result_ids: [], ...over });
const load = (): Promise<DashboardSource> => createMockApi({ latencyMs: 0 }).getDashboard();

function as<K extends Resolution['kind']>(r: Resolution, kind: K): Extract<Resolution, { kind: K }> {
  assert.equal(r.kind, kind, JSON.stringify(r));
  return r as Extract<Resolution, { kind: K }>;
}

const contact = (name: string, position: string): Contact => ({ email: `${name}@x`, name, position, isSuperior: false, isFavorite: false });

test('조사: 받침 · ㄹ 받침 · 숫자 · 따옴표 · 괄호', () => {
  assert.equal(withEul("'김 팀장님'"), "'김 팀장님'을");
  assert.equal(withEul('메일'), '메일을');
  assert.equal(withEul('업무 처리'), '업무 처리를');
  assert.equal(withEuro('김민준 팀장(사업2팀)'), '김민준 팀장(사업2팀)으로');
  assert.equal(withEuro('11/7(토) 08:30'), '11/7(토) 08:30으로');
  assert.equal(withEuro('메일'), '메일로');
  assert.equal(withEuro('회의'), '회의로');
  assert.equal(withI("'견적'"), "'견적'이");
  assert.equal(withI("'보고서'"), "'보고서'가");
});

test('발신자 맞추기: 성 + 직책, 이름 앞부분 + 직책, 직책이 다르면 아니다, 여럿이면 모두', () => {
  const cs = [contact('김민준', '팀장'), contact('김서연', '책임'), contact('김도현', '팀장'), contact('박지호', '매니저')];
  assert.deepEqual(resolveSender('김 팀장', cs).map((c) => c.name), ['김민준', '김도현']);
  assert.deepEqual(resolveSender('김민준 팀장', cs).map((c) => c.name), ['김민준']);
  assert.deepEqual(resolveSender('김 책임', cs).map((c) => c.name), ['김서연']);
  assert.deepEqual(resolveSender('이 팀장', cs), []);
});

test('D37 확인 규칙: 상태 변경 1건은 바로, 2건 이상 · 후보 여럿 · 설정 변경은 확인, 조회는 확인 없음', () => {
  assert.equal(needsConfirm({ mutating: true, targetCount: 1, candidateCount: 1 }), false);
  assert.equal(needsConfirm({ mutating: true, targetCount: 2, candidateCount: 1 }), true);
  assert.equal(needsConfirm({ mutating: true, targetCount: 1, candidateCount: 2 }), true);
  assert.equal(needsConfirm({ mutating: true, targetCount: 1, candidateCount: 1, settingsChange: true }), true);
  assert.equal(needsConfirm({ mutating: false, targetCount: 5, candidateCount: 3 }), false);
});

test('V-16: 김 팀장님 건 다 처리했어 → 김민준 팀장 미처리 3건, 확인 카드, 해석 문장', async () => {
  const data = await load();
  const r = as(resolvePlan(planCommand('김 팀장님 건 다 처리했어', ctx()), data, { lastAction: null }), 'status');
  assert.equal(r.op, 'complete');
  assert.deepEqual(
    r.targets.map((t) => t.text),
    ['계약서 수정본 검토 · 승인', '고객사 정기 미팅 참석 여부 회신', '협력사 평가표 작성'],
  );
  assert.ok(r.targets.every((t) => t.sender === '김민준 팀장'));
  assert.equal(r.confirm, true);
  assert.equal(r.question, '김민준 팀장님 업무 3건을 완료로 바꿀까요?');
  assert.deepEqual(r.interpretation, ["'김 팀장님'을 김민준 팀장(사업2팀)으로 해석했어요."]);
});

test('나중에 1건(견적)은 확인 없이 바로, 미처리(pending)만 대상', async () => {
  const data = await load();
  const r = as(resolvePlan(planCommand('견적 건 내일 아침으로 미뤄', ctx()), data, { lastAction: null }), 'status');
  assert.equal(r.op, 'snooze');
  assert.deepEqual(r.targets.map((t) => t.text), ['3차 견적서 수정본 송부']); // '견적 비교표 업데이트'는 이미 나중에
  assert.equal(r.confirm, false);
  assert.equal(r.untilMs, Date.parse('2026-11-07T08:30:00+09:00'));
});

test('이거 완료: 고른 메일의 미처리 업무. 1건이면 바로, 2건이면 확인', async () => {
  const data = await load();
  const one = as(resolvePlan(planCommand('이거 완료', ctx({ selected_mail_ids: ['1'] })), data, { lastAction: null }), 'status');
  assert.deepEqual(one.targets.map((t) => t.id), [1]);
  assert.equal(one.confirm, false);
  const two = as(resolvePlan(planCommand('이거 완료', ctx({ selected_mail_ids: ['3'] })), data, { lastAction: null }), 'status');
  assert.deepEqual(two.targets.map((t) => t.id), [3, 12]);
  assert.equal(two.confirm, true);
});

test('대상이 없거나 사람을 못 찾으면 실패로 끝난다(지어내지 않음)', async () => {
  const data = await load();
  as(resolvePlan(planCommand('이 팀장님 건 다 처리했어', ctx()), data, { lastAction: null }), 'fail');
  const none = as(resolvePlan(planCommand('공지 메일 다 처리했어', ctx()), data, { lastAction: null }), 'fail');
  assert.equal(none.title, '완료로 바꿀 미처리 업무가 없어요');
  as(resolvePlan(planCommand('오늘 뭐 해야 돼?', ctx()), undefined, { lastAction: null }), 'fail');
});

test('되돌리기: 이 패널의 마지막 행동이 있어야 한다', async () => {
  const data = await load();
  const plan = planCommand('방금 거 취소해', ctx());
  as(resolvePlan(plan, data, { lastAction: null }), 'fail');
  const u = as(resolvePlan(plan, data, { lastAction: { runId: 2, actionId: 7, count: 3 } }), 'undo');
  assert.equal(u.last.actionId, 7);
});

test('오늘 요약: 기한 지남 · 오늘 마감 · ASAP를 급한 순으로, 그 밖 미처리 · 확인사항 수', async () => {
  const data = await load();
  const s = as(resolvePlan(planCommand('오늘 뭐 해야 돼?', ctx()), data, { lastAction: null }), 'summary');
  const pending = data.tasks.filter((t) => t.status === 'pending').length;
  const n = Number(/긴급 (\d+)건/.exec(s.title)?.[1]);
  assert.ok(n > 0);
  assert.ok(s.items.length <= 5);
  assert.equal(s.items[0]?.due.kind, 'urgent');
  assert.ok(s.hint?.startsWith(`그 밖에 미처리 ${pending - n}건 · 확인사항 `));
});

test('답장 없는 메일: 3일 이상, 오래된 순. 응답 대기 칸이 없으면(실제 서버 BE-13 전) 실패', async () => {
  const data = await load();
  const a = as(resolvePlan(planCommand('답장 안 온 메일 있어?', ctx()), data, { lastAction: null }), 'awaiting');
  assert.deepEqual(a.items.map((i) => i.days), [4, 3]);
  assert.equal(a.title, '3일 이상 답장이 없는 메일 2건이에요');
  const { awaiting: _drop, ...noAwaiting } = data;
  as(resolvePlan(planCommand('답장 안 온 메일 있어?', ctx()), noAwaiting, { lastAction: null }), 'fail');
});

test('회신 초안: 고른 메일 받는 사람 · 제목 · 하고 싶은 말만', async () => {
  const data = await load();
  const d = as(resolvePlan(planCommand('이 메일 회신 초안 써줘', ctx({ selected_mail_ids: ['3'] })), data, { lastAction: null }), 'draft');
  assert.equal(d.to, '김민준 팀장');
  assert.equal(d.mailId, 3);
  assert.ok(d.text.includes('계약서 수정본 검토 · 승인'));
  assert.ok(!d.text.includes('안녕하세요')); // 인사 · 맺음은 답장 화면 템플릿 몫
});

test('초안 열기 주소: 받은편지함의 그 메일 + reply=1 + 초안 글자(인코딩)', () => {
  assert.equal(replyDraftPath(3 as MailId, '확인했습니다. 곧 회신드리겠습니다.'), `/mail/inbox/3?reply=1&draft=${encodeURIComponent('확인했습니다. 곧 회신드리겠습니다.')}`);
  assert.equal(new URLSearchParams(replyDraftPath(3 as MailId, 'a&b=c').split('?')[1]).get('draft'), 'a&b=c');
});
