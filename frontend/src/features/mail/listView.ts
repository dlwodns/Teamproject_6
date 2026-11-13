// 메일 목록의 묶음 · 고정 · 읽음 · 여러 통 고르기 판단(FE-5d, Outlook에서 가져온 메일 관리 기능).
// 화면 부품은 이 결과를 그리기만 한다. 시각은 데이터 기준 시각(as_of) · KST로 판단한다(mailboxes.ts와 같은 규칙).
//
// 서버가 칸을 보내지 않으면 기능을 숨긴다(components.md 1절 6번):
//   readAtMs가 undefined인 메일만 있으면 읽음 · 안 읽음 동작을 숨기고, pinnedAtMs가 undefined면 고정을 숨긴다.
import type { DashboardSource, Mail, MailId } from '../../api/types.ts';
import { kstDayNumber } from '../tasks/deadline.ts';

// ── 고정 · 읽음 ──

/** 고정됨: 서버가 고정 시각을 보냈고 값이 있을 때 */
export const isPinned = (mail: Mail): boolean => typeof mail.pinnedAtMs === 'number';

/** 읽음 상태를 바꿀 수 있는가: 서버가 읽은 시각 칸을 보냈을 때만(null = 안 읽음, 숫자 = 읽음) */
export const supportsRead = (mail: Mail): boolean => mail.readAtMs !== undefined;

/** 고정을 쓸 수 있는가: 서버가 고정 칸을 보냈을 때만 */
export const supportsPin = (mail: Mail): boolean => mail.pinnedAtMs !== undefined;

export interface MailPatchView {
  read?: boolean;
  pinned?: boolean;
}

/**
 * 화면 먼저 바꾸기: 고른 메일의 읽음 · 고정 칸만 바꾼 새 원자료. 칸이 없는(서버가 안 보낸) 메일은 건드리지 않는다.
 * 이미 읽은 메일을 다시 읽음으로 하면 처음 읽은 시각을 그대로 둔다.
 */
export function withMailPatch(source: DashboardSource, ids: readonly MailId[], patch: MailPatchView, nowMs: number): DashboardSource {
  const set = new Set(ids);
  let changed = false;
  const mails = source.mails.map((m) => {
    if (!set.has(m.id)) return m;
    const next: Mail = { ...m };
    if (patch.read !== undefined && supportsRead(m)) next.readAtMs = patch.read ? (m.readAtMs ?? nowMs) : null;
    if (patch.pinned !== undefined && supportsPin(m)) next.pinnedAtMs = patch.pinned ? (m.pinnedAtMs ?? nowMs) : null;
    if (next.readAtMs === m.readAtMs && next.pinnedAtMs === m.pinnedAtMs) return m;
    changed = true;
    return next;
  });
  return changed ? { ...source, mails } : source;
}

/** 서버가 돌려준 메일로 캐시의 그 메일만 바꾼다 */
export function withMailsReplaced(source: DashboardSource, updated: readonly Mail[]): DashboardSource {
  const byId = new Map(updated.map((m) => [m.id, m]));
  return { ...source, mails: source.mails.map((m) => byId.get(m.id) ?? m) };
}

/** 실패하면 그 메일들만 바꾸기 전 값으로 돌린다(그사이 다른 변경은 지우지 않는다) */
export function restoreMails(current: DashboardSource, before: DashboardSource, ids: readonly MailId[]): DashboardSource {
  const set = new Set(ids);
  return withMailsReplaced(current, before.mails.filter((m) => set.has(m.id)));
}

// ── 날짜 묶음 ──

export type DateGroupKey = 'today' | 'yesterday' | 'thisWeek' | 'lastWeek' | 'older';
export type GroupKey = 'pinned' | DateGroupKey;

export const GROUP_LABELS: Record<GroupKey, string> = {
  pinned: '고정됨',
  today: '오늘',
  yesterday: '어제',
  thisWeek: '이번 주',
  lastWeek: '지난주',
  older: '이전',
};

/** KST 날짜 번호의 요일 차례: 월요일 = 0 … 일요일 = 6 (1970-01-01은 목요일) */
const mondayIndex = (day: number) => (((day + 3) % 7) + 7) % 7;

/**
 * 받은 시각의 묶음(KST, 주는 월요일 시작). 기준 시각보다 뒤(미래)는 오늘로 본다.
 * 어제가 지난주에 속해도(기준일이 월요일) '어제'가 먼저다.
 */
export function dateGroupOf(ms: number, asOfMs: number): DateGroupKey {
  const day = kstDayNumber(ms);
  const today = kstDayNumber(asOfMs);
  if (day >= today) return 'today';
  if (day === today - 1) return 'yesterday';
  const weekStart = today - mondayIndex(today);
  if (day >= weekStart) return 'thisWeek';
  if (day >= weekStart - 7) return 'lastWeek';
  return 'older';
}

export interface MailGroup {
  key: GroupKey;
  label: string;
  mails: Mail[];
}

