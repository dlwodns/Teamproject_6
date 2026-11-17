import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { AgentTarget } from '../../api/contract.ts';
import type { MailId, TaskId } from '../../api/types.ts';
import { HttpError } from '../../api/errors.ts';
import { confirmLabel, dueOf, executedTitle, replyDraftPath, resultMailIds, targetStatusText, UNDO_BLOCKED_TEXT, undoFailState, undoneActionId, withStates } from './agentText.ts';

const target = (id: number, mailId: number): AgentTarget => ({ id: id as TaskId, mailId: mailId as MailId, text: `업무 ${id}`, status: 'pending', snoozedUntilMs: null });

test('확인 카드 버튼 · 실행 뒤 제목은 executor.py 결과 문구와 같다', () => {
  assert.equal(confirmLabel('T03', 2), '2건 완료 처리');
  assert.equal(confirmLabel('T05', 1), '1건 미루기');
  const until = Date.parse('2026-11-07T08:30:00+09:00');
  const state = { id: 2 as TaskId, status: 'snoozed' as const, doneAtMs: null, snoozedUntilMs: until, statusChangedAtMs: null };
  assert.equal(executedTitle('T05', 1, { actionId: 4, tasks: [state] }), '1건을 11/07 08:30까지 연기했습니다');
  assert.equal(executedTitle('T03', 3, { actionId: 4, tasks: [] }), '3건을 완료 처리했습니다');
  assert.equal(executedTitle('T03', 3, { actionId: null, tasks: [] }), '이미 해당 상태여서 변경된 내용이 없습니다');
  assert.deepEqual(withStates([target(2, 2)], { actionId: 4, tasks: [state] })[0]?.status, 'snoozed');
});

test('되돌린 기록 id는 T04 notes에서, 직전 결과는 메일 id(겹치면 한 번)', () => {
  assert.equal(undoneActionId(['행동 #7(T03)를 되돌림']), 7);
  assert.equal(undoneActionId(['선택한 메일 1통']), null);
  assert.deepEqual(resultMailIds([target(3, 3), target(12, 3), target(9, 9)]), [3, 9]);
});

test('조회 상태 꼬리 · 요약 기한 표시', () => {
  assert.equal(targetStatusText(target(1, 1)), null);
  assert.equal(targetStatusText({ ...target(1, 1), status: 'snoozed', snoozedUntilMs: Date.parse('2026-11-14T09:00:00+09:00') }), '나중에(11/14 09:00)');
  const asOf = Date.parse('2026-11-06T10:42:00+09:00');
  assert.deepEqual(dueOf({ dueAtMs: null, dueRaw: 'ASAP' }, asOf), { kind: 'urgent', text: 'ASAP', full: '즉시(ASAP)' });
  assert.equal(dueOf({ dueAtMs: Date.parse('2026-11-04T18:00:00+09:00'), dueRaw: null }, asOf).kind, 'urgent');
  assert.equal(dueOf({ dueAtMs: Date.parse('2026-11-06T18:00:00+09:00'), dueRaw: null }, asOf).kind, 'today');
  // 회고의 완료 업무: 기한이 지났어도 '완료'(#190 리뷰 2)
  assert.deepEqual(dueOf({ dueAtMs: Date.parse('2026-11-06T09:00:00+09:00'), dueRaw: null, section: 'done_today' }, asOf),
    { kind: 'done', text: '완료', full: '완료' });
});

test('초안 열기 주소: 받은편지함의 그 메일 + reply=1 + 초안 글자(인코딩)', () => {
  assert.equal(replyDraftPath(3 as MailId, '확인했습니다. 곧 회신드리겠습니다.'), `/mail/inbox/3?reply=1&draft=${encodeURIComponent('확인했습니다. 곧 회신드리겠습니다.')}`);
  assert.equal(new URLSearchParams(replyDraftPath(3 as MailId, 'a&b=c').split('?')[1]).get('draft'), 'a&b=c');
});

test('되돌리기 409는 blocked(다시 하지 않음), 그 밖의 실패는 error(다시 누를 수 있음) — #60 리뷰', () => {
  assert.equal(undoFailState(new HttpError(409, '이미 되돌린 기록입니다')), 'blocked');
  assert.equal(undoFailState(new HttpError(500, '서버 오류')), 'error');
  assert.equal(undoFailState(new TypeError('Failed to fetch')), 'error');
  assert.equal(UNDO_BLOCKED_TEXT, '이미 변경되어 되돌릴 수 없습니다');
});
