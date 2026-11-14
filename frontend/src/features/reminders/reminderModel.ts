// 리마인더 화면의 판단 (FE-16 · 명세 docs/10_planning/reminders.md 2 · 3 · 5절). 순수 함수, node --test 대상.
// - 업무 하나에는 항목 하나: 여러 유형에 걸리면 정해진 순서에서 앞선 것 하나만(정리 제안이 맨 앞)
// - 목록 순서: 기한이 이른 순, 기한이 없으면 생긴 순. '조용히 둠'은 맨 아래 접기 한 곳에
// - 버튼은 등록된 행동만 그린다(D27). 실행할 길이 없는 버튼은 그리지 않는다(죽은 버튼 금지)
import {
  DISMISS_REASONS,
  REMINDER_GROUPS,
  type DismissReason,
  type ReminderAction,
  type ReminderGroup,
  type ReminderItem,
  type ReminderType,
} from '../../api/contract.ts';
import type { MailId, TaskId } from '../../api/types.ts';
import { formatKstShort } from '../../lib/snooze.ts';
import { COMMAND_TEXT, HTTP_NOT_READY, type PlanMode } from '../agent/agentPanelPlan.ts';
import { mailPath } from '../mail/routes.ts';

export type GroupFilter = ReminderGroup | 'all';

export const GROUP_LABEL: Record<GroupFilter, string> = {
  all: '전체',
  due: '기한',
  waiting: '답 기다림',
  promise: '내 약속',
  revisit: '다시 볼 일',
  prepare: '준비',
  cleanup: '정리 제안',
};

/** 메뉴 · 칩 순서 */
export const GROUP_FILTERS: readonly GroupFilter[] = ['all', ...REMINDER_GROUPS];

export const TYPE_LABEL: Record<ReminderType, string> = {
  overdue: '기한 지남',
  due_soon: '기한 임박',
  due_changed: '기한 바뀜',
  due_cluster: '기한 몰림',
  no_reply: '답 없음',
  their_promise: '상대 약속 지남',
  my_promise: '내가 한 약속',
  delegated: '넘긴 일',
  snooze_due: '미룬 일',
  priority_sender: '상급자 메일',
  cc_mention: '참조 속 지목',
  stale: '오래 둔 일',
  stalled_thread: '끊긴 대화',
  meeting_prep: '회의 준비',
  recurring: '반복 업무',
  resolved: '끝난 것 같아요',
  reply_confirm: '답장 보냈어요',
};

/** AI가 알아챈 신호로 생긴 유형. ⋯ 메뉴 '잘못 알아챘어요'는 이것들에만 */
export const AI_SIGNAL_TYPES: ReadonlySet<ReminderType> = new Set(['due_changed', 'their_promise', 'my_promise', 'resolved', 'stalled_thread']);

/** 업무 하나가 여러 유형에 걸릴 때 남길 순서(명세 3절). 이미 끝난 일을 '기한 지남'으로 재촉하지 않게 정리 제안이 맨 앞 */
export const TASK_PRIORITY: readonly ReminderType[] = [
  'resolved',
  'reply_confirm',
  'due_changed',
  'overdue',
  'due_soon',
  'meeting_prep',
  'snooze_due',
  'priority_sender',
  'cc_mention',
  'stalled_thread',
  'stale',
];

const rank = (t: ReminderType) => {
  const i = TASK_PRIORITY.indexOf(t);
  return i < 0 ? TASK_PRIORITY.length : i;
};

/** 업무 하나에 항목 하나. 업무가 하나뿐인 항목만 비교하고(기한 몰림처럼 날짜 단위 항목은 그대로), 처음 나온 자리를 지킨다 */
export function onePerTask(items: readonly ReminderItem[]): ReminderItem[] {
  const best = new Map<TaskId, ReminderItem>();
  for (const it of items) {
    if (it.taskId === null) continue;
    const cur = best.get(it.taskId);
    if (!cur || rank(it.type) < rank(cur.type)) best.set(it.taskId, it);
  }
  return items.filter((it) => it.taskId === null || best.get(it.taskId) === it);
}

/** 기한이 이른 순, 기한이 없으면 생긴 순(기한 있는 것 다음). 같으면 키 순 */
export function sortItems(items: readonly ReminderItem[]): ReminderItem[] {
  return [...items].sort((a, b) => {
    if (a.dueAtMs !== null && b.dueAtMs !== null && a.dueAtMs !== b.dueAtMs) return a.dueAtMs - b.dueAtMs;
    if ((a.dueAtMs === null) !== (b.dueAtMs === null)) return a.dueAtMs === null ? 1 : -1;
    if (a.createdAtMs !== b.createdAtMs) return a.createdAtMs - b.createdAtMs;
    return a.key < b.key ? -1 : a.key > b.key ? 1 : 0;
  });
}

/** 화면에 보일 항목 전부(끝난 것은 빼고, 업무당 하나, 정렬) */
export function visibleItems(items: readonly ReminderItem[]): ReminderItem[] {
  return sortItems(onePerTask(items.filter((i) => i.state === 'active' || i.state === 'quiet')));
}

