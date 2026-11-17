// 모의 캘린더(BE-15 backend/app/services/calendar.py 흉내). 응답은 실제 서버와 같은 형식(provisional)으로 만든다.
// 규칙: 미처리 업무의 기한(due) · 나중에 다시 알림(snoozed) · 회의(meeting) · 넣은 일정(event)을 시각 순으로.
// 미처리 = pending, 또는 미뤘는데 다시 알릴 시각이 지난 업무(서버와 같은 기준). 지난 업무는 기한 날짜에 due로 보이고 snoozed는 빠진다.
// 기한이 없으면 보일 날짜가 없으므로 다시 알릴 시각이 지나도 snoozed를 남긴다(BE-D24 보완).
// 같은 메일로 넣은 일정이 있으면 그 회의는 일정 하나로만 보인다. 남의 업무 · 끝난 업무는 없다.
import { toKstIso } from '../adapter.ts';
import type { ProvisionalCalendarItem } from '../provisional.ts';

export const DEFAULT_EVENT_MS = 60 * 60_000; // 끝 시각이 없으면 1시간(D50)
export const MAX_RANGE_DAYS = 62;
const DAY_MS = 24 * 3600_000;

/**
 * 모의 전용 회의 2건. 시안 메일(9 · 21) 본문에는 회의 시각이 없어, 캘린더 화면을 보이려고 정한 값이다(실제 데이터 아님).
 * 모의에는 일정참석 업무가 없어 업무 id 없이 메일에만 붙인다.
 */
export const MOCK_MEETINGS = [
  { mailId: 9, title: '고객사 정기 미팅', startMs: Date.parse('2026-11-12T14:00:00+09:00'), endMs: Date.parse('2026-11-12T15:30:00+09:00') },
  { mailId: 21, title: 'AI 전환 실무 세미나', startMs: Date.parse('2026-11-18T15:00:00+09:00'), endMs: null },
] as const;

export interface MockEvent {
  id: number;
  title: string;
  startMs: number;
  endMs: number;
  mailId: number | null;
  taskId: number | null;
  deleted: boolean;
}

export interface MockCalendarInput {
  tasks: readonly { id: number; mail_id: number; text: string; status: string; due_at: string | null }[];
  snoozedUntil: (taskId: number) => number | null;
  subjects: ReadonlyMap<number, string>;
  events: readonly MockEvent[];
  /** 모의 서비스 시각(epoch 밀리초). 다시 알릴 시각이 지났는지 이 값으로 본다 */
  nowMs: number;
}

/** 'YYYY-MM-DD'(KST) → 그날 0시(epoch 밀리초). 형식이 아니면 null */
export function kstDayStart(day: string): number | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return null;
  const ms = Date.parse(`${day}T00:00:00+09:00`);
  return Number.isNaN(ms) ? null : ms;
}

/** 기간 검사. 문제가 있으면 422 문구, 없으면 [시작, 끝 다음 날 0시) */
export function checkRange(start: string, end: string): [number, number] | string {
  const lo = kstDayStart(start);
  const last = kstDayStart(end);
  if (lo === null || last === null) return '날짜는 YYYY-MM-DD';
  if (last < lo) return '끝 날짜가 시작 날짜보다 앞입니다';
  if ((last - lo) / DAY_MS + 1 > MAX_RANGE_DAYS) return `한 번에 ${MAX_RANGE_DAYS}일까지 볼 수 있습니다`;
  return [lo, last + DAY_MS];
}

export function calendarItems(input: MockCalendarInput, lo: number, hi: number): ProvisionalCalendarItem[] {
  const out: ProvisionalCalendarItem[] = [];
  const item = (x: Omit<ProvisionalCalendarItem, 'auto'>): ProvisionalCalendarItem => ({ ...x, auto: false });
  const live = input.events.filter((e) => !e.deleted);
  for (const e of live) {
    if (e.startMs < hi && e.endMs > lo) {
      out.push(item({ kind: 'event', title: e.title, start: toKstIso(e.startMs), end: toKstIso(e.endMs), time_stated: true,
        mail_id: e.mailId, task_id: e.taskId, event_id: e.id, subject: e.mailId === null ? null : (input.subjects.get(e.mailId) ?? null) }));
    }
  }
  const evented = new Set(live.map((e) => e.mailId).filter((m) => m !== null));
  for (const m of MOCK_MEETINGS) {
    if (evented.has(m.mailId) || m.startMs < lo || m.startMs >= hi) continue;
    out.push(item({ kind: 'meeting', title: m.title, start: toKstIso(m.startMs), end: toKstIso(m.endMs ?? m.startMs + DEFAULT_EVENT_MS),
      time_stated: true, mail_id: m.mailId, task_id: null, event_id: null, subject: input.subjects.get(m.mailId) ?? null }));
  }
  for (const t of input.tasks) {
    const subject = input.subjects.get(t.mail_id) ?? null;
    const until = t.status === 'snoozed' ? input.snoozedUntil(t.id) : null; // 처음 자료의 '나중에'는 시각을 몰라 빠진다
    const woke = until !== null && until <= input.nowMs; // 다시 알릴 시각이 지남 = 미처리
    if ((t.status === 'pending' || woke) && t.due_at) {
      const due = Date.parse(t.due_at);
      if (due >= lo && due < hi) {
        out.push(item({ kind: 'due', title: t.text, start: t.due_at, end: null, time_stated: true, mail_id: t.mail_id, task_id: t.id, event_id: null, subject }));
      }
    }
    if (until !== null && (!woke || !t.due_at) && until >= lo && until < hi) {
      out.push(item({ kind: 'snoozed', title: t.text, start: toKstIso(until), end: null, time_stated: true, mail_id: t.mail_id, task_id: t.id, event_id: null, subject }));
    }
  }
  const order = { event: 0, meeting: 1, due: 2, snoozed: 3 } as Record<string, number>;
  return out.sort((a, b) => Date.parse(a.start) - Date.parse(b.start) || order[a.kind]! - order[b.kind]! || (a.task_id ?? 0) - (b.task_id ?? 0));
}

