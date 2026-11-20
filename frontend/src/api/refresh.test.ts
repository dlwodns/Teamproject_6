import assert from 'node:assert/strict';
import { test } from 'node:test';
import { IDLE_REFRESH_MS, PENDING_REFRESH_MS, PENDING_STALL_MS, refreshInterval } from './queries.ts';

test('분류 대기: 수가 줄어드는 동안만 자주 받고, 그대로 멈춰 있으면 가끔으로(실패 · AI 꺼짐에 끝없이 5초마다 받지 않게)', () => {
  const seen = { count: 0, since: 0 };
  assert.equal(refreshInterval(3, 0, seen), PENDING_REFRESH_MS);
  assert.equal(refreshInterval(2, 60_000, seen), PENDING_REFRESH_MS);
  assert.equal(refreshInterval(2, 60_000 + PENDING_STALL_MS, seen), IDLE_REFRESH_MS);
  assert.equal(refreshInterval(1, 60_000 + PENDING_STALL_MS + 1, seen), PENDING_REFRESH_MS); // 다시 줄면 자주
  assert.equal(refreshInterval(0, 0, seen), IDLE_REFRESH_MS);
});
