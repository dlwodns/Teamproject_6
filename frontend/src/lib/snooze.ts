// '나중에' 시각 계산 (components.md 3절 Menu · design_system 5절). 모든 시각은 KST.
// 한국은 일광 절약 시간이 없어 epoch 밀리초에 +9시간 고정 오프셋으로 날짜 · 요일을 구한다.
// 실행 환경의 시간대(TZ)와 무관하게 같은 결과가 나온다.
//
// 규칙
// - 1시간 뒤: 지금 + 60분.
// - 오늘 오후 4시: 지금이 KST 15:00 전일 때만 보인다. 15:00 이후면 16:00까지 1시간이 안 남아
//   '1시간 뒤'보다 이르거나 거의 같으므로 뺀다(같은 뜻의 선택지 두 개를 보이지 않기 위해).
// - 내일 아침 08:30: 다음 KST 날짜 08:30.
// - 다음 주 월요일 09:00: 오늘 이후 처음 오는 월요일 09:00. 오늘이 월요일이면 7일 뒤, 일요일이면 다음 날.
// - '직접 고르기'(날짜 + 시각 입력)는 화면 부품이 따로 둔다.

const HOUR_MS = 60 * 60 * 1000;
const DAY_MS = 24 * HOUR_MS;
const KST_OFFSET_MS = 9 * HOUR_MS;
const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'] as const;

export type SnoozeKey = 'in-1h' | 'today-16' | 'tomorrow-0830' | 'next-monday-09';

export interface SnoozeOption {
  key: SnoozeKey;
  /** 메뉴에 보이는 이름 */
  label: string;
  /** 실제 시각 표시(예: 11/7(토) 08:30), 메뉴 오른쪽 보조 글자 · 화면 읽기용 */
  detail: string;
  /** 다시 보일 시각(epoch 밀리초) */
  untilMs: number;
}

/** KST 날짜 번호(1970-01-01 KST = 0) */
function kstDay(ms: number): number {
  return Math.floor((ms + KST_OFFSET_MS) / DAY_MS);
}

/** KST 날짜 번호 + 시 · 분 → epoch 밀리초 */
function kstAt(day: number, hour: number, minute: number): number {
  return day * DAY_MS - KST_OFFSET_MS + hour * HOUR_MS + minute * 60 * 1000;
}

/** 0 = 일요일 … 6 = 토요일 (1970-01-01은 목요일) */
function kstWeekday(day: number): number {
  return (((day + 4) % 7) + 7) % 7;
}

const pad = (n: number) => String(n).padStart(2, '0');

/** 예: 11/7(토) 08:30 */
export function formatKstShort(ms: number): string {
  const d = new Date(ms + KST_OFFSET_MS); // UTC 필드를 KST 값으로 읽는다
  const wd = WEEKDAYS[d.getUTCDay()] ?? '';
  return `${d.getUTCMonth() + 1}/${d.getUTCDate()}(${wd}) ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

export function snoozeOptions(nowMs: number): SnoozeOption[] {
  const today = kstDay(nowMs);
  const options: SnoozeOption[] = [];
  const push = (key: SnoozeKey, label: string, untilMs: number) => options.push({ key, label, detail: formatKstShort(untilMs), untilMs });

  push('in-1h', '1시간 뒤', nowMs + HOUR_MS);
  if (nowMs < kstAt(today, 15, 0)) push('today-16', '오늘 오후 4시', kstAt(today, 16, 0));
  push('tomorrow-0830', '내일 아침 08:30', kstAt(today + 1, 8, 30));
  const daysToMonday = (8 - kstWeekday(today)) % 7 || 7;
  push('next-monday-09', '다음 주 월요일 09:00', kstAt(today + daysToMonday, 9, 0));
  return options;
}
