// 캘린더 화면 계산(FE-12 · D56). 모든 날짜는 KST 기준이다(deadline.ts와 같은 고정 +9시간).
// 달력은 일요일부터 시작하는 6주(42칸) 고정 — 달마다 높이가 바뀌어 화면이 출렁이지 않게.
import type { CalendarItem, CalendarKind } from '../../api/contract.ts';
import { kstDayNumber, kstDayStartMs, kstWeekday } from '../tasks/deadline.ts';

export const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'] as const;

/** 화면에 보이는 종류 이름. 색이 아니라 글자로 구분한다(색 신호는 하나만, design_system) */
export const KIND_LABEL: Record<CalendarKind, string> = { event: '일정', meeting: '회의', due: '기한', snoozed: '다시 알림' };

export interface Month {
  year: number;
  month: number; // 1~12
}

export interface DayCell {
  key: string; // 'YYYY-MM-DD'
  day: number; // KST 날짜 번호(deadline.kstDayNumber)
  date: number; // 1~31
  weekday: number; // 0 = 일요일
  inMonth: boolean;
}

const pad = (n: number) => String(n).padStart(2, '0');

/** KST 날짜 번호 → 'YYYY-MM-DD' */
export function dayKey(day: number): string {
  return new Date(kstDayStartMs(day) + 9 * 3600_000).toISOString().slice(0, 10);
}

export const keyOfMs = (ms: number) => dayKey(kstDayNumber(ms));

export function monthOf(ms: number): Month {
  const [y, m] = keyOfMs(ms).split('-').map(Number) as [number, number];
  return { year: y, month: m };
}

export function shiftMonth({ year, month }: Month, by: number): Month {
  const i = year * 12 + (month - 1) + by;
  return { year: Math.floor(i / 12), month: (i % 12) + 1 };
}

export const monthTitle = ({ year, month }: Month) => `${year}년 ${month}월`;

/** 그 달 1일이 있는 주의 일요일부터 6주 */
export function monthGrid(m: Month): DayCell[] {
  const first = kstDayNumber(Date.parse(`${m.year}-${pad(m.month)}-01T00:00:00+09:00`));
  const start = first - kstWeekday(first);
  return Array.from({ length: 42 }, (_, i) => {
    const day = start + i;
    const key = dayKey(day);
    return { key, day, date: Number(key.slice(8)), weekday: kstWeekday(day), inMonth: Number(key.slice(5, 7)) === m.month };
  });
}

/** 조회 기간(달력에 보이는 첫 칸 ~ 마지막 칸). 42일이라 서버 한도(62일) 안이다 */
export function gridRange(cells: readonly DayCell[]): { start: string; end: string } {
  return { start: cells[0]!.key, end: cells[cells.length - 1]!.key };
}

/** 날짜별로 묶는다. 여러 날에 걸친 일정도 시작한 날에만 둔다(앱 일정은 대부분 한두 시간이다) */
export function byDay(items: readonly CalendarItem[]): Map<string, CalendarItem[]> {
  const out = new Map<string, CalendarItem[]>();
  for (const it of items) {
    const k = keyOfMs(it.startMs);
    const list = out.get(k);
    if (list) list.push(it);
    else out.set(k, [it]);
  }
  return out;
}

const hhmm = (ms: number) => new Date(ms + 9 * 3600_000).toISOString().slice(11, 16);

/** 칸 안 짧은 시각. 메일에 시각이 없던 것은 비운다(지어낸 18:00을 보이지 않는다) */
export function shortTime(it: CalendarItem): string {
  return it.timeStated ? hhmm(it.startMs) : '';
}

/** 그날 목록의 시각 칸: '14:00~15:30' · '18:00' · '시각 없음' */
export function timeRange(it: CalendarItem): string {
  if (!it.timeStated) return '시각 없음';
  return it.endMs !== null && (it.kind === 'event' || it.kind === 'meeting') ? `${hhmm(it.startMs)}~${hhmm(it.endMs)}` : hhmm(it.startMs);
}

/** 그날 목록 머리: '11월 12일 (목)' */
export function dayTitle(cell: Pick<DayCell, 'key' | 'weekday'>): string {
  const [, m, d] = cell.key.split('-').map(Number);
  return `${m}월 ${d}일 (${WEEKDAYS[cell.weekday]})`;
}

/** 회의를 캘린더에 넣을 수 있나: 시각이 메일에 적힌 회의만(시각을 지어내지 않는다, D50) */
export const canAddMeeting = (it: CalendarItem) => it.kind === 'meeting' && it.timeStated && it.mailId !== null;
