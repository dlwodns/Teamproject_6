// 리마인더 화면의 판단 (FE-16 · 명세 docs/10_planning/reminders.md 2 · 3 · 5절). 순수 함수, node --test 대상.
// - 업무 하나에는 항목 하나: 여러 유형에 걸리면 정해진 순서에서 앞선 것 하나만(정리 제안이 맨 앞)
// - 목록 순서: 기한이 이른 순, 기한이 없으면 생긴 순. '조용히 둠'은 맨 아래 접기 한 곳에
// - 버튼은 등록된 행동만 그린다(D27). 실행할 길이 없는 버튼은 그리지 않는다(죽은 버튼 금지)
import {
  DISMISS_REASONS,
  type DismissReason,
  type ReminderAction,
  type ReminderGroup,
  type ReminderItem,
  type ReminderType,
  type TaskType,
} from '../../api/contract.ts';
import type { MailId, TaskId } from '../../api/types.ts';
import { formatKstShort } from '../../lib/snooze.ts';
import { mailPath } from '../mail/routes.ts';
import { COMMAND_TEXT, HTTP_NOT_READY, type PlanMode } from '../agent/agentPanelPlan.ts';

/** 알림 이유 묶음 이름. 🔔 알림 센터 칩에만 쓴다(캐치봇 리마인더 칸은 업무 유형 채널) */
export const GROUP_LABEL: Record<ReminderGroup, string> = {
  due: '기한',
  waiting: '회신 대기',
  promise: '이행 약속',
  revisit: '재확인',
  prepare: '준비',
  cleanup: '정리 제안',
};

// ── 캐치봇 리마인더 칸: 채널 2개(11-14 결정) ──
// 기준은 '시간이 무슨 뜻인가' 하나다. 마감 = 그때까지 끝내면 됨(기한 3시간 전 알림), 참석 = 그 시각에 가 있어야 함(30분 전 알림).
// 업무 유형 6종은 카드 맨 위 굵은 글자로 남긴다. 업무 유형이 없는 항목(보낸 메일 답 없음 · 약속 · 기한 몰림 · 유형 모르는 옛 업무)은
// 칸에 보이지 않는다(🔔 · 브리핑에는 남음).

/** 주소에 쓰는 채널 코드, 메뉴 순서 */
export const CHANNELS = ['deadline', 'meeting'] as const;
export type Channel = (typeof CHANNELS)[number];
/** 'all'은 주소에서만 받는다(🔔 · 브리핑의 바로가기). 화면은 항목의 채널로 바꿔 쓴다 */
export type ChannelFilter = Channel | 'all';

export const CHANNEL_LABEL: Record<Channel, string> = { deadline: '마감', meeting: '참석' };

/** 카드 맨 위에 크게 쓰는 업무 유형 이름 */
export const TASK_TYPE_LABEL: Record<TaskType, string> = {
  자료제출요청: '자료 제출',
  회신요청: '회신',
  검토승인요청: '검토 · 승인',
  수정재전송요청: '수정 · 재전송',
  일정참석: '참석',
  조치요청: '조치',
};

export function channelOf(item: Pick<ReminderItem, 'taskType'>): Channel | null {
  if (item.taskType === null) return null;
  return item.taskType === '일정참석' ? 'meeting' : 'deadline';
}

export const TYPE_LABEL: Record<ReminderType, string> = {
  overdue: '기한 경과',
  due_soon: '기한 임박',
  due_changed: '기한 변경',
  due_cluster: '마감 집중',
  no_reply: '회신 미수신',
  their_promise: '상대 약속 기한 경과',
  my_promise: '이행 약속',
  delegated: '위임 업무',
  snooze_due: '연기 업무',
  priority_sender: '상급자 메일',
  cc_mention: '참조 메일 내 요청',
  stale: '장기 미처리',
  stalled_thread: '회신 지연',
  meeting_prep: '회의 준비',
  recurring: '반복 업무',
  resolved: '종결 추정',
  reply_confirm: '회신 발송 확인',
};

/** AI가 알아챈 신호로 생긴 유형. ⋯ 메뉴 '잘못된 알림으로 신고'는 이것들에만 */
export const AI_SIGNAL_TYPES: ReadonlySet<ReminderType> = new Set(['due_changed', 'their_promise', 'my_promise', 'resolved', 'stalled_thread']);

/** 업무 하나가 여러 유형에 걸릴 때 남길 순서(명세 3절). 이미 끝난 일을 '기한 경과'으로 재촉하지 않게 정리 제안이 맨 앞 */
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