export function inGroup(items: readonly ReminderItem[], group: GroupFilter): ReminderItem[] {
  return group === 'all' ? [...items] : items.filter((i) => i.group === group);
}

/** 묶음의 목록과 '조용히 둔 것' */
export function splitQuiet(items: readonly ReminderItem[]): { active: ReminderItem[]; quiet: ReminderItem[] } {
  return { active: items.filter((i) => i.state !== 'quiet'), quiet: items.filter((i) => i.state === 'quiet') };
}

/** 메뉴 건수. 화면에 보이는 목록과 같은 숫자가 되게 서버 건수 대신 거른 항목으로 센다 */
export function groupCounts(items: readonly ReminderItem[]): Record<GroupFilter, number> {
  const counts = { all: items.length } as Record<GroupFilter, number>;
  for (const g of REMINDER_GROUPS) counts[g] = items.filter((i) => i.group === g).length;
  return counts;
}

/** '기한' 메뉴 숫자에만 리마인드 색을 쓴다 — 기한 지남이 있을 때(한 화면에 색 신호 하나) */
export function hasOverdue(items: readonly ReminderItem[]): boolean {
  return items.some((i) => i.type === 'overdue' && i.state === 'active');
}

/** 줄 둘째 줄: 유형 · 이유(회색) */
export function secondLine(item: ReminderItem): string {
  return `${TYPE_LABEL[item.type]} · ${item.reason}`;
}

export function counterpartText(item: ReminderItem): string | null {
  const c = item.counterpart;
  if (!c) return null;
  return c.position ? `${c.name} ${c.position}` : c.name;
}

// ── 버튼 → 실행 계획 ──

/** 메일 열기 대상: 받은 메일이면 그 메일, 답을 기다리는 보낸 메일이면 응답 대기 메일함, 둘 다 아니면 열 곳이 없다 */
export type MailTarget = 'mail' | 'waiting' | null;

export interface PlanContext {
  mailTarget: (mailId: MailId) => MailTarget;
  /** 데이터 모드. 실제(http)에서는 backend에 실행 경로가 없는 초안 · 그날 업무 · 응답 대기를 화면 이동으로 바꾼다(#60 리뷰와 같은 문제) */
  mode?: PlanMode;
}

export type ReminderPlan =
  | { type: 'status'; status: 'done' | 'excluded'; taskIds: TaskId[] }
  /** 시각 메뉴를 거쳐 미루기. 업무가 여럿(기한 몰림 '하나 미루기')이면 먼저 업무를 고른다 */
  | { type: 'snooze'; taskIds: TaskId[] }
  | { type: 'command'; text: string; selectedMailIds?: MailId[] }
  | { type: 'open_mail'; mailId: MailId }
  | { type: 'open_waiting' }
  | { type: 'route'; to: string }
  | { type: 'apply' }
  | { type: 'dismiss'; reason: DismissReason };

export function planReminderAction(item: ReminderItem, action: ReminderAction, ctx: PlanContext): ReminderPlan | null {
  const taskIds = item.taskIds;
  switch (action.action) {
    case 'T03':
      return taskIds.length === 1 ? { type: 'status', status: 'done', taskIds } : null;
    case 'T10':
      return taskIds.length === 1 ? { type: 'status', status: 'excluded', taskIds } : null;
    case 'T05':
      return taskIds.length > 0 ? { type: 'snooze', taskIds } : null;
    case 'T07':
      if (item.mailId === null) return null;
      if (ctx.mode === 'http' && HTTP_NOT_READY.has('T07')) return { type: 'route', to: mailPath('inbox', item.mailId, { reply: true }) };
      return { type: 'command', text: COMMAND_TEXT.T07, selectedMailIds: [item.mailId] };
    case 'T01':
      if (ctx.mode === 'http' && HTTP_NOT_READY.has('T01')) return { type: 'route', to: '/dashboard' };
      return { type: 'command', text: COMMAND_TEXT.T01 };
    case 'T06':
      if (ctx.mode === 'http' && HTTP_NOT_READY.has('T06')) return { type: 'open_waiting' };
      return { type: 'command', text: COMMAND_TEXT.T06 };
    case 'open_mail': {
      if (item.mailId === null) return null;
      const where = ctx.mailTarget(item.mailId);
      return where === 'mail' ? { type: 'open_mail', mailId: item.mailId } : where === 'waiting' ? { type: 'open_waiting' } : null;
    }
    case 'apply':
      return { type: 'apply' };
    case 'dismiss':
      return { type: 'dismiss', reason: action.reason ?? ((DISMISS_REASONS as readonly string[]).includes(action.id) ? (action.id as DismissReason) : 'hide') };
    default:
      return null;
  }
}

export const MAX_BUTTONS = 3;

/** 그릴 버튼(실행 경로가 있는 것만, 최대 limit개). 주 버튼이 맨 뒤(오른쪽) — 보조 → 주 순서 */
export function drawableActions(item: ReminderItem, ctx: PlanContext, limit = MAX_BUTTONS): { action: ReminderAction; plan: ReminderPlan }[] {
  const all = item.actions.flatMap((action) => {
    const plan = planReminderAction(item, action, ctx);
    return plan ? [{ action, plan }] : [];
  });
  const primary = all.filter((a) => a.action.primary);
  const rest = all.filter((a) => !a.action.primary);
  // 자리가 모자라면 주 버튼을 남기고 앞쪽 보조 버튼부터 남긴다
  const keep = rest.slice(0, Math.max(0, limit - primary.length));
  return [...keep, ...primary.slice(0, limit)];
}

