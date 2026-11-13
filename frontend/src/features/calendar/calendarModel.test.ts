// 캘린더 화면 계산(FE-12) · 모의 캘린더(BE-15 흉내) 시험. 입력 → 기대 결과.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { CalendarItem } from '../../api/contract.ts';
import { createMockApi } from '../../api/mockClient.ts';
import { byDay, canAddMeeting, dayTitle, gridRange, monthGrid, monthOf, shiftMonth, shortTime, timeRange } from './calendarModel.ts';

const at = (iso: string) => Date.parse(iso);
const item = (over: Partial<CalendarItem>): CalendarItem => ({
  kind: 'due', title: 'x', startMs: at('2026-11-12T14:00:00+09:00'), endMs: null, timeStated: true,
  mailId: null, taskId: null, eventId: null, subject: null, auto: false, ...over,
});

test('2026년 11월 달력: 일요일 11/1부터 6주 42칸, 12/12까지', () => {
  const cells = monthGrid({ year: 2026, month: 11 });
  assert.equal(cells.length, 42);
  assert.deepEqual([cells[0]!.key, cells[0]!.weekday, cells[0]!.inMonth], ['2026-11-01', 0, true]);
  assert.deepEqual(gridRange(cells), { start: '2026-11-01', end: '2026-12-12' });
  assert.equal(cells.filter((c) => c.inMonth).length, 30);
});

test('달 1일이 주 중간이면 앞 칸은 지난달: 2026년 12월은 11/29(일)부터', () => {
  const cells = monthGrid({ year: 2026, month: 12 });
  assert.deepEqual([cells[0]!.key, cells[0]!.inMonth, cells[2]!.key, cells[2]!.inMonth], ['2026-11-29', false, '2026-12-01', true]);
});

test('달 넘기기: 12월 다음은 다음 해 1월, 1월 앞은 지난해 12월. KST 자정 직전은 그날', () => {
  assert.deepEqual(shiftMonth({ year: 2026, month: 12 }, 1), { year: 2027, month: 1 });
  assert.deepEqual(shiftMonth({ year: 2026, month: 1 }, -1), { year: 2025, month: 12 });
  assert.deepEqual(monthOf(at('2026-11-30T23:59:00+09:00')), { year: 2026, month: 11 });
  assert.deepEqual(monthOf(at('2026-11-30T15:00:00Z')), { year: 2026, month: 12 }); // UTC 15시 = KST 12/1 0시
});

test('시각 표시: 시각 없는 기한은 비우고 "시각 없음", 회의 · 일정은 시작~끝', () => {
  assert.equal(shortTime(item({ timeStated: false })), '');
  assert.equal(timeRange(item({ timeStated: false })), '시각 없음');
  assert.equal(timeRange(item({ kind: 'meeting', endMs: at('2026-11-12T15:30:00+09:00') })), '14:00~15:30');
  assert.equal(timeRange(item({ kind: 'due', endMs: null })), '14:00');
  assert.equal(dayTitle({ key: '2026-11-12', weekday: 4 }), '11월 12일 (목)');
});

test('날짜별 묶기는 KST 날짜로: 11/12 23:30과 11/13 00:10은 다른 날', () => {
  const m = byDay([item({ startMs: at('2026-11-12T23:30:00+09:00') }), item({ startMs: at('2026-11-13T00:10:00+09:00') })]);
  assert.deepEqual([...m.keys()], ['2026-11-12', '2026-11-13']);
});

test('회의 넣기 버튼: 시각이 적힌 회의만', () => {
  assert.equal(canAddMeeting(item({ kind: 'meeting', mailId: 9 as never })), true);
  assert.equal(canAddMeeting(item({ kind: 'meeting', mailId: 9 as never, timeStated: false })), false);
  assert.equal(canAddMeeting(item({ kind: 'due', mailId: 9 as never })), false);
});

// ── 모의 캘린더(BE-15 흉내) ──

