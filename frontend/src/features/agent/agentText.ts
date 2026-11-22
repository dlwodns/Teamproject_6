// 에이전트 패널 글자 · 작은 판단 (순수 함수, node --test 대상). 대상 찾기 · 확인 판정은 서버(AgentResult)가 하므로 여기에는 없다.
import type { ActionResult, AgentSummaryItem, AgentTarget } from '../../api/contract.ts';
import { HttpError } from '../../api/errors.ts';
import type { Contact, DashboardSource, MailId } from '../../api/types.ts';
import type { DueKind } from '../../ui/DueLabel.tsx';
import { dueLabel } from '../tasks/deadline.ts';

/** 소개 줄 아래 예시 명령 칩 */
export const INTRO_EXAMPLES = ['오늘 뭐 해야 돼?', '김 팀장님 건 다 처리했어', '방금 거 취소해', '견적 건 내일 아침으로 미뤄', '답장 안 온 메일 있어?'] as const;

/** 지원 외 · 되묻기 카드의 예시(눌러서 실행) */
export const FALLBACK_EXAMPLES = ['김 팀장님 건 다 처리했어', '견적 건 내일 아침으로 미뤄', '오늘 뭐 해야 돼?'] as const;

/** 확인 시간이 지났을 때(확인 카드 expires_at · 실행 409) */
export const EXPIRED_TEXT = '확인 시간이 지났습니다. 다시 요청해 주십시오';

/** 되돌리기가 409로 거절됐을 때(이미 되돌린 기록 · 뒤에 같은 업무 · 항목을 바꾼 기록이 있음). 다시 눌러도 같으므로 버튼 없이 이 문장으로 끝낸다(#60 리뷰) */
export const UNDO_BLOCKED_TEXT = '이미 변경되어 되돌릴 수 없습니다';

/** 되돌리기 실패 → 409면 blocked(다시 하지 않음), 그 밖(연결 실패 · 5xx)은 error(다시 누를 수 있음) */
export function undoFailState(e: unknown): 'blocked' | 'error' {
  return e instanceof HttpError && e.status === 409 ? 'blocked' : 'error';
}

/** 확인 카드 실행 버튼 */
export function confirmLabel(action: string | null, n: number): string {
  if (action === 'T03') return `${n}건 완료 처리`;
  if (action === 'T05') return `${n}건 미루기`;
  if (action === 'T10') return `${n}건 빼기`;
  return `${n}건 실행`;
}

/** executor.py `%m/%d %H:%M`과 같은 모양(서버 제목과 맞춘다) */
export function formatMdhm(ms: number): string {
  const d = new Date(ms + 9 * 3600_000);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getUTCMonth() + 1)}/${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
}

/** 확인 카드 실행 뒤 결과 카드 제목. 실행 응답에는 제목이 없어 executor.py 결과 문구와 같게 만든다 */
export function executedTitle(action: string | null, n: number, result: ActionResult): string {
  if (result.actionId === null) return '이미 해당 상태여서 변경된 내용이 없습니다';
  if (action === 'T05') {
    const until = result.tasks.find((t) => t.snoozedUntilMs !== null)?.snoozedUntilMs;
    return until === undefined || until === null ? `${n}건을 연기했습니다` : `${n}건을 ${formatMdhm(until)}까지 연기했습니다`;
  }
  if (action === 'T10') return `${n}건을 목록에서 제외했습니다`;
  if (action === 'T03') return `${n}건을 완료 처리했습니다`;
  return `${n}건을 변경했습니다`;
}

/** 실행 응답의 새 상태를 대상에 입힌다 */
export function withStates(targets: readonly AgentTarget[], result: ActionResult): AgentTarget[] {
  const byId = new Map(result.tasks.map((t) => [t.id, t]));
  return targets.map((t) => {
    const s = byId.get(t.id);
    return s ? { ...t, status: s.status, snoozedUntilMs: s.snoozedUntilMs } : t;
  });
}

/** T04 결과 notes '행동 #7(T03)를 되돌림'에서 되돌린 기록 id. 없으면 null */
export function undoneActionId(notes: readonly string[]): number | null {
  for (const n of notes) {
    const m = /행동 #(\d+)\(/.exec(n);
    if (m) return Number(m[1]);
  }
  return null;
}

/** 직전 결과(다음 명령의 last_result_ids): 대상의 메일 id, 겹치면 한 번 */
export function resultMailIds(targets: readonly { mailId: MailId }[]): MailId[] {
  return [...new Set(targets.map((t) => t.mailId))];
}

// ── 화면 표시 ──

function contactLabel(c: Contact | undefined, fallback: string): string {
  if (!c?.name) return fallback;
  return c.position ? `${c.name} ${c.position}` : c.name;
}

/** 메일 id → 보낸 사람 표시(예: 김민준 팀장). 원자료가 없거나 모르는 메일이면 null(지어내지 않는다) */
export function senderLookup(data: DashboardSource | undefined): (mailId: MailId) => string | null {
  if (!data) return () => null;
  const mails = new Map(data.mails.map((m) => [m.id, m]));
  const contacts = new Map(data.contacts.map((c) => [c.email, c]));
  return (mailId) => {
    const m = mails.get(mailId);
    return m ? contactLabel(contacts.get(m.sender), m.sender) : null;
  };
}

/** 조회 결과 상태 꼬리: '나중에(11/14 09:00)' 등. 미처리면 null */
export function targetStatusText(t: AgentTarget): string | null {
  if (t.status === 'snoozed') return t.snoozedUntilMs === null ? '나중에' : `나중에(${formatMdhm(t.snoozedUntilMs)})`;
  if (t.status === 'done') return '완료';
  if (t.status === 'excluded') return '제외';
  return null;
}

export interface DueView {
  kind: DueKind;
  text: string;
  full: string | null;
}

/** 오늘 요약 한 줄의 기한 표시 */
export function dueOf(item: Pick<AgentSummaryItem, 'dueAtMs' | 'dueRaw' | 'dueTimeStated' | 'section'>, asOfMs: number): DueView {
  // 회고의 '금일 완료 업무'는 기한이 지났어도 끝낸 일이다(#190 리뷰 2)
  if (item.section === 'done_today') return { kind: 'done', text: '완료', full: '완료' };
  if (item.dueAtMs === null && item.dueRaw === 'ASAP') return { kind: 'urgent', text: 'ASAP', full: '즉시(ASAP)' };
  const d = dueLabel(item.dueAtMs, asOfMs, item.dueTimeStated);
  const kind: DueKind = d.state === 'overdue' ? 'urgent' : d.state === 'today' ? 'today' : d.state === 'none' ? 'none' : 'later';
  return { kind, text: d.text, full: d.full };
}

/** 회신 초안을 메일 화면의 답장 작성으로 여는 주소(FE-5 메일 화면이 reply · draft를 읽는다) */
export function replyDraftPath(mailId: MailId, text: string): string {
  return `/mail/inbox/${mailId}?reply=1&draft=${encodeURIComponent(text)}`;
}
