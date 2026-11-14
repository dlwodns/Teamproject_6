// 제안 카드 버튼 → 행동 표(계약 3.1) · 결과 줄 자리 · 기록 탭 판단
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { HistoryItem, Suggestion, SuggestionButton } from '../../api/contract.ts';
import type { MailId, TaskId } from '../../api/types.ts';
import {
  drawableButtons,
  historyAction,
  landingTab,
  planSuggestionButton,
  relativeTime,
  splitHistory,
  suggestionResultText,
  withResults,
} from './agentPanelPlan.ts';

const target = { taskIds: [7 as TaskId], mailIds: [3 as MailId] };
const b = (action: string, o: Partial<SuggestionButton> = {}): SuggestionButton => ({ label: action, kind: 'action', action, primary: false, params: {}, target, ...o });
const card = (buttons: SuggestionButton[], key = 'due_soon:task:7'): Suggestion => ({
  key,
  rule: 'due_soon',
  via: 'suggestion:due_soon',
  createdAtMs: 0,
  title: '',
  detail: [],
  taskIds: [7 as TaskId],
  mailIds: [3 as MailId],
  buttons,
  menu: [],
});
const c = card([]);

test('버튼 → 행동: 완료 · 업무 아님은 상태 변경 + 카드 via, 나중에는 시각 메뉴', () => {
  assert.deepEqual(planSuggestionButton(c, b('T03')), { type: 'status', status: 'done', taskId: 7, via: 'suggestion:due_soon' });
  assert.deepEqual(planSuggestionButton(c, b('T10')), { type: 'status', status: 'excluded', taskId: 7, via: 'suggestion:due_soon' });
  assert.deepEqual(planSuggestionButton(c, b('T05', { params: { until: null } })), { type: 'snooze', taskId: 7, via: 'suggestion:due_soon', untilMs: null });
  const until = planSuggestionButton(c, b('T05', { params: { until: '2026-11-07T08:30:00+09:00' } }));
  assert.equal(until?.type === 'snooze' && until.untilMs, Date.parse('2026-11-07T08:30:00+09:00'));
});

test('실제 모드: backend에 실행 경로가 없는 초안 · 요약 · 응답 대기는 화면으로 보낸다(#60 리뷰, 죽은 버튼 금지)', () => {
  // 답장 보내기 경로가 아직 없어 '초안'을 약속하지 않고 [메일 열기]로 그 메일만 연다(#60 2차 리뷰)
  assert.deepEqual(planSuggestionButton(c, b('T07'), 'http'), { type: 'route', to: '/mail/inbox/3?reply=1' });
  assert.deepEqual(planSuggestionButton(c, b('T01', { target: { taskIds: [], mailIds: [] } }), 'http'), { type: 'command', text: '오늘 뭐 해야 돼?' }); // T01은 11-14 서버에 생겼다
  assert.deepEqual(planSuggestionButton(c, b('T06'), 'http'), { type: 'route', to: '/dashboard' });
  assert.equal(planSuggestionButton(c, b('T07', { target: { taskIds: [], mailIds: [] } }), 'http'), null);
  // 바로 실행되는 것은 모드와 관계없이 같다
  assert.deepEqual(planSuggestionButton(c, b('T03'), 'http'), { type: 'status', status: 'done', taskId: 7, via: 'suggestion:due_soon' });
  assert.deepEqual(planSuggestionButton(c, b('open_mail', { kind: 'navigate' }), 'http'), { type: 'open_mail', mailId: 3 });
});

test('버튼 → 행동: 초안 · 요약 · 응답 대기는 명령 경로, 메일 열기는 이동, 숨기기는 hide, 모르는 행동은 그리지 않는다', () => {
  assert.deepEqual(planSuggestionButton(c, b('T07')), { type: 'route', to: '/mail/inbox/3?reply=1' });
  assert.deepEqual(planSuggestionButton(c, b('T01', { target: { taskIds: [], mailIds: [] } })), { type: 'command', text: '오늘 뭐 해야 돼?' });
  assert.deepEqual(planSuggestionButton(c, b('T06')), { type: 'command', text: '답장 안 온 메일 있어?' });
  assert.deepEqual(planSuggestionButton(c, b('open_mail', { kind: 'navigate' })), { type: 'open_mail', mailId: 3 });
  assert.deepEqual(planSuggestionButton(c, b('hide', { kind: 'hide', target: { taskIds: [], mailIds: [] } })), { type: 'hide', key: 'due_soon:task:7' });
  assert.equal(planSuggestionButton(c, b('T13')), null);
  assert.equal(planSuggestionButton(c, b('T03', { target: { taskIds: [], mailIds: [] } })), null);
  assert.equal(planSuggestionButton(c, b('T07', { target: { taskIds: [], mailIds: [] } })), null);
});

test('그릴 버튼: 실행 경로가 없는 것은 빼고, 주 버튼은 맨 뒤(확인 카드와 같은 순서)', () => {
  const x = card([b('T07', { primary: true }), b('T05'), b('T13'), b('T03')]);
  assert.deepEqual(drawableButtons(x).map((d) => d.button.action), ['T05', 'T03', 'T07']);
});

test('결과 줄은 카드가 목록에서 빠져도 처음 자리에 남는다', () => {
  const a = card([], 'a:1');
  const d = card([], 'd:1');
  const rows = withResults([a, d], [{ key: 'gone:1', index: 1 }, { key: 'd:1', index: 2 }]);
  assert.deepEqual(rows.map((r) => (r.type === 'card' ? r.card.key : `r:${r.result.key}`)), ['a:1', 'r:gone:1', 'r:d:1']);
  assert.equal(suggestionResultText('done', '주간 보고 자료 제출', null), "'주간 보고 자료 제출' 완료 처리했습니다");
  assert.equal(suggestionResultText('snoozed', null, Date.parse('2026-11-07T08:30:00+09:00')), '업무 11/7(토) 08:30까지 연기했습니다');
});

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

test('상대 시각과 처음 탭', () => {
  const now = Date.parse('2026-11-06T10:42:00+09:00');
  assert.equal(relativeTime(now + 5000, now), '방금 전');
  assert.equal(relativeTime(now - 10 * 60_000, now), '10분 전');
  assert.equal(relativeTime(now - 3 * 3600_000, now), '3시간 전');
  assert.equal(relativeTime(Date.parse('2026-11-05T09:00:00+09:00'), now), '11/5(목) 09:00');
  assert.equal(landingTab(undefined, false), null);
  assert.equal(landingTab(6, false), 'suggest');
  assert.equal(landingTab(0, false), 'chat');
  assert.equal(landingTab(undefined, true), 'chat');
});
