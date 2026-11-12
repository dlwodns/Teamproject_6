import assert from 'node:assert/strict';
import { test } from 'node:test';
import { dueLabel, dueState, formatKstFull, kstDayNumber } from './deadline.ts';

const t = (iso: string) => Date.parse(iso);
const ASOF = t('2026-10-20T09:00:00+09:00');

test('기한 경계: 기준 시각 정각은 오늘 마감(남음), 1ms 전은 기한 지남', () => {
  assert.equal(dueState(ASOF, ASOF), 'today');
  assert.equal(dueState(ASOF - 1, ASOF), 'overdue');
  assert.equal(dueState(t('2026-10-20T08:30:00+09:00'), ASOF), 'overdue');
});

test('KST 날짜 경계: 23:59:59는 오늘, 다음 날 00:00은 내일', () => {
  assert.equal(dueState(t('2026-10-20T23:59:59+09:00'), ASOF), 'today');
  assert.equal(dueState(t('2026-10-21T00:00:00+09:00'), ASOF), 'tomorrow');
  assert.equal(dueState(t('2026-10-21T23:59:59+09:00'), ASOF), 'tomorrow');
  assert.equal(dueState(t('2026-10-22T00:00:00+09:00'), ASOF), 'later');
});

test('UTC 날짜와 KST 날짜가 다른 시각도 KST로 판정한다', () => {
  // 2026-10-21T00:30 KST = 2026-10-20T15:30Z — UTC로는 기준 시각과 같은 날이지만 KST로는 내일
  assert.equal(dueState(t('2026-10-20T15:30:00Z'), ASOF), 'tomorrow');
  // 기준 시각이 KST 새벽이면 UTC로는 전날이다
  const earlyAsOf = t('2026-10-20T01:00:00+09:00'); // 2026-10-19T16:00Z
  assert.equal(dueState(t('2026-10-20T18:00:00+09:00'), earlyAsOf), 'today');
  assert.equal(kstDayNumber(earlyAsOf), kstDayNumber(t('2026-10-20T23:00:00+09:00')));
});

test('기한 없음은 due_at이 없을 때만', () => {
  assert.equal(dueState(null, ASOF), 'none');
});

test('표시용 시각은 실행 환경 시간대와 무관하게 KST', () => {
  assert.match(formatKstFull(ASOF), /2026.*10.*20.*09:00/);
});

test('기한 라벨(UX-D10): 짧은 글자만, ⚠ · \'기한 지남\' 글자 없음', () => {
  const text = (iso: string | null) => dueLabel(iso === null ? null : t(iso), ASOF).text;
  assert.equal(text('2026-10-18T18:00:00+09:00'), 'D+2');
  assert.equal(text('2026-10-20T08:30:00+09:00'), 'D+0'); // 같은 날 이미 지남
  assert.equal(text('2026-10-20T18:00:00+09:00'), '오늘 18:00');
  assert.equal(text('2026-10-21T12:00:00+09:00'), '내일 12:00');
  assert.equal(text('2026-10-23T09:00:00+09:00'), '10/23(금)');
  assert.equal(text(null), '기한 없음');
  for (const iso of ['2026-10-18T18:00:00+09:00', '2026-10-20T18:00:00+09:00']) {
    assert.doesNotMatch(text(iso), /⚠|기한 지남|마감/);
  }
});

test('기한 라벨 상태 · 전체 시각', () => {
  const l = dueLabel(t('2026-10-18T18:00:00+09:00'), ASOF);
  assert.equal(l.state, 'overdue');
  assert.match(l.full!, /2026.*10.*18.*18:00/);
  assert.equal(dueLabel(null, ASOF).full, null);
});
