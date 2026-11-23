// 기한 판정 (FE-1 모의 데이터 기준 · FE와 BE가 합의한 규칙 아님, BE-3 연결 때 맞출 계약)
// - 기한 지남: due_at < 기준 시각
// - 오늘 마감(기한 남음): 기준 시각과 같은 KST 날짜이고 due_at >= 기준 시각 (마감 정각은 아직 남음)
// - 내일: 기준 시각 다음 KST 날짜
// - 기한 유무는 due_at으로만 판단한다(due_source가 none이어도 due_at이 있을 수 있다)
// 날짜는 epoch 밀리초에 +9시간을 더해 계산한다. 한국은 일광 절약 시간이 없어 고정 오프셋이 맞고,
// 브라우저 · 실행 환경 시간대(TZ)와 무관하게 같은 결과가 나온다.

const KST_OFFSET_MS = 9 * 60 * 60 * 1000;
const DAY_MS = 24 * 60 * 60 * 1000;

export type DueState = 'none' | 'overdue' | 'today' | 'tomorrow' | 'later';

/** KST 기준 날짜 번호(1970-01-01 KST = 0). */
export function kstDayNumber(ms: number): number {
  return Math.floor((ms + KST_OFFSET_MS) / DAY_MS);
}

export function dueState(dueAtMs: number | null, asOfMs: number): DueState {
  if (dueAtMs === null) return 'none';
  if (dueAtMs < asOfMs) return 'overdue';
  const days = kstDayNumber(dueAtMs) - kstDayNumber(asOfMs);
  if (days === 0) return 'today';
  if (days === 1) return 'tomorrow';
  return 'later';
}

const kstFormat = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  month: 'numeric',
  day: 'numeric',
  weekday: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});

const kstTime = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});

const kstFull = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  weekday: 'short',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
});

const kstFullDate = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit', weekday: 'short' });

const kstShortDate = new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', month: 'numeric', day: 'numeric', weekday: 'short' });

/** 예: 11/10(화) — 기한 라벨용 짧은 날짜(UX-D10) */
export function formatKstShortDate(ms: number): string {
  const parts = Object.fromEntries(kstShortDate.formatToParts(ms).map((p) => [p.type, p.value]));
  return `${parts.month}/${parts.day}(${parts.weekday})`;
}

/** 예: 10. 21. (수) 18:00 */
export const formatKstDateTime = (ms: number): string => kstFormat.format(ms);
/** 예: 18:00 */
export const formatKstTime = (ms: number): string => kstTime.format(ms);
/** 예: 2026. 10. 20. (화) 09:00 */
export const formatKstFull = (ms: number): string => kstFull.format(ms);

export interface DueLabel {
  state: DueState;
  /** 화면에 보이는 짧은 라벨 (UX-D10): D+2 · 오늘 18:00 · 내일 12:00 · 11/10(화) · 기한 없음 */
  text: string;
  /** 기한 전체 시각(화면 읽기 · 말풍선용). 기한 없음이면 null */
  full: string | null;
}

/**
 * 기한 라벨 (UX-D10). ⚠ · '기한 지남' 같은 말은 붙이지 않고 글자 자체가 상태를 말한다.
 * - 기한 지남: D+N (N = 기준 시각 KST 날짜 − 기한 KST 날짜, 같은 날 지났으면 D+0)
 * - 오늘: 오늘 HH:MM · 내일: 내일 HH:MM · 그 뒤: M/D(요일) · 없음: 기한 없음
 * - 시각이 메일에 없던 기한(timeStated false, 18:00 같은 기본값)은 날짜만: 오늘 · 내일, 말풍선도 날짜까지(11-20 결정).
 *   null · undefined(옛 업무 · 사용자가 바꾼 기한 · 모의)는 모른다는 뜻이라 지금처럼 시각까지 보인다.
 */
export function dueLabel(dueAtMs: number | null, asOfMs: number, timeStated?: boolean | null): DueLabel {
  const state = dueState(dueAtMs, asOfMs);
  if (dueAtMs === null) return { state, text: '기한 없음', full: null };
  const dateOnly = timeStated === false;
  const full = dateOnly ? kstFullDate.format(dueAtMs) : formatKstFull(dueAtMs);
  const at = dateOnly ? '' : ` ${formatKstTime(dueAtMs)}`;
  switch (state) {
    case 'overdue':
      return { state, text: `D+${kstDayNumber(asOfMs) - kstDayNumber(dueAtMs)}`, full };
    case 'today':
      return { state, text: `오늘${at}`, full };
    case 'tomorrow':
      return { state, text: `내일${at}`, full };
    default:
      return { state, text: formatKstShortDate(dueAtMs), full };
  }
}

