import assert from 'node:assert/strict';
import test from 'node:test';
import type { MailId } from '../../api/types.ts';
import { agentViewer } from './agentViewer.ts';

test('결과물 칸 메일(11-18): 메일 줄을 누르면 그 결과와 메일을 열고, 다른 결과를 열거나 닫으면 메일이 풀린다', () => {
  agentViewer.openMail(3, 100 as MailId);
  assert.deepEqual([agentViewer.getState().openRunId, agentViewer.getState().mail], [3, { runId: 3, mailId: 100 }]);
  agentViewer.closeMail(); // [‹ 결과로]
  assert.deepEqual([agentViewer.getState().openRunId, agentViewer.getState().mail], [3, null]);
  agentViewer.openMail(3, 17 as MailId);
  agentViewer.open(4);
  assert.deepEqual([agentViewer.getState().openRunId, agentViewer.getState().mail], [4, null]);
  agentViewer.openMail(4, 7 as MailId);
  agentViewer.close();
  assert.deepEqual([agentViewer.getState().openRunId, agentViewer.getState().mail], [null, null]);
});
