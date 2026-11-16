import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { MailId } from '../../api/types.ts';
import { COMPLETION_TOAST_MS, completionText, finishedSince, notifyDecision, runningIds, type NotifyContext } from './agentNotify.ts';
import type { Entry, Outcome, Run } from './agentSession.ts';

function runOf(id: number, outcome: Outcome | null, phase: Run['phase'] = 'done', text = '오늘 뭐 해야 돼?'): Run {
  return {
    kind: 'run', id, text, action: null, source: null, steps: ['understand', 'target', 'exec'], status: ['done', 'done', 'done'],
    notes: {}, phase, unsure: false, startedAtMs: 0, endedAtMs: 1000, outcome,
  };
}

const ctx = (over: Partial<NotifyContext> = {}): NotifyContext => ({
  onAgentPage: false, hidden: false, browserOptIn: false, permission: 'default', ...over,
});
const draftRun = runOf(2, { type: 'draft', title: '초안을 만들었어요', draft: { mailId: 1 as MailId, to: '김', subject: 'RE', text: '본문' } });
const noticeRun = runOf(2, { type: 'notice', title: '없어요', hint: null });

test('보고 있으면(캐치봇 화면, 탭이 보임) 알리지 않고 결과물 칸에 바로 연다', () => {
  assert.deepEqual(notifyDecision(draftRun, ctx({ onAgentPage: true })), { toast: false, toastTimeout: 0, browser: false, openInViewer: true });
  assert.equal(notifyDecision(noticeRun, ctx({ onAgentPage: true })).openInViewer, false); // 대화에 두는 결과
});

test('보고 있지 않으면 토스트 하나. 브라우저 알림은 탭이 가려졌고 · 사용자가 켰고 · 허락됐을 때만', () => {
  const d = notifyDecision(draftRun, ctx());
  assert.equal(d.toast, true);
  assert.equal(d.toastTimeout, COMPLETION_TOAST_MS);
  assert.equal(d.browser, false);
  // 탭이 가려짐: 보고 있지 않다. 토스트는 돌아와서 보게 닫지 않는다
  const hidden = notifyDecision(draftRun, ctx({ hidden: true, browserOptIn: true, permission: 'granted' }));
  assert.deepEqual(hidden, { toast: true, toastTimeout: 0, browser: true, openInViewer: false });
  assert.equal(notifyDecision(draftRun, ctx({ hidden: true, browserOptIn: false, permission: 'granted' })).browser, false); // 켜지 않음
  assert.equal(notifyDecision(draftRun, ctx({ hidden: true, browserOptIn: true, permission: 'default' })).browser, false); // 허락 전
  assert.equal(notifyDecision(draftRun, ctx({ hidden: true, browserOptIn: true, permission: 'denied' })).browser, false);
  assert.equal(notifyDecision(draftRun, ctx({ hidden: true, browserOptIn: true, permission: 'unsupported' })).browser, false);
  assert.equal(notifyDecision(draftRun, ctx({ browserOptIn: true, permission: 'granted' })).browser, false); // 탭이 보이면 토스트만
  // 에이전트 화면인데 탭이 가려짐: 알리고, 결과물 칸에도 열어 둔다
  assert.equal(notifyDecision(draftRun, ctx({ onAgentPage: true, hidden: true })).openInViewer, true);
});

test('실패도 알리고, 스스로 취소한 일 · 진행 중은 알리지 않는다', () => {
  assert.equal(notifyDecision(runOf(2, { type: 'error', title: '요청을 처리하지 못했습니다', hint: '' }, 'fail'), ctx()).toast, true);
  assert.equal(notifyDecision(runOf(2, null, 'stopped'), ctx()).toast, false);
  assert.equal(notifyDecision(runOf(2, null, 'cancelled'), ctx()).toast, false);
  assert.equal(notifyDecision(runOf(2, null, 'running'), ctx()).toast, false);
});

test('끝난 작업 찾기 · 알림 글자', () => {
  const before: Entry[] = [{ kind: 'user', id: 1, text: 'a' }, runOf(2, null, 'running'), runOf(4, null, 'done')];
  const prev = runningIds(before);
  assert.deepEqual([...prev], [2]);
  assert.deepEqual(finishedSince(prev, before), []);
  const after: Entry[] = [before[0]!, draftRun, before[2]!];
  assert.deepEqual(finishedSince(prev, after).map((r) => r.id), [2]);
  assert.deepEqual(completionText(draftRun), { title: '초안을 만들었어요', body: "'오늘 뭐 해야 돼?'" });
  const long = runOf(3, null, 'fail', '가'.repeat(60));
  assert.equal(completionText(long).title, '처리하지 못했습니다');
  assert.equal(completionText(long).body.length, 42); // 따옴표 2 + 40자
});

test('확인 카드를 기다리기 시작하면 한 번 알리고, 기다리는 동안은 다시 알리지 않는다 (#62 리뷰)', () => {
  const confirm: Outcome = { type: 'confirm', title: '3건을 완료로 변경하시겠습니까?', action: 'T03', targets: [], expiresAtMs: null };
  const prev = runningIds([runOf(2, null, 'running')]);
  const waitingRun = runOf(2, confirm, 'running');
  assert.deepEqual(finishedSince(prev, [waitingRun]).map((r) => r.id), [2]);
  assert.deepEqual([...runningIds([waitingRun])], []);
  assert.equal(notifyDecision(waitingRun, ctx()).toast, true);
  assert.equal(notifyDecision(waitingRun, ctx({ onAgentPage: true })).toast, false);
  assert.equal(completionText(waitingRun).title, '3건을 완료로 변경하시겠습니까?');
});