// ── v3.1 대시보드 · 메일 공용 (FE-3) — 위 함수들은 그대로 두고 새 이름으로 더한다 ──

/** KST 날짜 번호의 0시(epoch 밀리초). kstDayNumber의 반대 */
export function kstDayStartMs(day: number): number {
  return day * DAY_MS - KST_OFFSET_MS;
}

/** KST 요일(0 = 일요일 … 6 = 토요일). 1970-01-01은 목요일 */
export function kstWeekday(day: number): number {
  return (((day + 4) % 7) + 7) % 7;
}

/** 그 날이 든 주의 월요일 날짜 번호 */
export function kstMondayOf(day: number): number {
  return day - ((kstWeekday(day) + 6) % 7);
}

/** 예: 11/5(목) — KST 날짜 번호로 */
export function formatKstDay(day: number): string {
  return formatKstShortDate(kstDayStartMs(day));
}

/**
 * ASAP 업무인가(AI-D11): 시각이 없고(due_at 비움) 원문 기한이 'ASAP'일 때만.
 * dueRaw가 아예 오지 않으면(undefined) ASAP를 지어내지 않는다.
 */
export function isAsap(dueAtMs: number | null, dueRaw: string | null | undefined): boolean {
  return dueAtMs === null && typeof dueRaw === 'string' && dueRaw.trim().toUpperCase() === 'ASAP';
}

/** 화면 DueLabel의 종류(ui/DueLabel의 DueKind 중 업무 줄에 쓰는 넷) */
export type TaskDueKind = 'urgent' | 'today' | 'later' | 'none';

export interface TaskDueBadge {
  /** overdue · asap · today · tomorrow · later · raw(시각 모르는 원문 기한) · none */
  state: DueState | 'asap' | 'raw';
  kind: TaskDueKind;
  text: string;
  /** 화면 읽기용으로 덧붙일 글자 */
  srText: string | null;
  /** 말풍선 전체 시각. 기한 시각이 없으면 null */
  fullTime: string | null;
}

const BADGE_KIND: Record<DueState, TaskDueKind> = { overdue: 'urgent', today: 'today', tomorrow: 'later', later: 'later', none: 'none' };

/**
 * 업무 줄 기한 라벨(UX-D10 · UX-D20 · wireframe 13-2): D+N(빨강) · ASAP(빨강) · 오늘 HH:MM(초록) · 내일 HH:MM · M/D(요일)(파랑) · 기한 없음(회색).
 * D+N은 KST 달력 날짜 차이이고 같은 날 지났으면 D+0. due_at 없이 원문 기한만 있으면(예: '미팅 전에') 날짜를 모르므로
 * 정해진 문구 '기한 없음'을 보이고 원문은 말풍선 · 화면 읽기로 준다(11-20 결정).
 */
export function taskDueBadge(dueAtMs: number | null, dueRaw: string | null | undefined, asOfMs: number, timeStated?: boolean | null): TaskDueBadge {
  if (isAsap(dueAtMs, dueRaw)) return { state: 'asap', kind: 'urgent', text: 'ASAP', srText: '즉시 처리', fullTime: null };
  if (dueAtMs === null) {
    const raw = typeof dueRaw === 'string' ? dueRaw.trim() : '';
    if (raw) return { state: 'raw', kind: 'none', text: '기한 없음', srText: `메일 속 기한 ${raw}`, fullTime: `메일 속 기한: ${raw}` };
    return { state: 'none', kind: 'none', text: '기한 없음', srText: null, fullTime: null };
  }
  const label = dueLabel(dueAtMs, asOfMs, timeStated);
  const full = label.full;
  return {
    state: label.state,
    kind: BADGE_KIND[label.state],
    text: label.text,
    srText: full === null ? null : label.state === 'overdue' ? `기한 지남 · ${full}` : full,
    fullTime: full,
  };
}