const status = (code: number) => (e: unknown) => (e as { status?: number }).status === code;
const mock = () => createMockApi({ latencyMs: 0, agentDelayMs: { rule: 0, model: 0 } });

test('모의: 11월 달력 → 미처리 기한 · 회의 2건, 기간 밖 · 거꾸로 · 62일 넘김은 422', async () => {
  const api = mock();
  const r = await api.getCalendar('2026-11-01', '2026-12-12');
  const kinds = new Set(r.items.map((i) => i.kind));
  assert.ok(kinds.has('due') && kinds.has('meeting'));
  assert.equal(r.items.filter((i) => i.kind === 'meeting').length, 2);
  assert.ok(r.items.every((a, i, xs) => i === 0 || xs[i - 1]!.startMs <= a.startMs)); // 시각 순
  await assert.rejects(api.getCalendar('2026-11-12', '2026-11-01'), status(422));
  await assert.rejects(api.getCalendar('2026-11-01', '2027-01-15'), status(422));
});

test('모의: 회의를 캘린더에 넣기 → 회의 대신 일정 하나, 같은 메일 또 넣기 409, 되돌리기 → 회의로 돌아옴', async () => {
  const api = mock();
  const meeting = (await api.getCalendar('2026-11-01', '2026-11-30')).items.find((i) => i.kind === 'meeting' && i.mailId === 9)!;
  const added = await api.addCalendarEvent({ startMs: meeting.startMs, endMs: meeting.endMs, mailId: meeting.mailId });
  assert.equal(added.item.title, '고객사 정기 미팅');
  let items = (await api.getCalendar('2026-11-01', '2026-11-30')).items.filter((i) => i.mailId === 9 && i.kind !== 'due');
  assert.deepEqual(items.map((i) => i.kind), ['event']);
  await assert.rejects(api.addCalendarEvent({ startMs: meeting.startMs, mailId: meeting.mailId }), status(409));
  await api.undoAction(added.actionId);
  items = (await api.getCalendar('2026-11-01', '2026-11-30')).items.filter((i) => i.mailId === 9 && i.kind !== 'due');
  assert.deepEqual(items.map((i) => i.kind), ['meeting']);
});

test('모의: 일정 빼기 → 사라짐 → 되돌리기 → 돌아옴. 끝 시각이 없으면 1시간, 기록 탭에 문장', async () => {
  const api = mock();
  const start = at('2026-11-20T10:00:00+09:00');
  const added = await api.addCalendarEvent({ startMs: start, title: '예산 회의' });
  assert.equal(added.item.endMs, start + 3600_000);
  const removed = await api.removeCalendarEvent(added.item.eventId!);
  assert.equal((await api.getCalendar('2026-11-20', '2026-11-20')).items.filter((i) => i.kind === 'event').length, 0);
  await assert.rejects(api.removeCalendarEvent(added.item.eventId!), status(404));
  await api.undoAction(removed.actionId);
  assert.equal((await api.getCalendar('2026-11-20', '2026-11-20')).items.filter((i) => i.kind === 'event').length, 1);
  const texts = (await api.getActionHistory(7)).items.map((i) => i.text);
  assert.ok(texts.includes("캘린더에 11/20 10:00 '예산 회의'을(를) 넣었어요"));
});

test('모의: 나중에로 미룬 업무 → 다시 알릴 시각에 "다시 알림"으로 보임', async () => {
  const api = mock();
  const due = (await api.getCalendar('2026-11-01', '2026-11-30')).items.find((i) => i.kind === 'due')!;
  const until = at('2026-11-24T09:00:00+09:00');
  await api.patchTaskStatus(due.taskId!, { status: 'snoozed', snoozedUntilMs: until });
  const items = (await api.getCalendar('2026-11-01', '2026-11-30')).items.filter((i) => i.taskId === due.taskId);
  assert.deepEqual(items.map((i) => [i.kind, i.startMs]), [['snoozed', until]]);
});
