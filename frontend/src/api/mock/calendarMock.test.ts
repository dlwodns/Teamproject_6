// 모의 캘린더: 다시 알릴 시각이 지난 미룬 업무(BE-D24 보완). 서버 backend/app/services/calendar.py와 같은 정책인지 본다.
import assert from 'node:assert/strict';
import { mock, test } from 'node:test';
import type { TaskId } from '../types.ts';
import { createMockApi } from '../mockClient.ts';
import { calendarItems, type MockCalendarInput } from './calendarMock.ts';

const at = (s: string) => Date.parse(s);
const DAY = 24 * 3600_000;
const lo = at('2026-11-16T00:00:00+09:00');
const hi = lo + 7 * DAY;

function input(tasks: MockCalendarInput['tasks'], until: Record<number, number>, nowMs: number): MockCalendarInput {
  return { tasks, snoozedUntil: (id) => until[id] ?? null, subjects: new Map(), events: [], nowMs };
}
const kinds = (inp: MockCalendarInput, from = lo, to = hi) =>
  calendarItems(inp, from, to).filter((i) => i.task_id !== null).map((i) => [i.kind, i.task_id, i.start.slice(0, 16)]);

const t1 = { id: 1, mail_id: 1, text: '견적', status: 'snoozed', due_at: '2026-11-18T18:00:00+09:00' };
const noDue = { id: 4, mail_id: 4, text: '기한 없음', status: 'snoozed', due_at: null };

test('지난 미룬 업무: 직전엔 다시 알림, 정각 · 이후엔 원래 기한 날짜에 기한(중복 없음)', () => {
  const until = { 1: at('2026-11-17T09:00:00+09:00') };
  assert.deepEqual(kinds(input([t1], until, at('2026-11-17T08:59:00+09:00'))), [['snoozed', 1, '2026-11-17T09:00']]);
  for (const now of [at('2026-11-17T09:00:00+09:00'), at('2026-11-17T10:00:00+09:00')]) {
    assert.deepEqual(kinds(input([t1], until, now)), [['due', 1, '2026-11-18T18:00']]);
  }
});

test('같은 날(다시 알림 18일 09:00 · 기한 18일 18:00): 지나면 기한 하나만', () => {
  const inp = input([t1], { 1: at('2026-11-18T09:00:00+09:00') }, at('2026-11-18T09:30:00+09:00'));
  assert.deepEqual(kinds(inp, at('2026-11-18T00:00:00+09:00'), at('2026-11-19T00:00:00+09:00')), [['due', 1, '2026-11-18T18:00']]);
});

test('기한 없는 업무는 다시 알릴 시각이 지나도 다시 알림 표시를 남긴다', () => {
  const inp = input([noDue], { 4: at('2026-11-17T09:00:00+09:00') }, at('2026-11-17T10:00:00+09:00'));
  assert.deepEqual(kinds(inp), [['snoozed', 4, '2026-11-17T09:00']]);
});

test('KST 날짜 경계: 기한 18일 00:00은 18일 칸에만, 끝난 업무는 없다', () => {
  const midnight = { ...t1, id: 7, due_at: '2026-11-18T00:00:00+09:00' };
  const done = { ...t1, id: 6, status: 'done' };
  const inp = input([midnight, done], { 7: at('2026-11-16T09:00:00+09:00') }, at('2026-11-16T10:00:00+09:00'));
  assert.deepEqual(kinds(inp, at('2026-11-17T00:00:00+09:00'), at('2026-11-18T00:00:00+09:00')), []);
  assert.deepEqual(kinds(inp, at('2026-11-18T00:00:00+09:00'), at('2026-11-19T00:00:00+09:00')), [['due', 7, '2026-11-18T00:00']]);
});

test('모의 API: 미루기 → 시각이 지나면 기한 날짜 → 다시 미루기 → 되돌리기 → 완료', async (t) => {
  t.mock.timers.enable({ apis: ['Date'], now: Date.now() });
  const api = createMockApi({ latencyMs: 0, agentDelayMs: { rule: 0, model: 0 } });
  const first = await api.getCalendar('2026-11-01', '2026-12-12');
  const now0 = first.asOfMs;
  const due = first.items.find((i) => i.kind === 'due' && i.taskId !== null && i.startMs > now0 + DAY)!;
  assert.ok(due, '내일 이후 기한인 업무가 있어야 한다');
  const id = due.taskId as TaskId;
  const mine = async () => (await api.getCalendar('2026-11-01', '2026-12-12')).items.filter((i) => i.taskId === id).map((i) => [i.kind, i.startMs]);

  const until = now0 + 3600_000;
  await api.patchTaskStatus(id, { status: 'snoozed', snoozedUntilMs: until });
  assert.deepEqual(await mine(), [['snoozed', until]], '다시 알릴 시각 전');
  t.mock.timers.tick(3600_000); // 정각
  assert.deepEqual(await mine(), [['due', due.startMs]], '정각: 원래 기한 날짜');
  t.mock.timers.tick(60_000);
  const later = now0 + 2 * DAY;
  const again = await api.patchTaskStatus(id, { status: 'snoozed', snoozedUntilMs: later });
  assert.deepEqual(await mine(), [['snoozed', later]], '다시 미루기: 기한 표시가 빠지고 새 시각');
  await api.undoAction(again.actionId!);
  assert.deepEqual(await mine(), [['due', due.startMs]], '되돌리기: 지난 시각으로 돌아가 다시 기한');
  await api.patchTaskStatus(id, { status: 'done' });
  assert.deepEqual(await mine(), [], '완료: 없음');
  mock.timers.reset();
});
