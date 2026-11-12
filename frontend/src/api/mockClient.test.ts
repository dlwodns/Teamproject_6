import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { NotificationId } from './contract.ts';
import { ConfigError, HttpError, NotAvailableError } from './errors.ts';
import { createMockApi, readMockDataset } from './mockClient.ts';
import type { MailId, TaskId } from './types.ts';

const T = (n: number) => n as TaskId;
const fresh = () => createMockApi({ latencyMs: 0 });

test('데이터 묶음: 기본 v2, v1도 읽히고, 그 밖의 값은 설정 오류', async () => {
  assert.equal(readMockDataset(undefined), 'v2');
  assert.equal(readMockDataset('v1'), 'v1');
  assert.throws(() => readMockDataset('v3'), ConfigError);
  const v2 = await fresh().getDashboard();
  assert.deepEqual([v2.mails.length, v2.tasks.length, v2.awaiting?.length], [24, 23, 2]);
  assert.equal(v2.mails[0]!.lane, '할 일');
  const v1api = createMockApi({ latencyMs: 0, dataset: 'v1' });
  const v1 = await v1api.getDashboard();
  assert.equal(v1.awaiting, undefined); // v1에는 응답 대기 칸이 없다 → 숨김
  await assert.rejects(v1api.getAwaiting(), NotAvailableError);
  await assert.rejects(v1api.getMail(1 as MailId), NotAvailableError);
});

test('?mock=error · empty 흉내', async () => {
  await assert.rejects(createMockApi({ latencyMs: 0, preview: 'error' }).getSettings(), HttpError);
  const empty = createMockApi({ latencyMs: 0, preview: 'empty' });
  const d = await empty.getDashboard();
  assert.deepEqual([d.mails.length, d.tasks.length, d.awaiting], [0, 0, []]);
  assert.deepEqual(await empty.getNotifications(), []);
});

test('1건 상태 바꾸기: 기록 id가 늘고, 같은 상태로 다시 바꾸면 기록 없음(null)', async () => {
  const api = fresh();
  const r1 = await api.patchTaskStatus(T(1), { status: 'done' });
  assert.equal(r1.actionId, 1);
  assert.equal(r1.tasks[0]!.status, 'done');
  assert.equal(typeof r1.tasks[0]!.doneAtMs, 'number');
  const again = await api.patchTaskStatus(T(1), { status: 'done' });
  assert.equal(again.actionId, null);
  const r2 = await api.patchTaskStatus(T(2), { status: 'excluded' });
  assert.equal(r2.actionId, 2);
  const d = await api.getDashboard();
  assert.equal(d.tasks.find((t) => t.id === 1)!.status, 'done'); // 대시보드에도 반영
});

test('BE-4와 같은 거절: 없는 업무 404, 나중에인데 시각 없음 422, 시각만 있음 422', async () => {
  const api = fresh();
  await assert.rejects(api.patchTaskStatus(T(999), { status: 'done' }), (e: unknown) => e instanceof HttpError && e.status === 404);
  await assert.rejects(api.patchTaskStatus(T(1), { status: 'snoozed' }), (e: unknown) => e instanceof HttpError && e.status === 422);
  await assert.rejects(api.patchTaskStatus(T(1), { status: 'done', snoozedUntilMs: 1 }), (e: unknown) => e instanceof HttpError && e.status === 422);
  const until = Date.parse('2026-11-07T09:00:00+09:00');
  const r = await api.patchTaskStatus(T(1), { status: 'snoozed', snoozedUntilMs: until });
  assert.equal(r.tasks[0]!.snoozedUntilMs, until);
});

test('되돌리기: 그 기록의 업무만 이전 상태로, 새 기록 id, 두 번째는 409, 뒤에 살아 있는 변경이 있으면 409', async () => {
  const api = fresh();
  const before = await api.getDashboard();
  const s1 = before.tasks.find((t) => t.id === 1)!.status;
  const a = await api.patchTaskStatus(T(1), { status: 'done' });
  await api.patchTaskStatus(T(2), { status: 'done' });
  const u = await api.undoAction(a.actionId!);
  assert.deepEqual([u.actionId, u.undoneActionId], [3, a.actionId]);
  assert.deepEqual(u.tasks.map((t) => [t.id, t.status]), [[1, s1]]);
  assert.equal((await api.getDashboard()).tasks.find((t) => t.id === 2)!.status, 'done'); // 다른 업무는 그대로
  await assert.rejects(api.undoAction(a.actionId!), (e: unknown) => e instanceof HttpError && e.status === 409);
  // 다시 하기(되돌리기를 되돌림)
  const redo = await api.undoAction(u.actionId);
  assert.equal(redo.tasks[0]!.status, 'done');
  // 완료 → 제외 뒤에 완료를 되돌리려 하면 409
  const b = await api.patchTaskStatus(T(4), { status: 'done' });
  await api.patchTaskStatus(T(4), { status: 'excluded' });
  await assert.rejects(api.undoAction(b.actionId!), (e: unknown) => e instanceof HttpError && e.status === 409);
  await assert.rejects(api.undoAction(999), (e: unknown) => e instanceof HttpError && e.status === 404);
});