const DATE_ORDER: DateGroupKey[] = ['today', 'yesterday', 'thisWeek', 'lastWeek', 'older'];

/**
 * 목록 묶음: 고정됨(있을 때만) → 오늘 → 어제 → 이번 주 → 지난주 → 이전. 빈 묶음은 뺀다.
 * 각 묶음 안은 받은 시각 최근 순(고정됨도 같다 — 고정한 차례로 섞이지 않게).
 */
export function groupMails(mails: readonly Mail[], asOfMs: number): MailGroup[] {
  const recent = (a: Mail, b: Mail) => b.receivedAtMs - a.receivedAtMs || b.id - a.id;
  const pinned = mails.filter(isPinned).sort(recent);
  const buckets = new Map<DateGroupKey, Mail[]>();
  for (const m of mails) {
    if (isPinned(m)) continue;
    const key = dateGroupOf(m.receivedAtMs, asOfMs);
    const list = buckets.get(key);
    if (list) list.push(m);
    else buckets.set(key, [m]);
  }
  const groups: MailGroup[] = [];
  if (pinned.length > 0) groups.push({ key: 'pinned', label: GROUP_LABELS.pinned, mails: pinned });
  for (const key of DATE_ORDER) {
    const list = buckets.get(key);
    if (list) groups.push({ key, label: GROUP_LABELS[key], mails: list.sort(recent) });
  }
  return groups;
}

/** 화면에 보이는 차례 그대로 편 목록(키보드 이동 · 다음/이전 메일 · 범위 고르기가 같은 차례를 쓴다) */
export const flattenGroups = (groups: readonly MailGroup[]): Mail[] => groups.flatMap((g) => g.mails);

/** 다음(+1) · 이전(-1) 메일. 고른 메일이 없으면 첫 메일, 끝에서는 그대로 */
export function stepMail(order: readonly Mail[], currentId: MailId | null, delta: 1 | -1): Mail | null {
  if (order.length === 0) return null;
  const i = currentId === null ? -1 : order.findIndex((m) => m.id === currentId);
  if (i < 0) return order[0]!;
  return order[Math.min(order.length - 1, Math.max(0, i + delta))]!;
}

// ── 메일함 안 읽음 수 ──

/** 안 읽은 메일 수. 읽음 칸이 하나도 없으면 undefined(모름 → 숫자를 숨긴다) */
export function unreadCount(mails: readonly Mail[]): number | undefined {
  if (!mails.some(supportsRead)) return undefined;
  return mails.filter((m) => m.readAtMs === null).length;
}

// ── 여러 통 고르기 ──

export interface Selection {
  ids: ReadonlySet<MailId>;
  /** Shift 범위의 시작(마지막으로 하나를 고르거나 푼 메일) */
  anchor: MailId | null;
}

export const EMPTY_SELECTION: Selection = { ids: new Set(), anchor: null };

export interface ClickMods {
  /** Shift: 기준 메일부터 이 메일까지 범위를 더한다 */
  range: boolean;
}

/**
 * 고르기 상자 · Ctrl/⌘ 누르기: 하나를 넣거나 뺀다(기준점이 된다).
 * Shift를 함께 누르면 기준점부터 이 메일까지 보이는 차례대로 더한다(Gmail · Outlook 체크 상자 방식, 기존 고른 것은 남긴다).
 */
export function toggleSelect(sel: Selection, order: readonly MailId[], id: MailId, mods: ClickMods = { range: false }): Selection {
  if (mods.range && sel.anchor !== null) {
    const a = order.indexOf(sel.anchor);
    const b = order.indexOf(id);
    if (a >= 0 && b >= 0) {
      const ids = new Set(sel.ids);
      for (let i = Math.min(a, b); i <= Math.max(a, b); i++) ids.add(order[i]!);
      return { ids, anchor: sel.anchor };
    }
  }
  const ids = new Set(sel.ids);
  if (ids.has(id)) ids.delete(id);
  else ids.add(id);
  return { ids, anchor: id };
}

/** 지금 목록에 없는 메일은 고른 것에서 뺀다(메일함을 바꾸거나 메일이 빠졌을 때) */
export function pruneSelection(sel: Selection, visible: readonly MailId[]): Selection {
  const set = new Set(visible);
  const ids = new Set([...sel.ids].filter((id) => set.has(id)));
  if (ids.size === sel.ids.size) return sel;
  return { ids, anchor: sel.anchor !== null && set.has(sel.anchor) ? sel.anchor : null };
}

/** 고른 메일을 보이는 차례대로 */
export const selectedInOrder = (sel: Selection, order: readonly Mail[]): Mail[] => order.filter((m) => sel.ids.has(m.id));

/** 묶음 동작 [고정]의 방향: 고른 것이 모두 고정이면 '고정 해제', 하나라도 아니면 '고정' */
export const bulkPinTarget = (mails: readonly Mail[]): boolean => !mails.filter(supportsPin).every(isPinned);
