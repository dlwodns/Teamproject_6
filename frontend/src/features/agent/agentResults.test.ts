import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { MailId, TaskId } from '../../api/types.ts';
import { openedRun, viewerItemOf, viewerItems } from './agentResults.ts';
import type { Entry, Outcome, Run } from './agentSession.ts';

function runOf(id: number, outcome: Outcome | null, phase: Run['phase'] = 'done', text = '오늘 뭐 해야 돼?'): Run {
  return {
    kind: 'run', id, text, action: null, source: null, steps: ['understand', 'target', 'exec'], status: ['done', 'done', 'done'],
    notes: {}, phase, unsure: false, startedAtMs: 0, endedAtMs: 1000, outcome,
  };
}

const target = (n: number) => ({ id: n as TaskId, mailId: (100 + n) as MailId, text: `업무 ${n}`, status: 'pending' as const, snoozedUntilMs: null });
const summaryItem = { taskId: 1 as TaskId, mailId: 101 as MailId, text: '견적서 회신', dueAtMs: null, dueRaw: 'ASAP' };

test('결과물로 여는 결과: 초안 · 요약 · 업무 목록 · 답장 없는 메일. 짧은 카드 이름은 건수로', () => {
  assert.deepEqual(viewerItemOf(runOf(2, { type: 'draft', title: '초안을 만들었어요', draft: { mailId: 1 as MailId, to: '김', subject: 'RE: 견적', text: '안녕하세요' } })), {
    runId: 2, kind: 'draft', label: '초안 1건', title: '초안을 만들었어요',
  });
  assert.equal(viewerItemOf(runOf(2, { type: 'summary', title: '긴급 1건이에요', summary: { items: [summaryItem], hint: null } }))?.label, '요약');
  assert.equal(viewerItemOf(runOf(2, { type: 'query', title: '미처리 3건', targets: [target(1), target(2), target(3)], notes: [] }))?.label, '업무 3건');
  assert.equal(viewerItemOf(runOf(2, { type: 'awaiting', title: '2통', items: [{ mailId: 1 as MailId, subject: 's', to: 't', days: 3, sentAtMs: 0 }, { mailId: 2 as MailId, subject: 's', to: 't', days: 4, sentAtMs: 0 }] } as Outcome))?.label, '메일 2건');
});

test('대화에 그대로 두는 결과: 실행 결과 · 알림 · 실패 · 0건 · 진행 중', () => {
  assert.equal(viewerItemOf(runOf(2, { type: 'result', title: '완료로 바꿨어요', targets: [target(1)], actionId: 1, undo: 'idle', notes: [] })), null);
  assert.equal(viewerItemOf(runOf(2, { type: 'notice', title: '없어요', hint: null })), null);
  assert.equal(viewerItemOf(runOf(2, { type: 'error', title: '실패', hint: '' }, 'fail')), null);
  assert.equal(viewerItemOf(runOf(2, { type: 'query', title: '0건', targets: [], notes: [] })), null);
  assert.equal(viewerItemOf(runOf(2, { type: 'summary', title: '없어요', summary: { items: [], hint: null } })), null);
  // 브리핑 문장만 있어도 연다
  assert.equal(viewerItemOf(runOf(2, { type: 'summary', title: '없어요', summary: { items: [], hint: null, text: '오늘은 한가해요.' } }))?.kind, 'summary');
  assert.equal(viewerItemOf(runOf(2, null, 'running')), null);
});

test('고른 결과 열기 · 다시 열기: 대화에 있는 결과만, 없어진 결과는 빈 상태', () => {
  const entries: Entry[] = [
    { kind: 'user', id: 1, text: '오늘 뭐 해야 돼?' },
    runOf(2, { type: 'summary', title: '긴급 1건이에요', summary: { items: [summaryItem], hint: null } }),
    { kind: 'user', id: 3, text: '완료' },
    runOf(4, { type: 'result', title: '완료로 바꿨어요', targets: [target(1)], actionId: 1, undo: 'idle', notes: [] }),
    { kind: 'user', id: 5, text: '초안' },
    runOf(6, { type: 'draft', title: '초안', draft: { mailId: 1 as MailId, to: '김', subject: 'RE', text: '본문' } }),
  ];
  assert.deepEqual(viewerItems(entries).map((i) => i.runId), [2, 6]);
  assert.equal(openedRun(entries, null), null); // 처음에는 빈 상태
  assert.equal(openedRun(entries, 6)?.id, 6);
  assert.equal(openedRun(entries, 2)?.id, 2); // 지난 결과 다시 열기
  assert.equal(openedRun(entries, 4), null); // 대화에 두는 결과는 열지 않는다
  assert.equal(openedRun([], 6), null); // 새로고침 등으로 대화가 사라짐
});