test('여러 건: 미리보기 → 실행 한 번, 두 번째 실행은 409, 되돌리면 모두 돌아온다', async () => {
  const api = fresh();
  const p = await api.bulkPreview({ taskIds: [T(1), T(2), T(2)], status: 'done' });
  assert.deepEqual(p.targets.map((t) => t.id), [1, 2]);
  assert.equal(p.status, 'done');
  assert.equal((await api.getDashboard()).tasks.find((t) => t.id === 1)!.status, 'pending'); // 미리보기는 바꾸지 않는다
  const r = await api.executeAction(p.previewId);
  assert.deepEqual(r.tasks.map((t) => t.status), ['done', 'done']);
  await assert.rejects(api.executeAction(p.previewId), (e: unknown) => e instanceof HttpError && e.status === 409);
  await assert.rejects(api.executeAction('nope'), (e: unknown) => e instanceof HttpError && e.status === 404);
  const u = await api.undoAction(r.actionId!);
  assert.deepEqual(u.tasks.map((t) => t.status), ['pending', 'pending']);
});

test('알림 · 설정 · 연락처 바꾸기는 메모리에 남는다', async () => {
  const api = fresh();
  const list = await api.getNotifications();
  assert.equal(list.length, 6);
  const read = await api.patchNotification(1 as NotificationId, { read: true });
  assert.equal(typeof read.readAtMs, 'number');
  await assert.rejects(api.patchNotification(1 as NotificationId, { answer: 'yes' }), (e: unknown) => e instanceof HttpError && e.status === 422);
  const answered = await api.patchNotification(4 as NotificationId, { answer: 'yes' });
  assert.equal(typeof answered.answeredAtMs, 'number');
  assert.equal((await api.getNotifications()).find((n) => n.id === 4)!.answeredAtMs, answered.answeredAtMs);

  const s = await api.patchSettings({ remindTime: '09:00', quietStart: null });
  assert.equal(s.remindTime, '09:00');
  assert.equal(s.templates?.length, 4);
  assert.equal((await api.getSettings()).remindTime, '09:00');
  await assert.rejects(api.patchSettings({ remindTime: '9시' }), (e: unknown) => e instanceof HttpError && e.status === 422);

  const email = (await api.getDashboard()).contacts[0]!.email;
  const c = await api.patchContact(email, { isFavorite: true });
  assert.equal(c.isFavorite, true);
  assert.equal((await api.getDashboard()).contacts[0]!.isFavorite, true);
  await assert.rejects(api.patchContact('none@x', { isFavorite: true }), (e: unknown) => e instanceof HttpError && e.status === 404);
});

test('메일 한 통 · 요약: 본문과 그 메일 업무, 요약 없음은 null, summary_fail_first는 첫 요청만 실패', async () => {
  const api = fresh();
  const m = await api.getMail(1 as MailId);
  assert.equal(m.body.length, 4);
  assert.deepEqual(m.tasks.map((t) => t.mailId), m.tasks.map(() => 1));
  assert.equal(await api.summarizeMail(1 as MailId), null);
  assert.equal((await api.summarizeMail(12 as MailId))?.asks.length, 2);
  await assert.rejects(api.summarizeMail(24 as MailId), HttpError);
  assert.equal((await api.summarizeMail(24 as MailId))?.lang, 'fr');
  await assert.rejects(api.getMail(999 as MailId), (e: unknown) => e instanceof HttpError && e.status === 404);
});

test('지연 중 취소하면 그 요청은 거절된다', async () => {
  const api = createMockApi({ latencyMs: 50 });
  const c = new AbortController();
  const p = api.getDashboard(c.signal);
  c.abort();
  await assert.rejects(p);
});
