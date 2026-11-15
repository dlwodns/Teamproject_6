// 기록 판단(실행 취소 · 다시 하기 · 이어서 보기) · 상대 시각
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { HistoryItem } from '../../api/contract.ts';
import { historyAction, relativeTime, splitHistory } from './agentPanelPlan.ts';

const item = (o: Partial<HistoryItem>): HistoryItem => ({
  id: 'log:1', state: 'done', action: 'set_status', actionId: 1, previewId: null, text: '', via: 'ui', viaLabel: '화면 버튼',
  auto: false, atMs: 0, expiresAtMs: null, canUndo: true, redoActionId: null, ...o,
});

test('기록: 확인 기다림은 위로, 버튼은 실행 취소 · 다시 하기 · 이어서 보기(열린 확인 카드가 있을 때만)', () => {
  const items = [item({ id: 'log:2' }), item({ id: 'preview:p', state: 'waiting', previewId: 'p', actionId: null, canUndo: false })];
  assert.deepEqual(splitHistory(items).waiting.map((i) => i.id), ['preview:p']);
  assert.deepEqual(historyAction(item({}), () => false), { kind: 'undo', actionId: 1 });
  assert.equal(historyAction(item({ canUndo: false }), () => false), null);
  assert.deepEqual(historyAction(item({ state: 'undone', canUndo: false, redoActionId: 9 }), () => false), { kind: 'redo', actionId: 9 });
  assert.equal(historyAction(items[1]!, () => false), null);
  assert.deepEqual(historyAction(items[1]!, (p) => p === 'p'), { kind: 'resume', previewId: 'p' });
});

test('상대 시각', () => {
  const now = Date.parse('2026-11-06T10:42:00+09:00');
  assert.equal(relativeTime(now + 5000, now), '방금 전');
  assert.equal(relativeTime(now - 10 * 60_000, now), '10분 전');
  assert.equal(relativeTime(now - 3 * 3600_000, now), '3시간 전');
  assert.equal(relativeTime(Date.parse('2026-11-05T09:00:00+09:00'), now), '11/5(목) 09:00');
});
