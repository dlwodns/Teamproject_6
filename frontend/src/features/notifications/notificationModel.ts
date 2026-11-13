// 알림 센터 🔔의 판단 (FE-10 · FE-16 · 명세 6절). 순수 함수, node --test 대상.
// 팝업은 "지금 새로 온 것"만 보이고, 전체는 에이전트 화면 리마인더 메뉴가 맡는다(UX-D19).
// - 🔔 숫자 = 아직 읽지 않은 리마인더 알림 수(10 이상 9+). 리마인더가 아닌 알림(새 업무 · 에이전트 작업 완료)은 세지 않는다
// - 탭 [리마인더 | 알림], 묶음 칩은 건수가 있는 묶음만, 한 줄에 넘치면 마지막 칩이 › 전체 보기
// - 줄은 최대 5개, 줄을 누르면 에이전트 화면에서 그 항목이 열린다
import { REMINDER_GROUPS, type AppNotification, type ReminderGroup } from '../../api/contract.ts';

/** 리마인더 알림인가: 묶음 칸이 있거나, 종류가 리마인더 · 묶음 알림 · 답장 후 완료 확인(정리 제안 묶음)이면 */
export function isReminderNotification(n: Pick<AppNotification, 'kind' | 'group'>): boolean {
  return (n.group !== undefined && n.group !== null) || n.kind === 'reminder' || n.kind === 'digest' || n.kind === 'reply_confirm';
}

/** 최근 것부터 */
const byNewest = <T extends { createdAtMs: number }>(list: readonly T[]) => [...list].sort((a, b) => b.createdAtMs - a.createdAtMs);

export function splitNotifications(list: readonly AppNotification[]): { reminders: AppNotification[]; others: AppNotification[] } {
  return { reminders: byNewest(list.filter(isReminderNotification)), others: byNewest(list.filter((n) => !isReminderNotification(n))) };
}

export function unreadReminderCount(list: readonly AppNotification[]): number {
  return list.filter((n) => isReminderNotification(n) && n.readAtMs === null).length;
}

/** 🔔 버튼 이름(숫자는 배지가 아니라 이름으로 읽힌다) */
export function bellLabel(unread: number | null): string {
  return unread ? `알림 센터 열기, 읽지 않은 리마인더 ${unread}개` : '알림 센터 열기';
}

export type ChipFilter = ReminderGroup | 'all';

/** 묶음 칩: 건수가 있는 묶음만 정해진 순서로. max개를 넘으면 앞 max − 1개만 두고 마지막 자리를 '전체 보기 ›'로 */
export function groupChips(rows: readonly Pick<AppNotification, 'group'>[], max = 4): { chips: { group: ReminderGroup; count: number }[]; overflow: boolean } {
  const all = REMINDER_GROUPS.map((group) => ({ group, count: rows.filter((r) => r.group === group).length })).filter((c) => c.count > 0);
  if (all.length <= max) return { chips: all, overflow: false };
  return { chips: all.slice(0, max - 1), overflow: true };
}

export const POPOVER_ROWS = 5;

export function popoverRows<T extends Pick<AppNotification, 'group'>>(rows: readonly T[], filter: ChipFilter, limit = POPOVER_ROWS): { rows: T[]; more: number } {
  const hit = filter === 'all' ? [...rows] : rows.filter((r) => r.group === filter);
  return { rows: hit.slice(0, limit), more: Math.max(0, hit.length - limit) };
}

/** 줄을 눌렀을 때 갈 곳: 항목 키가 있으면 에이전트 화면의 그 항목, 아침 묶음 알림이면 브리핑, 그 밖에는 리마인더 전체 */
export function notificationTarget(n: Pick<AppNotification, 'reminderKey' | 'group' | 'rule' | 'kind'>): { kind: 'reminder'; key: string } | { kind: 'briefing' } | { kind: 'reminders' } {
  if (n.reminderKey) return { kind: 'reminder', key: n.reminderKey };
  if (n.kind === 'digest' || n.rule === 'R-아침') return { kind: 'briefing' };
  return { kind: 'reminders' };
}

/** 처음 받은 뒤 새로 생긴 안 읽은 리마인더 알림(리마인더 토스트 대상). 처음 받은 목록은 토스트를 띄우지 않는다 */
export function newReminderNotifications(seen: ReadonlySet<number> | null, list: readonly AppNotification[]): AppNotification[] {
  if (seen === null) return [];
  return list.filter((n) => !seen.has(n.id) && n.readAtMs === null && isReminderNotification(n));
}
