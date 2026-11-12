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
 * ASAP(due_at 없이 due_raw 'ASAP')는 지금 FE 계약에 due_raw가 없어 표시하지 않는다(BE-3 계약에 추가 필요).
 */
export function dueLabel(dueAtMs: number | null, asOfMs: number): DueLabel {
  const state = dueState(dueAtMs, asOfMs);
  if (dueAtMs === null) return { state, text: '기한 없음', full: null };
  const full = formatKstFull(dueAtMs);
  switch (state) {
    case 'overdue':
      return { state, text: `D+${kstDayNumber(asOfMs) - kstDayNumber(dueAtMs)}`, full };
    case 'today':
      return { state, text: `오늘 ${formatKstTime(dueAtMs)}`, full };
    case 'tomorrow':
      return { state, text: `내일 ${formatKstTime(dueAtMs)}`, full };
    default:
      return { state, text: formatKstShortDate(dueAtMs), full };
  }
}
