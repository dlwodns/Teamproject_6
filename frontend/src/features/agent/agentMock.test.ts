import assert from 'node:assert/strict';
import { test } from 'node:test';
import { kstNaive, MOCK_SUPPORTED, parseKstNaive, planCommand, remindAt, type PlanContext } from './agentMock.ts';

// 모의 데이터 v2 기준 시각: 2026-11-06(금) 10:42 KST
const NOW = '2026-11-06T10:42:00';
const ctx = (over: Partial<PlanContext> = {}): PlanContext => ({ now: NOW, selected_mail_ids: [], last_result_ids: [], ...over });
const nowMs = parseKstNaive(NOW)!;

test('시각 글자: KST 시간대 없는 ISO와 epoch 밀리초를 오간다', () => {
  assert.equal(kstNaive(nowMs), NOW);
  assert.equal(parseKstNaive('2026-11-06'), Date.parse('2026-11-06T00:00:00+09:00'));
  assert.equal(parseKstNaive('엉뚱한 글자'), null);
});

test('① 오늘 뭐 해야 돼? → T01 오늘_요약(규칙), 날짜는 오늘', () => {
  const p = planCommand('오늘 뭐 해야 돼?', ctx());
  assert.equal(p.action, 'T01');
  assert.equal(p.action_name, '오늘_요약');
  assert.equal(p.source, 'rule');
  assert.equal(p.reason, null);
  assert.deepEqual(p.params, { date: '2026-11-06' });
  assert.equal(p.prompt_version, null);
  assert.ok(p.rules_version.startsWith('agent_rules_v1.4'));
});

test('② 김 팀장님 건 다 처리했어 → T03, 발신자 단서 "김 팀장"(이름 · 직책), 키워드로 "팀장님"을 잡지 않는다', () => {
  const p = planCommand('김 팀장님 건 다 처리했어', ctx());
  assert.equal(p.action, 'T03');
  assert.equal(p.target.sender, '김 팀장');
  assert.equal(p.target.keyword, null);
  assert.deepEqual(p.target.mail_ids, []);
  assert.equal(p.source, 'rule');
});

test('③ 방금 거 취소해 → T04 되돌리기. 일정 · 구독 취소는 되돌리기가 아니다', () => {
  assert.equal(planCommand('방금 거 취소해', ctx()).action, 'T04');
  assert.equal(planCommand('되돌려줘', ctx()).action, 'T04');
  const meeting = planCommand('회의 취소 메일 써줘', ctx());
  assert.notEqual(meeting.action, 'T04');
});

test('이거 완료: 고른 메일이 있으면 그 메일(T03 mail_ids), 없으면 되묻기', () => {
  const p = planCommand('이거 완료', ctx({ selected_mail_ids: ['3'] }));
  assert.equal(p.action, 'T03');
  assert.deepEqual(p.target.mail_ids, ['3']);
  const q = planCommand('이거 완료', ctx());
  assert.equal(q.action, null);
  assert.equal(q.reason, 'ambiguous');
  assert.deepEqual(q.candidates, ['T03']);
});

test('나중에: "견적 건 내일 아침으로 미뤄" → T05 키워드 견적 · 11/7 08:30, 요일은 오늘 빼고 가장 가까운 날', () => {
  const p = planCommand('견적 건 내일 아침으로 미뤄', ctx());
  assert.equal(p.action, 'T05');
  assert.equal(p.target.keyword, '견적');
  assert.deepEqual(p.params, { until: '2026-11-07T08:30:00' });
  // 기준일이 금요일이라 '금요일'은 다음 주 금요일
  assert.equal(planCommand('견적 건은 금요일에 다시 알려줘', ctx()).params.until, '2026-11-13T08:30:00');
  // 언제인지 없으면 되묻는다
  const q = planCommand('견적 건 나중에 다시 알려줘', ctx());
  assert.equal(q.action, null);
  assert.equal(q.reason, 'ambiguous');
});

test('remindAt: 상대 시각 · 시각만 · 다음 주 · 오후', () => {
  const at = (t: string) => {
    const ms = remindAt(t, nowMs);
    return ms === null ? null : kstNaive(ms);
  };
  assert.equal(at('2시간 뒤에'), '2026-11-06T12:42:00');
  assert.equal(at('오후 3시에'), '2026-11-06T15:00:00');
  assert.equal(at('9시에'), '2026-11-07T09:00:00'); // 오늘 9시는 지났다 → 내일
  assert.equal(at('다음 주에'), '2026-11-09T08:30:00');
  assert.equal(at('다음 주 수요일'), '2026-11-11T08:30:00');
  assert.equal(at('내일 오후'), '2026-11-07T18:00:00');
  assert.equal(at('모레 10시 반'), '2026-11-08T10:30:00');
  assert.equal(at('언젠가'), null);
});

test('⑥ 답장 안 온 메일 있어? → T06(기본 3일), 회신 초안은 고른 메일 1통이 있어야 한다', () => {
  const p = planCommand('답장 안 온 메일 있어?', ctx());
  assert.equal(p.action, 'T06');
  assert.deepEqual(p.params, { min_days: 3 });
  assert.equal(planCommand('일주일 넘게 답장 안 온 거', ctx()).params.min_days, 7);
  const d = planCommand('이 메일 회신 초안 써줘', ctx({ selected_mail_ids: ['3'] }));
  assert.equal(d.action, 'T07');
  assert.deepEqual(d.target.mail_ids, ['3']);
  assert.equal(planCommand('회신 초안 써줘', ctx()).reason, 'ambiguous');
});

test('모르는 문장 · 모의가 처리하지 못하는 행동 → 엑사원 경로로 지원 외(action null)', () => {
  for (const text of ['점심 메뉴 추천해줘', '아침 알림은 9시로 바꿔줘', '박 책임님 메일은 항상 중요로', '그 2건 재촉 메일 보내줘']) {
    const p = planCommand(text, ctx());
    assert.equal(p.action, null, text);
    assert.equal(p.reason, 'unsupported', text);
    assert.equal(p.source, 'model', text);
    assert.ok(p.prompt_version, text);
  }
});

test('부정 · 의문은 상태를 바꾸지 않는다', () => {
  assert.equal(planCommand('김 팀장님 건 완료 처리하지 마', ctx()).action, null);
  assert.equal(planCommand('김 팀장님 건 다 처리했나?', ctx()).action, null);
});

test('모의가 고르는 행동은 끝까지 처리할 수 있는 것뿐이다', () => {
  const texts = ['오늘 뭐 해야 돼?', '김 팀장님 건 다 처리했어', '방금 거 취소해', '견적 건 내일 아침으로 미뤄', '답장 안 온 메일 있어?'];
  for (const t of texts) {
    const a = planCommand(t, ctx()).action;
    assert.ok(a && MOCK_SUPPORTED.includes(a), t);
  }
});
