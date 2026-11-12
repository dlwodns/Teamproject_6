import assert from 'node:assert/strict';
import { test } from 'node:test';
import { durationFor, INFO_MS, MAX_TOASTS, pushToast, remainingAfter, removeToast, WITH_ACTION_MS, type Toast } from './toastQueue.ts';

const t = (id: number): Toast => ({ id, kind: 'info', text: `t${id}`, durationMs: INFO_MS });

test('정보 5초, 버튼이 있거나 오류면 8초 (wireframe 13-6)', () => {
  assert.equal(durationFor({ kind: 'info', text: 'a' }), INFO_MS);
  assert.equal(durationFor({ kind: 'info', text: 'a', action: { label: '되돌리기', run: () => {} } }), WITH_ACTION_MS);
  assert.equal(durationFor({ kind: 'error', text: 'a' }), WITH_ACTION_MS);
});

test('동시에 3개까지, 넘으면 오래된 것부터 닫는다', () => {
  let list: Toast[] = [];
  for (let i = 1; i <= 4; i++) list = pushToast(list, t(i));
  assert.equal(MAX_TOASTS, 3);
  assert.deepEqual(list.map((x) => x.id), [2, 3, 4]);
  assert.deepEqual(removeToast(list, 3).map((x) => x.id), [2, 4]);
});

test('멈춘 동안은 줄지 않고, 흐른 만큼만 줄며 0 밑으로 내려가지 않는다', () => {
  assert.equal(remainingAfter(5000, 1000, 3000), 3000);
  assert.equal(remainingAfter(5000, 1000, 1000), 5000);
  assert.equal(remainingAfter(5000, 1000, 9000), 0);
  assert.equal(remainingAfter(5000, 1000, 500), 5000); // 시계가 뒤로 가도 늘지 않는다
});
