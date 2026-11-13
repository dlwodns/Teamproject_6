// 브리핑 · 회고 메뉴의 판단(FE-16 · 명세 4.3절): 날짜 · 빈 상태 문장 · 줄 버튼. 할 일을 권하는 문장이 없다(AI-D18)
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { briefingEmptyText, canSnoozeToMorning, dateLabel, josa, kstDate, shiftDate, weekRange } from './briefingModel.ts';

const at = (iso: string) => Date.parse(iso);

test('한국 날짜 · 날짜 옮기기 · 이름표 · 주 범위(월 ~ 금)', () => {
  assert.equal(kstDate(at('2026-11-05T15:30:00Z')), '2026-11-06');
  assert.equal(shiftDate('2026-11-01', -1), '2026-10-31');
  assert.equal(dateLabel('2026-11-06'), '11/6(금)');
  assert.equal(weekRange('2026-11-08'), '11/2(월) ~ 11/6(금)');
  assert.equal(weekRange('2026-11-02'), '11/2(월) ~ 11/6(금)');
});

test('조사는 받침을 따른다', () => {
  assert.equal(josa('아침 브리핑', '은', '는'), '아침 브리핑은');
  assert.equal(josa('퇴근 회고', '은', '는'), '퇴근 회고는');
});

test('빈 상태: 아직이면 언제 만드는지, 만들었는데 없으면 없었다고, 기록이 없으면 없다고. 내용이 있으면 null', () => {
  const now = at('2026-11-06T10:42:00+09:00');
  const evening = { kind: 'evening' as const, generatedAtMs: null, scheduledAtMs: at('2026-11-06T17:30:00+09:00'), sections: [] };
  assert.match(briefingEmptyText(evening, now) ?? '', /^퇴근 회고는 .*에 만들어요\.$/);
  assert.equal(briefingEmptyText({ ...evening, kind: 'morning', generatedAtMs: now - 1, scheduledAtMs: now - 1 }, now), '아침 브리핑에 담을 것이 없었어요.');
  assert.equal(briefingEmptyText({ ...evening, kind: 'weekly', scheduledAtMs: null }, now), '이날 만든 주간 회고가 없어요.');
  assert.equal(briefingEmptyText({ ...evening, generatedAtMs: now, sections: [{ id: 'x', title: 'x', count: 0, items: [] }] }, now), null);
  for (const t of [briefingEmptyText(evening, now), briefingEmptyText({ ...evening, scheduledAtMs: null }, now)]) assert.doesNotMatch(t ?? '', /챙기세요|하세요/);
});

test('내일 아침으로 미루기는 퇴근 회고 남은 일의, 아직 끝나지 않은 업무에만', () => {
  assert.equal(canSnoozeToMorning('remaining', 'pending'), true);
  assert.equal(canSnoozeToMorning('remaining', 'snoozed'), true);
  assert.equal(canSnoozeToMorning('remaining', 'done'), false);
  assert.equal(canSnoozeToMorning('due_tomorrow', 'pending'), false);
  assert.equal(canSnoozeToMorning('remaining', undefined), false);
});