export type MenuKind = 'not_mine' | 'mute' | 'unmute' | 'wrong_signal';

/**
 * ⋯ 메뉴: 내 일 아님(업무 항목, 버튼에 없을 때) · 이 유형 알림 끄기(끈 유형이면 켜기) · 잘못 알아챘어요(AI 신호 유형, 버튼에 없을 때).
 * 같은 동작을 버튼과 메뉴에 두 번 두지 않는다(UX-D18)
 */
export function menuKinds(item: ReminderItem, muted: boolean, drawn: readonly { plan: ReminderPlan }[]): MenuKind[] {
  const has = (reason: DismissReason) => drawn.some((d) => (d.plan.type === 'dismiss' && d.plan.reason === reason) || (reason === 'not_mine' && d.plan.type === 'status' && d.plan.status === 'excluded'));
  const out: MenuKind[] = [];
  if (item.taskId !== null && !has('not_mine')) out.push('not_mine');
  out.push(muted ? 'unmute' : 'mute');
  if (AI_SIGNAL_TYPES.has(item.type) && !has('wrong_signal')) out.push('wrong_signal');
  return out;
}

export const MENU_LABEL: Record<MenuKind, string> = {
  not_mine: '내 일 아님',
  mute: '이 유형 알림 끄기',
  unmute: '이 유형 알림 켜기',
  wrong_signal: '잘못 알아챘어요',
};

const quote = (t: string) => `'${t.length > 20 ? `${t.slice(0, 19).trimEnd()}…` : t}'`;

/** 실행 뒤 토스트 한 줄(과거형) */
export function reminderResultText(
  kind: 'done' | 'excluded' | 'snoozed' | 'applied' | DismissReason | 'muted' | 'unmuted',
  item: Pick<ReminderItem, 'title' | 'type'>,
  untilMs: number | null = null,
): string {
  const what = quote(item.title);
  switch (kind) {
    case 'done':
      return `${what} 완료했어요`;
    case 'excluded':
    case 'not_mine':
      return `${what} 내 일에서 뺐어요`;
    case 'snoozed':
      return untilMs === null ? `${what} 미뤘어요` : `${what} ${formatKstShort(untilMs)}까지 미뤘어요`;
    case 'applied':
      if (item.type === 'due_changed') return `${what} 기한을 바꿨어요`;
      if (item.type === 'my_promise') return `${what} 약속을 지켰다고 남겼어요`;
      if (item.type === 'their_promise') return `${what} 받았다고 남겼어요`;
      return `${what} 완료했어요`;
    case 'stop_waiting':
      return `${what} 답을 그만 기다려요`;
    case 'wrong_signal':
      return `${what} 잘못 알아챈 것으로 남겼어요`;
    case 'hide':
      return `${what} 리마인더를 숨겼어요`;
    case 'keep':
      return `${what} 그대로 뒀어요`;
    case 'muted':
      return `'${TYPE_LABEL[item.type]}' 알림을 껐어요. 목록에는 계속 보여요`;
    case 'unmuted':
      return `'${TYPE_LABEL[item.type]}' 알림을 다시 켰어요`;
  }
}

/** 상세 '이 항목 기록' 한 줄 */
export function historyLine(item: ReminderItem): string {
  const first = `처음 알아챈 때 ${formatKstShort(item.createdAtMs)}`;
  if (item.notifyCount === 0) return `${first} · 아직 알리지 않았어요`;
  const last = item.lastNotifiedAtMs === null ? '' : ` · 마지막 ${formatKstShort(item.lastNotifiedAtMs)}`;
  const quiet = item.state === 'quiet' ? ' · 이제 목록에만 둬요' : '';
  return `${first} · 알림 ${item.notifyCount}번${last}${quiet}`;
}

/** 빈 상태 문구: 무엇이 나타날지 + 다음 행동(NN/g) */
export const EMPTY_TEXT: Record<GroupFilter, string> = {
  all: '새 메일에서 기한 · 답 기다림 · 약속을 찾으면 여기에 모아요.',
  due: '기한이 지나거나 24시간 안으로 다가온 업무가 여기에 보여요.',
  waiting: '보낸 요청에 3일 넘게 답이 없거나, 상대가 약속한 날이 지나면 여기에 보여요.',
  promise: '보낸 메일에서 "금요일까지 드리겠습니다" 같은 약속을 찾으면 여기에 보여요.',
  revisit: '미룬 시각이 된 일, 상급자 메일, 오래 둔 일이 여기에 보여요.',
  prepare: '회의 · 행사가 30분 앞으로 다가오면 여기에 보여요.',
  cleanup: '끝난 것 같은 업무나 답장을 보낸 메일이 있으면 완료할지 여기서 물어봐요.',
};
