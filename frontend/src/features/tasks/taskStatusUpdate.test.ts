import assert from 'node:assert/strict';
import { test } from 'node:test';
import { HttpError, NetworkError } from '../../api/errors.ts';
import type { DashboardSource, MailId, TaskId } from '../../api/types.ts';
import { buildDashboard } from './aggregate.ts';
import { actionErrorText, applyTaskStatuses } from './taskStatusUpdate.ts';

const src: DashboardSource = {
  origin: { kind: 'mock', dataset: 'test', version: 'v' },
  asOfMs: 0,
  contacts: [],
  mails: [{ id: 1 as MailId, sourceId: 'M-1', direction: 'received', sender: 'a@example.com', subject: 's', receivedAtMs: 0, category: '요청' }],
  tasks: [1, 2].map((n) => ({ id: n as TaskId, mailId: 1 as MailId, text: `t${n}`, dueAtMs: null, status: 'pending' as const, seenAtMs: null })),
};

test('바뀐 업무만 새 상태로, 다시 집계하면 칸 · 미처리 수가 줄어든다', () => {
  const next = applyTaskStatuses(src, [{ id: 1 as TaskId, status: 'done' }]);
  assert.equal(next.tasks[0]!.status, 'done');
  assert.equal(next.tasks[1], src.tasks[1]); // 안 바뀐 업무는 같은 객체
  assert.equal(src.tasks[0]!.status, 'pending'); // 원본은 그대로
  const before = buildDashboard(src);
  const after = buildDashboard(next);
  assert.equal(after.status.pending, before.status.pending - 1);
  assert.equal(after.nature.find((c) => c.key === '요청')!.items.length, 1);
});

test('바뀐 게 없거나 목록에 없는 id면 같은 원본을 돌려준다(다시 그리지 않음)', () => {
  assert.equal(applyTaskStatuses(src, [{ id: 1 as TaskId, status: 'pending' }]), src);
  assert.equal(applyTaskStatuses(src, [{ id: 99 as TaskId, status: 'done' }]), src);
});

test('오류 안내는 동작 이름으로 시작하고 원문을 드러내지 않는다', () => {
  assert.match(actionErrorText('완료로 바꾸지', new NetworkError('x')), /^완료로 바꾸지 못했습니다\. 서버에 연결하지 못했습니다/);
  assert.match(actionErrorText('되돌리지', new HttpError(409, '/api/actions/3/undo 응답 409')), /이미 다른 곳에서 바뀌었습니다/);
  assert.doesNotMatch(actionErrorText('되돌리지', new HttpError(500, '/api/secret')), /\/api/);
});
