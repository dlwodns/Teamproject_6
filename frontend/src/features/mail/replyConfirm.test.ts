// 답장 뒤 완료 확인 판단 시험(wireframe 13-5 · V-14 · V-15 · D48).
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { TaskId } from '../../api/types.ts';
import { dataNowMs, decideAfterSend, nextRemindAtMs } from './replyConfirm.ts';

const at = (s: string) => Date.parse(s);
const ids = [3, 4] as TaskId[];

test('다음 아침 알림 시각: 오늘 그 시각 전이면 오늘, 지났으면 내일(KST)', () => {
  assert.equal(nextRemindAtMs(at('2026-11-06T10:42:00+09:00'), '08:30'), at('2026-11-07T08:30:00+09:00'));
  assert.equal(nextRemindAtMs(at('2026-11-06T07:00:00+09:00'), '08:30'), at('2026-11-06T08:30:00+09:00'));
  assert.equal(nextRemindAtMs(at('2026-11-06T08:30:00+09:00'), '08:30'), at('2026-11-07T08:30:00+09:00'));
  assert.equal(nextRemindAtMs(at('2026-11-06T23:59:00+09:00'), '09:00'), at('2026-11-07T09:00:00+09:00'));
  assert.equal(nextRemindAtMs(at('2026-11-06T10:42:00+09:00'), '아침'), at('2026-11-07T08:30:00+09:00'));
});

test('V-14: 남은 업무가 있으면 시트, 없으면 토스트만', () => {
  const now = at('2026-11-06T10:42:00+09:00');
  assert.deepEqual(decideAfterSend(ids, null, now), { kind: 'sheet', taskIds: ids });
  assert.deepEqual(decideAfterSend(ids, undefined, now), { kind: 'sheet', taskIds: ids });
  assert.deepEqual(decideAfterSend([], null, now), { kind: 'sent-only' });
});

test("'오늘 다시 보지 않음' 시각 전에는 시트 없이 바로 완료, 지나면 다시 시트", () => {
  const until = at('2026-11-07T08:30:00+09:00');
  assert.deepEqual(decideAfterSend(ids, until, at('2026-11-06T15:00:00+09:00')), { kind: 'auto-complete', taskIds: ids, untilMs: until });
  assert.deepEqual(decideAfterSend(ids, until, until), { kind: 'sheet', taskIds: ids });
  assert.deepEqual(decideAfterSend([], until, at('2026-11-06T15:00:00+09:00')), { kind: 'sent-only' });
});

test('데이터 기준 지금: 기준 시각 + 받은 뒤 흐른 시간(뒤로 가지 않음)', () => {
  assert.equal(dataNowMs(1000, 5000, 8000), 4000);
  assert.equal(dataNowMs(1000, 5000, 4000), 1000);
});
