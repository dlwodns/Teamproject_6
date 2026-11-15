// 대화 메뉴 밖에서 보낸 명령의 결과 토스트(FE-16): 실행 취소 · 열기 · 알리지 않음
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { MailId } from '../../api/types.ts';
import type { Outcome, Run } from './agentSession.ts';
import { pageRunToast } from './pageRunToast.ts';

function run(outcome: Outcome | null, phase: Run['phase'] = 'done'): Run {
  return { kind: 'run', id: 1, text: '이거 완료해 줘', action: null, source: null, steps: [], status: [], notes: {}, phase, unsure: false, startedAtMs: 0, endedAtMs: 1, outcome };
}

test('실행 결과는 되돌릴 기록이 있으면 [실행 취소], 없으면 버튼 없이 한 줄', () => {
  const base = { type: 'result', title: '완료했어요', targets: [], undo: 'idle', notes: [] } as unknown as Extract<Outcome, { type: 'result' }>;
  assert.deepEqual(pageRunToast(run({ ...base, actionId: 9 })), { kind: 'undo', title: '완료했어요', action: 'undo', actionLabel: '실행 취소' });
  assert.deepEqual(pageRunToast(run({ ...base, actionId: null })), { kind: 'info', title: '완료했어요', action: null, actionLabel: null });
});

test('초안은 초안 메뉴로, 확인 카드는 기다리기 시작할 때 대화의 그 카드로, 실패는 대화로', () => {
  const draft = pageRunToast(run({ type: 'draft', title: '초안을 만들었어요', draft: { mailId: 1 as MailId, to: '김', subject: 'RE', text: '' } }));
  assert.equal(draft?.action, 'open_draft');
  const confirm = pageRunToast(run({ type: 'confirm', title: '3건 완료할까요?', action: 'T03', targets: [], expiresAtMs: null }, 'running'));
  assert.deepEqual(confirm, { kind: 'info', title: '확인이 필요해요 · 3건 완료할까요?', action: 'open_confirm', actionLabel: '열기' });
  assert.equal(pageRunToast(run({ type: 'error', title: '못 했어요', hint: '' }, 'fail'))?.kind, 'error');
  assert.equal(pageRunToast(run(null, 'fail'))?.title, '처리하지 못했어요');
});

test('아직 도는 중이거나 사용자가 취소 · 중지한 일은 알리지 않는다', () => {
  assert.equal(pageRunToast(run(null, 'running')), null);
  assert.equal(pageRunToast(run(null, 'cancelled')), null);
  assert.equal(pageRunToast(run(null, 'stopped')), null);
});