/** 리마인더 칸에 보일 항목 전부: 보이는 항목 중 업무 유형이 있는 것 */
export function channelItems(items: readonly ReminderItem[]): ReminderItem[] {
  return visibleItems(items).filter((i) => channelOf(i) !== null);
}

export function inChannel(items: readonly ReminderItem[], channel: Channel): ReminderItem[] {
  return items.filter((i) => channelOf(i) === channel);
}

/** 묶음의 목록과 '조용히 둔 것' */
export function splitQuiet(items: readonly ReminderItem[]): { active: ReminderItem[]; quiet: ReminderItem[] } {
  return { active: items.filter((i) => i.state !== 'quiet'), quiet: items.filter((i) => i.state === 'quiet') };
}

/** 메뉴 건수. 화면에 보이는 목록과 같은 숫자가 되게 서버 건수 대신 거른 항목으로 센다 */
export function channelCounts(items: readonly ReminderItem[]): Record<Channel, number> {
  const counts = {} as Record<Channel, number>;
  for (const c of CHANNELS) counts[c] = inChannel(items, c).length;
  return counts;
}

/** 채널 숫자에 리마인드 색을 쓰는 조건 — 활성 기한 지남이 있을 때 */
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
  /** 시각 메뉴를 거쳐 미루기. 업무가 여럿(기한 몰림 '1건 연기')이면 먼저 업무를 고른다 */
  | { type: 'snooze'; taskIds: TaskId[] }
  | { type: 'command'; text: string; selectedMailIds?: MailId[] }
  | { type: 'open_mail'; mailId: MailId; /** 서버 버튼 이름 대신 쓸 이름(실제 모드의 [초안 보기] → [메일 열기]) */ label?: string }
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
    case 'T07': {
      // 11-15 [회신 작성]: 대화를 거치지 않고 바로 그 메일의 답장 쓰기 화면으로(작성 · 다듬기는 메일 화면이 맡는다).
      // 답을 기다리는 보낸 메일(회신 요청 작성)은 응답 대기 메일함으로
      if (item.mailId === null) return null;
      const where = ctx.mailTarget(item.mailId);
      return where === 'mail' ? { type: 'route', to: mailPath('inbox', item.mailId, { reply: true }) } : where === 'waiting' ? { type: 'open_waiting' } : null;
    }
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
  not_mine: '담당 아님',
  mute: '이 유형 알림 끄기',
  unmute: '이 유형 알림 켜기',
  wrong_signal: '잘못된 알림으로 신고',
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
      return `${what} 완료 처리했습니다`;
    case 'excluded':
    case 'not_mine':
      return `${what} 담당 업무에서 제외했습니다`;
    case 'snoozed':
      return untilMs === null ? `${what} 연기했습니다` : `${what} ${formatKstShort(untilMs)}까지 연기했습니다`;
    case 'applied':
      if (item.type === 'due_changed') return `${what} 기한을 변경했습니다`;
      if (item.type === 'my_promise') return `${what} 이행 완료로 기록했습니다`;
      if (item.type === 'their_promise') return `${what} 수신 확인으로 기록했습니다`;
      return `${what} 완료 처리했습니다`;
    case 'stop_waiting':
      return `${what} 회신 대기를 종료했습니다`;
    case 'wrong_signal':
      return `${what} 잘못된 알림으로 신고했습니다`;
    case 'hide':
      return `${what} 알림을 숨겼습니다`;
    case 'keep':
      return `${what} 현행 유지했습니다`;
    case 'muted':
      return `'${TYPE_LABEL[item.type]}' 알림을 해제했습니다. 목록에는 계속 표시됩니다`;
    case 'unmuted':
      return `'${TYPE_LABEL[item.type]}' 알림을 다시 설정했습니다`;
  }
}

/** 상세 '이 항목 기록' 한 줄 */
export function historyLine(item: ReminderItem): string {
  const first = `처음 알아챈 때 ${formatKstShort(item.createdAtMs)}`;
  if (item.notifyCount === 0) return `${first} · 아직 알림 전입니다`;
  const last = item.lastNotifiedAtMs === null ? '' : ` · 마지막 ${formatKstShort(item.lastNotifiedAtMs)}`;
  const quiet = item.state === 'quiet' ? ' · 이후 목록에만 표시합니다' : '';
  return `${first} · 알림 ${item.notifyCount}번${last}${quiet}`;
}

/** 빈 상태 문구: 무엇이 나타날지 + 다음 행동(NN/g) */
export const EMPTY_TEXT: Record<Channel, string> = {
  deadline: '회신 · 제출 · 검토 · 조치 등 기한이 있는 업무의 마감이 다가오면 이곳에 표시됩니다.',
  meeting: '참석 예정인 회의 · 행사가 다가오면 이곳에 표시됩니다.',
};
