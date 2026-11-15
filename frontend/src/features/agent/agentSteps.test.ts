import assert from 'node:assert/strict';
import { test } from 'node:test';
import { isSendKey } from './agentKeys.ts';
import { SLOW_REQUEST_TIMEOUT_MS } from '../../api/httpClient.ts';
import { announceText, elapsedSec, finalSec, finishedLine, MODEL_TIMEOUT_SEC, runningLine, STOPPED_UNSURE_TEXT, stepsFor, understandNote } from './agentSteps.ts';

test('단계 목록: 상태 변경(T03 · T05 · T10)만 확인 단계를 둔다(기본 목록)', () => {
  assert.deepEqual(stepsFor('T05'), ['understand', 'target', 'confirm', 'exec']);
  assert.deepEqual(stepsFor('T02'), ['understand', 'target', 'exec']);
});

test('명령 이해 줄: 행동 · 이름 · 경로(규칙/엑사원). 응답이 없거나 경로를 모르면 빼고 적는다', () => {
  assert.equal(understandNote('T03', '일괄_완료', 'agent_rule'), 'T03 일괄_완료 · 규칙');
  assert.equal(understandNote(null, null, 'agent_model'), '엑사원');
  assert.equal(understandNote('T01', '오늘_요약', null), 'T01 오늘_요약');
  assert.equal(understandNote(null, null, null), null);
});

test('단계 목록: 상태 변경(T03 · T05)만 확인 단계를 둔다', () => {
  assert.deepEqual(stepsFor('T03', ['T03', 'T05']), ['understand', 'target', 'confirm', 'exec']);
  assert.deepEqual(stepsFor('T01', ['T03', 'T05']), ['understand', 'target', 'exec']);
  assert.deepEqual(stepsFor('T04', ['T03', 'T05']), ['understand', 'target', 'exec']);
  assert.deepEqual(stepsFor(null, ['T03', 'T05']), ['understand', 'target', 'exec']);
});

test('진행 중 한 줄: 지금 단계 진행형 · n/전체, 경과 초는 3초부터', () => {
  const steps = ['understand', 'target', 'confirm', 'exec'] as const;
  assert.deepEqual(runningLine({ steps, status: ['done', 'active', 'pending', 'pending'], action: 'T03', elapsed: 2 }), {
    label: '대상 업무를 찾는 중…',
    meta: '2/4',
  });
  assert.deepEqual(runningLine({ steps, status: ['done', 'active', 'pending', 'pending'], action: 'T03', elapsed: 3 }), {
    label: '대상 업무를 찾는 중…',
    meta: '2/4 · 3초',
  });
  assert.equal(runningLine({ steps, status: ['done', 'done', 'wait', 'pending'], action: 'T03', elapsed: 5 }).label, '확인을 기다리고 있습니다');
  assert.equal(runningLine({ steps, status: ['done', 'done', 'done', 'active'], action: 'T03', elapsed: 1 }).label, '완료로 바꾸는 중…');
});

test('엑사원 경로 최대 대기는 HTTP 제한(140초)과 같다 — 화면이 backend보다 먼저 끊지 않게(#63 리뷰)', () => {
  assert.equal(MODEL_TIMEOUT_SEC * 1000, SLOW_REQUEST_TIMEOUT_MS);
});

test('명령 이해가 3초를 넘으면 엑사원 문구(최대 140초), 남은 시간은 말하지 않는다', () => {
  const steps = ['understand', 'target', 'exec'] as const;
  const status = ['active', 'pending', 'pending'] as const;
  assert.equal(runningLine({ steps, status, action: null, elapsed: 2 }).label, '명령을 이해하는 중…');
  assert.deepEqual(runningLine({ steps, status, action: null, elapsed: 4 }), { label: '엑사원이 명령을 해석하는 중… (최대 140초)', meta: '1/3 · 4초' });
});

test('끝난 줄: N단계 완료 · M초(건너뜀은 세지 않음), 실패 · 중지 · 취소', () => {
  assert.deepEqual(finishedLine('done', ['done', 'done', 'done', 'done'], 6), { label: '4단계 완료', meta: '6초' });
  assert.deepEqual(finishedLine('done', ['done', 'done', 'skip', 'done'], 2), { label: '3단계 완료', meta: '2초' });
  assert.equal(finishedLine('fail', ['fail', 'skip', 'skip'], 5).label, '처리하지 못했습니다');
  assert.equal(finishedLine('stopped', ['done', 'skip', 'skip'], 1).label, '취소했습니다. 변경된 내용은 없습니다');
  assert.equal(finishedLine('stopped', ['skip', 'skip', 'skip'], 1, true).label, STOPPED_UNSURE_TEXT);
  assert.equal(finishedLine('cancelled', ['done', 'done', 'skip', 'skip'], 9).label, '취소했습니다. 변경된 내용은 없습니다');
});

test('시간: 경과는 내림, 끝난 시간은 반올림하되 최소 1초', () => {
  assert.equal(elapsedSec(1000, 3999), 2);
  assert.equal(elapsedSec(1000, 500), 0);
  assert.equal(finalSec(0, 200), 1);
  assert.equal(finalSec(0, 5600), 6);
  assert.equal(announceText('명령을 이해하는 중…'), '명령을 이해하는 중');
});

test('입력칸: Enter는 보내고, Shift+Enter · 한글 조합 중 Enter(isComposing · 229)는 보내지 않는다', () => {
  assert.equal(isSendKey({ key: 'Enter', shiftKey: false }), true);
  assert.equal(isSendKey({ key: 'Enter', shiftKey: true }), false);
  assert.equal(isSendKey({ key: 'Enter', shiftKey: false, isComposing: true }), false);
  assert.equal(isSendKey({ key: 'Enter', shiftKey: false, keyCode: 229 }), false);
  assert.equal(isSendKey({ key: 'Enter', shiftKey: false, ctrlKey: true }), false);
  assert.equal(isSendKey({ key: 'a', shiftKey: false }), false);
});

test('작업 카드 상태: 진행 중 → 완료 · 실패 · 취소됨(중지와 확인 취소는 모두 취소됨), 취소 문구는 처리됐을 수 있음을 말한다', async () => {
  const { jobState, JOB_STATE_TEXT } = await import('./agentSteps.ts');
  assert.equal(JOB_STATE_TEXT[jobState('running')], '진행 중');
  assert.equal(JOB_STATE_TEXT[jobState('done')], '완료');
  assert.equal(JOB_STATE_TEXT[jobState('fail')], '실패');
  assert.equal(JOB_STATE_TEXT[jobState('stopped')], '취소됨');
  assert.equal(JOB_STATE_TEXT[jobState('cancelled')], '취소됨');
  assert.match(STOPPED_UNSURE_TEXT, /이미 처리되었다면 기록에서 되돌릴 수 있습니다/);
  assert.doesNotMatch(STOPPED_UNSURE_TEXT, /바뀐 것은 없어요/);
});
