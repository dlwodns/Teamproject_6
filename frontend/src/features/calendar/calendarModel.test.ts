// 캘린더 화면 계산(FE-12) · 모의 캘린더(BE-15 흉내) 시험. 입력 → 기대 결과.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { CalendarItem } from '../../api/contract.ts';
import { createMockApi } from '../../api/mockClient.ts';
import { drawableActions } from '../reminders/reminderModel.ts';
import { addRequestOf, byDay, calendarDayPath, canAddMeeting, dayParamOf, dayTitle, gridRange, monthGrid, monthOf, monthOfKey, shiftMonth, shortTime, timeRange } from './calendarModel.ts';

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
  const added = await api.addCalendarEvent(addRequestOf(meeting)); // 화면이 보내는 요청 그대로
  assert.equal(added.item.title, '고객사 정기 미팅');
  let items = (await api.getCalendar('2026-11-01', '2026-11-30')).items.filter((i) => i.mailId === 9 && i.kind !== 'due');
  assert.deepEqual(items.map((i) => i.kind), ['event']);
  await assert.rejects(api.addCalendarEvent({ startMs: meeting.startMs, mailId: meeting.mailId }), status(409));
  await api.undoAction(added.actionId);
  items = (await api.getCalendar('2026-11-01', '2026-11-30')).items.filter((i) => i.mailId === 9 && i.kind !== 'due');
  assert.deepEqual(items.map((i) => i.kind), ['meeting']);
});

test('일정 넣기 제목: 화면은 회의 이름을 보내고, 제목 없이 넣으면 BE-15처럼 메일 제목(#75 리뷰)', async () => {
  const api = mock();
  const meeting = (await api.getCalendar('2026-11-01', '2026-11-30')).items.find((i) => i.kind === 'meeting' && i.mailId === 9)!;
  assert.equal(addRequestOf(meeting).title, '고객사 정기 미팅');
  const bare = await api.addCalendarEvent({ startMs: meeting.startMs, mailId: meeting.mailId });
  assert.ok(meeting.subject && meeting.subject !== '고객사 정기 미팅');
  assert.equal(bare.item.title, meeting.subject);
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

// ── 날짜를 주소로 받기: 리마인더 [당일 업무 보기](T13 start = end) → /calendar?day=YYYY-MM-DD ──

test('날짜 주소: 있는 날만 받는다. 형식이 틀리거나 없는 날이면 null(화면은 기본 보기, 넓히지 않는다)', () => {
  assert.equal(calendarDayPath('2026-11-13'), '/calendar?day=2026-11-13');
  assert.equal(dayParamOf(new URLSearchParams('day=2026-11-13')), '2026-11-13');
  assert.equal(dayParamOf(new URLSearchParams('day=2028-02-29')), '2028-02-29');
  for (const bad of ['', 'day=', 'day=2026-11-6', 'day=2026-13-01', 'day=2026-02-30', 'day=2027-02-29', 'day=abc', 'day=2026-11-13T00:00']) {
    assert.equal(dayParamOf(new URLSearchParams(bad)), null, bad);
  }
});

test('고른 날의 달: 그 달 달력에 그날 칸이 있다(없으면 화면이 오늘로 돌아간다). 달 첫날 · 마지막 날도', () => {
  for (const key of ['2026-11-13', '2026-11-01', '2026-11-30', '2026-12-31', '2027-01-01']) {
    const m = monthOfKey(key);
    const cell = monthGrid(m).find((c) => c.key === key);
    assert.ok(cell?.inMonth, key);
  }
  assert.deepEqual(monthOfKey('2026-12-31'), { year: 2026, month: 12 });
});

test('그날 목록은 KST 하루 [00:00, 다음 날 00:00): 앞뒤 날 · UTC로 적힌 다음 날 0시는 빠진다. 없는 날은 빈 목록', () => {
  const at13 = [
    item({ taskId: 1 as never, startMs: at('2026-11-12T23:59:59+09:00') }),
    item({ taskId: 2 as never, startMs: at('2026-11-13T00:00:00+09:00') }),
    item({ taskId: 3 as never, startMs: at('2026-11-13T23:59:59+09:00') }),
    item({ taskId: 4 as never, startMs: at('2026-11-13T15:00:00Z') }), // = 11/14 00:00 KST
    item({ taskId: 5 as never, startMs: at('2026-11-12T15:00:00Z') }), // = 11/13 00:00 KST
    item({ taskId: 6 as never, startMs: at('2026-11-14T00:00:00+09:00') }),
  ];
  const days = byDay(at13);
  assert.deepEqual((days.get('2026-11-13') ?? []).map((i) => i.taskId), [2, 3, 5]);
  assert.deepEqual(days.get('2026-11-15') ?? [], []);
});

test('모의 연결: 기한 몰림 [당일 업무 보기] → 그날 캘린더에 그 업무들이 있고, 다른 날 업무는 없다', async () => {
  const api = mock();
  const list = await api.getReminders('all');
  const cluster = list.items.find((i) => i.type === 'due_cluster')!;
  const open = drawableActions(cluster, { mailTarget: () => null, mode: 'mock' }).find((d) => d.action.action === 'T13');
  assert.ok(open, '모의 데이터도 T13 버튼이 그려진다');
  assert.equal(open.plan.type, 'route');
  const to = (open.plan as { to: string }).to;
  const day = dayParamOf(new URLSearchParams(to.split('?')[1]));
  assert.ok(day);
  const cells = monthGrid(monthOfKey(day));
  const r = await api.getCalendar(cells[0]!.key, cells[cells.length - 1]!.key); // 캘린더 화면과 같은 조회(달력 42칸)
  const agenda = byDay(r.items).get(day) ?? [];
  const dueIds = agenda.filter((i) => i.kind === 'due').map((i) => i.taskId);
  for (const id of cluster.taskIds) assert.ok(dueIds.includes(id), `업무 ${id}가 그날 목록에 있다`);
  assert.ok(agenda.every((i) => byDay([i]).has(day)));
});
