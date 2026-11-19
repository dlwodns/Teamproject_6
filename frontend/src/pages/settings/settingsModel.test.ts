import assert from 'node:assert/strict';
import { test } from 'node:test';
import { formatDays, fromKstLocal, parseDays, toKstLocal } from './settingsModel.ts';

test('근무 요일: 서버 형식("1-5" · "1,3,5")을 읽고 쉼표로 쓴다', () => {
  assert.deepEqual([...parseDays('1-5')], [1, 2, 3, 4, 5]);
  assert.deepEqual([...parseDays('1,3,6-7')].sort(), [1, 3, 6, 7]);
  assert.equal(formatDays(new Set([5, 1, 3])), '1,3,5');
});

test('부재 중 칸: 한국 시각 datetime-local ↔ ms', () => {
  const ms = Date.parse('2026-11-20T18:30:00+09:00');
  assert.equal(toKstLocal(ms), '2026-11-20T18:30');
  assert.equal(fromKstLocal('2026-11-20T18:30'), ms);
});
