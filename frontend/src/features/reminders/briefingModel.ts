// 브리핑 · 회고 메뉴의 판단 (FE-16 · 명세 4.3절). 순수 함수, node --test 대상.
// 브리핑은 무엇이 있는지만 알린다. 할 일을 권하는 문장("~부터 챙기세요")을 만들지 않는다(AI-D18) — 이 파일의 글자도 사실만 말한다.
import type { Briefing, BriefingKind } from '../../api/contract.ts';
import { formatKstShort } from '../../lib/snooze.ts';

const DAY_MS = 86_400_000;
const KST_MS = 9 * 3_600_000;
const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'] as const;

export const BRIEFING_LABEL: Record<BriefingKind, string> = { morning: '아침 브리핑', evening: '퇴근 회고', weekly: '주간 회고' };

/** 메뉴 둘째 줄: 언제 만드나(기본 설정 기준, 명세 4.3절) */
export const BRIEFING_WHEN: Record<BriefingKind, string> = { morning: '매일 08:30', evening: '매일 17:30', weekly: '금요일 17:30' };

/** epoch 밀리초 → 한국 날짜 YYYY-MM-DD */
export function kstDate(ms: number): string {
  return new Date(ms + KST_MS).toISOString().slice(0, 10);
}

/** YYYY-MM-DD에서 n일 옮기기 */
export function shiftDate(date: string, days: number): string {
  return new Date(Date.parse(`${date}T00:00:00Z`) + days * DAY_MS).toISOString().slice(0, 10);
}

/** 예: 11/6(금) */
export function dateLabel(date: string): string {
  const d = new Date(`${date}T00:00:00Z`);
  return `${d.getUTCMonth() + 1}/${d.getUTCDate()}(${WEEKDAYS[d.getUTCDay()]})`;
}

/** 그 날이 든 주(월 ~ 금): 11/2(월) ~ 11/6(금) */
export function weekRange(date: string): string {
  const wd = new Date(`${date}T00:00:00Z`).getUTCDay();
  const monday = shiftDate(date, -((wd + 6) % 7));
  return `${dateLabel(monday)} ~ ${dateLabel(shiftDate(monday, 4))}`;
}

/** ‹ › 날짜 옮기기: 아침 · 퇴근은 하루, 주간은 7일. 오늘을 넘지 않는다(하루씩 옮긴 뒤 주간에서 다음 주를 누르면 미래로 가던 것) */
export function stepBriefingDate(date: string, kind: BriefingKind, dir: -1 | 1, today: string): string {
  const next = shiftDate(date, dir * (kind === 'weekly' ? 7 : 1));
  return next > today ? today : next;
}

/** 받침에 맞는 조사(은/는 · 이/가) */
export function josa(word: string, withFinal: string, withoutFinal: string): string {
  const code = word.charCodeAt(word.length - 1) - 0xac00;
  const hasFinal = code >= 0 && code <= 11171 && code % 28 !== 0;
  return `${word}${hasFinal ? withFinal : withoutFinal}`;
}

/**
 * 내용 대신 보일 한 줄(내용을 보여도 되면 null). 만든 시각(generatedAtMs)이 있고 내용이 있으면 그대로 보인다.
 * - 아직 만들 시각이 아니면 언제 만드는지. 서버가 답한 시각(as_of)이 있으면 그것으로 판단한다 — BE-12는 요청할 때 만들어서
 *   예정 시각 전에 불러도 지금까지의 내용을 보내는데, 그때 어댑터가 generatedAtMs를 비워 두므로 내용이 와도 여기로 온다.
 *   서버 시각이 없으면 화면 시계(nowMs)로
 * - 만들었는데 없으면 없었다고, 기록이 없으면 없다고
 */
export function briefingEmptyText(
  b: Pick<Briefing, 'kind' | 'generatedAtMs' | 'scheduledAtMs' | 'sections'> & { asOfMs?: number | null },
  nowMs: number,
): string | null {
  if (b.generatedAtMs !== null && b.sections.length > 0) return null;
  const name = BRIEFING_LABEL[b.kind];
  const now = b.asOfMs ?? nowMs;
  if (b.scheduledAtMs !== null && b.scheduledAtMs > now) return `아직 만들 시각이 아니에요. ${josa(name, '은', '는')} ${formatKstShort(b.scheduledAtMs)}에 만들어요.`;
  if (b.generatedAtMs !== null) return `${name}에 담을 것이 없었어요.`;
  return `이날 만든 ${josa(name, '이', '가')} 없어요.`;
}

/** 줄 버튼: 퇴근 회고의 '남은 일'만 [내일 아침으로 미루기](아직 끝나지 않은 업무일 때) */
export function canSnoozeToMorning(sectionId: string, taskStatus: string | undefined): boolean {
  return sectionId === 'remaining' && (taskStatus === 'pending' || taskStatus === 'snoozed');
}
