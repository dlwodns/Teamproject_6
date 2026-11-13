import assert from 'node:assert/strict';
import { test } from 'node:test';
import { formatKstShort, snoozeOptions } from './snooze.ts';

const t = (iso: string) => Date.parse(iso);
const byKey = (now: number) => Object.fromEntries(snoozeOptions(now).map((o) => [o.key, o]));

test('시연 기준 11/6(금) 10:42: 네 가지 모두 보이고 시각이 KST로 맞다', () => {
  const now = t('2026-11-06T10:42:00+09:00');
  const o = byKey(now);
  assert.deepEqual(
    snoozeOptions(now).map((x) => x.label),
    ['1시간 뒤', '오늘 오후 4시', '내일 아침 08:30', '다음 주 월요일 09:00'],
  );
  assert.equal(o['in-1h']?.untilMs, t('2026-11-06T11:42:00+09:00'));
  assert.equal(o['today-16']?.untilMs, t('2026-11-06T16:00:00+09:00'));
  assert.equal(o['tomorrow-0830']?.untilMs, t('2026-11-07T08:30:00+09:00'));
  assert.equal(o['next-monday-09']?.untilMs, t('2026-11-09T09:00:00+09:00'));
  assert.equal(o['tomorrow-0830']?.detail, '11/7(토) 08:30');
  assert.equal(o['next-monday-09']?.detail, '11/9(월) 09:00');
});

test('KST 15:00부터는 오늘 오후 4시를 빼고, 14:59에는 보인다', () => {
  assert.equal(byKey(t('2026-11-06T14:59:59+09:00'))['today-16'] !== undefined, true);
  assert.equal(byKey(t('2026-11-06T15:00:00+09:00'))['today-16'], undefined);
  assert.equal(byKey(t('2026-11-06T22:00:00+09:00'))['today-16'], undefined);
});

test('UTC로는 전날인 KST 새벽도 KST 날짜로 계산한다', () => {
  // 2026-11-06T01:00 KST = 2026-11-05T16:00Z
  const o = byKey(t('2026-11-06T01:00:00+09:00'));
  assert.equal(o['today-16']?.untilMs, t('2026-11-06T16:00:00+09:00'));
  assert.equal(o['tomorrow-0830']?.untilMs, t('2026-11-07T08:30:00+09:00'));
});

test('다음 주 월요일: 월요일이면 7일 뒤, 일요일이면 다음 날', () => {
  assert.equal(byKey(t('2026-11-09T10:00:00+09:00'))['next-monday-09']?.untilMs, t('2026-11-16T09:00:00+09:00'));
  assert.equal(byKey(t('2026-11-08T10:00:00+09:00'))['next-monday-09']?.untilMs, t('2026-11-09T09:00:00+09:00'));
  // 월요일 새벽 08:00에도 오늘 09:00이 아니라 다음 주
  assert.equal(byKey(t('2026-11-09T08:00:00+09:00'))['next-monday-09']?.untilMs, t('2026-11-16T09:00:00+09:00'));
});

test('표시 형식: 월/일(요일) 시:분, 두 자리', () => {
  assert.equal(formatKstShort(t('2026-01-05T00:05:00+09:00')), '1/5(월) 00:05');
});
