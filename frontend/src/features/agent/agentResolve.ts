// 명령 해석 결과(PlanResponse) + 대시보드 원자료 → 실제 대상 업무 · 확인 여부 · 카드에 쓸 글자 (순수 함수, node --test 대상).
// 실제 서비스에서는 backend(BE-18)가 하는 일(발신자 DB 맞추기 · D37 확인 정책)이다. 창구가 생기면 서버 응답으로 바뀌는 부분이라
// 화면 부품과 떼어 둔다.
//
// D37 확인 규칙(decisions.md 3절 '확인 절차는 서로 다른 규칙이다' 3번):
//   - 조회 · 표시(T01 · T06 · T07)와 되돌리기(T04)는 확인 없이 바로
//   - 상태 변경 대상 1건은 바로 실행 + [실행 취소]
//   - 대상 2건 이상 · 후보(발신자) 여럿 · 설정 변경은 대화 안 확인 카드
import type { Awaiting, Contact, DashboardSource, Mail, MailId, Task, TaskId } from '../../api/types.ts';
import type { DueKind } from '../../ui/DueLabel.tsx';
import { formatKstShort } from '../../lib/snooze.ts';
import { dueLabel } from '../tasks/deadline.ts';
import { mockReplyDraft, parseKstNaive, type ActionId, type PlanResponse } from './agentMock.ts';

export interface TargetItem {
  id: TaskId;
  text: string;
  /** 보낸 사람 표시(예: 김민준 팀장) */
  sender: string;
}

/** 이 패널에서 마지막으로 바꾼 것(T04 '방금 거 취소해'가 되돌린다) */
export interface LastAgentAction {
  runId: number;
  actionId: number;
  count: number;
}

export interface SummaryItem {
  id: TaskId;
  text: string;
  sender: string;
  due: { kind: DueKind; text: string; full: string | null };
}

export type StatusOp = 'complete' | 'snooze';

export type Resolution =
  | {
      kind: 'status';
      op: StatusOp;
      untilMs: number | null;
      targets: TargetItem[];
      confirm: boolean;
      /** 확인 카드 제목(동사 질문) */
      question: string;
      /** 단계 목록 '대상 찾기' 아래 한 줄 */
      note: string;
      /** '어떻게 해석했나요' 문장들 */
      interpretation: string[];
    }
  | { kind: 'undo'; last: LastAgentAction; note: string }
  | { kind: 'summary'; title: string; items: SummaryItem[]; hint: string | null; note: string }
  | { kind: 'awaiting'; title: string; items: Awaiting[]; note: string }
  | { kind: 'draft'; mailId: MailId; subject: string; to: string; text: string; note: string }
  | { kind: 'fail'; title: string; hint: string; note: string };

export interface ResolveSession {
  lastAction: LastAgentAction | null;
}

// ── 조사 ──

const HANGUL_FIRST = 0xac00;
const HANGUL_LAST = 0xd7a3;
// 숫자를 읽는 소리의 받침: 0 영 · 1 일 · 3 삼 · 6 육 · 7 칠 · 8 팔 → 받침 있음(1 · 7 · 8은 ㄹ)
const DIGIT_FINAL: Record<string, 'none' | 'rieul' | 'other'> = {
  '0': 'other', '1': 'rieul', '2': 'none', '3': 'other', '4': 'none', '5': 'none', '6': 'other', '7': 'rieul', '8': 'rieul', '9': 'none',
};

/** 마지막 소리의 받침. 따옴표 · 괄호 닫기는 건너뛰고 본다. 한글 · 숫자가 아니면 null */
function finalSound(word: string): 'none' | 'rieul' | 'other' | null {
  const trimmed = word.replace(/[\s'"’”)\]]+$/u, '');
  const ch = trimmed[trimmed.length - 1] ?? '';
  if (/\d/.test(ch)) return DIGIT_FINAL[ch]!;
  const code = ch.charCodeAt(0);
  if (Number.isNaN(code) || code < HANGUL_FIRST || code > HANGUL_LAST) return null;
  const f = (code - HANGUL_FIRST) % 28;
  return f === 0 ? 'none' : f === 8 ? 'rieul' : 'other';
}

/** 을/를 */
export function withEul(word: string): string {
  const f = finalSound(word);
  return `${word}${f === null ? '을(를)' : f === 'none' ? '를' : '을'}`;
}

/** 이/가 */
export function withI(word: string): string {
  const f = finalSound(word);
  return `${word}${f === null ? '이(가)' : f === 'none' ? '가' : '이'}`;
}

/** 으로/로(받침 없음 · ㄹ 받침 → 로) */
export function withEuro(word: string): string {
  const f = finalSound(word);
  return `${word}${f === null ? '(으)로' : f === 'other' ? '으로' : '로'}`;
}

// ── 발신자 맞추기 ──

export function contactLabel(c: Contact | undefined, fallback: string): string {
  if (!c?.name) return fallback;
  return c.position ? `${c.name} ${c.position}` : c.name;
}

/**
 * '김 팀장' · '김민준 팀장' → 연락처 후보. 이름이 한 글자면 성으로, 두 글자 이상이면 이름 앞부분으로 맞추고 직책은 같아야 한다.
 * 결과가 2명 이상이면 '후보 여럿'(D37 확인 카드)이다.
 */
export function resolveSender(query: string, contacts: readonly Contact[]): Contact[] {
  const parts = query.trim().split(/\s+/);
  const title = parts.length > 1 ? parts[parts.length - 1]! : null;
  const name = parts.length > 1 ? parts.slice(0, -1).join('') : parts[0] ?? '';
  if (!name) return [];
  return contacts.filter((c) => {
    if (!c.name || c.name.length < 2) return false;
    const nameOk = name.length === 1 ? c.name.startsWith(name) : c.name === name || c.name.startsWith(name);
    const titleOk = title === null || c.position === title;
    return nameOk && titleOk;
  });
}

// ── D37 ──

export interface ConfirmInput {
  /** 상태 · 설정을 바꾸는 행동인가(T03 · T05 등). 조회 · 표시 · 되돌리기는 false */
  mutating: boolean;
  targetCount: number;
  /** 대상 사람(발신자) 후보 수 */
  candidateCount: number;
  settingsChange?: boolean;
}

/** D37: 대상 1건 상태 변경은 바로 실행, 2건 이상 · 후보 여럿 · 설정 변경은 확인 카드 */
export function needsConfirm({ mutating, targetCount, candidateCount, settingsChange = false }: ConfirmInput): boolean {
  if (!mutating) return false;
  return settingsChange || targetCount >= 2 || candidateCount >= 2;
}

/** 확인 단계를 둘 수 있는 행동(단계 줄에 '확인'을 넣는다. 대상 1건이면 건너뜀으로 표시) */
export const CONFIRMABLE: readonly ActionId[] = ['T03', 'T05'];

// ── 해석 ──

function fail(title: string, hint: string, note = title): Resolution {
  return { kind: 'fail', title, hint, note };
}

function dueOf(task: Task, asOfMs: number): SummaryItem['due'] {
  if (task.dueAtMs === null && task.dueRaw === 'ASAP') return { kind: 'urgent', text: 'ASAP', full: '즉시(ASAP)' };
  const d = dueLabel(task.dueAtMs, asOfMs);
  const kind: DueKind = d.state === 'overdue' ? 'urgent' : d.state === 'today' ? 'today' : d.state === 'none' ? 'none' : 'later';
  return { kind, text: d.text, full: d.full };
}

const DUE_RANK: Record<DueKind, number> = { urgent: 0, today: 1, later: 2, none: 3, done: 4, 'overdue-mail': 0 };

function summary(plan: PlanResponse, data: DashboardSource): Resolution {
  const mails = new Map(data.mails.map((m) => [m.id, m]));
  const contacts = new Map(data.contacts.map((c) => [c.email, c]));
  const pending = data.tasks.filter((t) => t.status === 'pending');
  const dateMs = typeof plan.params.date === 'string' ? parseKstNaive(plan.params.date) : null;
  const dayOffset = dateMs === null ? 0 : Math.round((dateMs - startOfKstDay(data.asOfMs)) / 86_400_000);
  const toItem = (t: Task): SummaryItem => {
    const mail = mails.get(t.mailId);
    return { id: t.id, text: t.text, sender: mail ? contactLabel(contacts.get(mail.sender), mail.sender) : '보낸 사람 모름', due: dueOf(t, data.asOfMs) };
  };
  const byDue = (a: SummaryItem, b: SummaryItem) => DUE_RANK[a.due.kind] - DUE_RANK[b.due.kind];

  if (dayOffset === 1) {
    const items = pending.filter((t) => dueLabel(t.dueAtMs, data.asOfMs).state === 'tomorrow').map(toItem);
    return {
      kind: 'summary',
      title: items.length ? `내일 마감 ${items.length}건이에요` : '내일 마감인 업무는 없어요',
      items,
      hint: `지금 미처리 ${pending.length}건`,
      note: `내일 마감 업무 ${items.length}건`,
    };
  }
  const urgent = pending
    .map(toItem)
    .filter((i) => i.due.kind === 'urgent' || i.due.kind === 'today')
    .sort(byDue);
  const checks = data.mails.some((m) => m.lane !== undefined) ? data.mails.filter((m) => m.lane === '확인').length : null;
  const rest = pending.length - urgent.length;
  return {
    kind: 'summary',
    title: urgent.length ? `긴급 ${urgent.length}건이에요` : '오늘 급한 업무는 없어요',
    items: urgent.slice(0, 5),
    hint: `그 밖에 미처리 ${rest}건${checks === null ? '' : ` · 확인사항 ${checks}건`}${urgent.length > 5 ? ` · 긴급 ${urgent.length - 5}건 더 있음` : ''}`,
    note: `미처리 ${pending.length}건 중 기한 지남 · 오늘 마감 · ASAP`,
  };
}

function startOfKstDay(ms: number): number {
  const kst = 9 * 3600_000;
  return Math.floor((ms + kst) / 86_400_000) * 86_400_000 - kst;
}

function statusChange(plan: PlanResponse, data: DashboardSource, op: StatusOp): Resolution {
  const t = plan.target;
  const mails = new Map(data.mails.map((m) => [m.id, m]));
  const contacts = new Map(data.contacts.map((c) => [c.email, c]));
  const interpretation: string[] = [];
  const notes: string[] = [];

  let senders: Contact[] | null = null;
  if (t.sender) {
    senders = resolveSender(t.sender, data.contacts);
    if (senders.length === 0) return fail(`'${t.sender}'에 맞는 연락처가 없어요`, '이름과 직책을 연락처에 있는 그대로 말해 보세요. 예: 김민준 팀장님 건 다 처리했어');
    const names = senders.map((c) => `${contactLabel(c, c.email)}${c.org ? `(${c.org})` : ''}`);
    interpretation.push(
      senders.length === 1
        ? `${withEul(`'${t.sender}님'`)} ${withEuro(names[0]!)} 해석했어요.`
        : `'${t.sender}님'에 맞는 사람이 ${senders.length}명이에요: ${names.join(', ')}.`,
    );
    notes.push(`'${t.sender}' → ${senders.map((c) => contactLabel(c, c.email)).join(' · ')}`);
  }
  let pickedMails: Set<MailId> | null = null;
  if (t.mail_ids.length) {
    pickedMails = new Set(t.mail_ids.map((id) => Number(id) as MailId));
    const subjects = [...pickedMails].map((id) => mails.get(id)?.subject).filter((s): s is string => Boolean(s));
    interpretation.push(subjects.length ? `가리킨 메일을 고른 메일 ${withEuro(`'${subjects.join("' · '")}'`)} 해석했어요.` : '가리킨 메일을 찾지 못했어요.');
    notes.push('고른 메일');
  }
  if (t.keyword) {
    interpretation.push(`'${t.keyword} 건'을 업무 이름이나 메일 제목에 ${withI(`'${t.keyword}'`)} 들어간 업무로 찾았어요.`);
    notes.push(`'${t.keyword}' 들어간 업무`);
  }
  if (t.category) {
    interpretation.push(`${withEuro(`'${t.category}'`)} 분류된 메일의 업무로 찾았어요.`);
    notes.push(`${t.category} 메일`);
  }

  const emails = senders ? new Set(senders.map((c) => c.email)) : null;
  const open = (task: Task) => (op === 'complete' ? task.status === 'pending' || task.status === 'snoozed' : task.status === 'pending');
  const matches = (task: Task, mail: Mail | undefined) => {
    if (pickedMails && !pickedMails.has(task.mailId)) return false;
    if (!mail) return !emails && !t.category && !t.keyword;
    if (emails && !emails.has(mail.sender)) return false;
    if (t.category && mail.category !== t.category) return false;
    if (t.keyword && !task.text.includes(t.keyword) && !mail.subject.includes(t.keyword)) return false;
    return true;
  };
  const targets: TargetItem[] = data.tasks
    .filter((task) => open(task) && matches(task, mails.get(task.mailId)))
    .map((task) => {
      const mail = mails.get(task.mailId);
      return { id: task.id, text: task.text, sender: mail ? contactLabel(contacts.get(mail.sender), mail.sender) : '보낸 사람 모름' };
    });

  let untilMs: number | null = null;
  if (op === 'snooze') {
    untilMs = typeof plan.params.until === 'string' ? parseKstNaive(plan.params.until) : null;
    if (untilMs === null) return fail('언제까지 미룰지 모르겠어요', "'내일 아침으로 미뤄'처럼 때를 함께 말해 주세요.");
    if (untilMs <= data.asOfMs) return fail('이미 지난 시각이에요', '앞으로의 때를 말해 주세요.');
    interpretation.push(`다시 볼 때를 ${withEuro(formatKstShort(untilMs))} 해석했어요.`);
  }

  const what = op === 'complete' ? '완료로 바꿀' : '미룰';
  if (targets.length === 0) {
    return fail(`${what} 미처리 업무가 없어요`, interpretation.join(' ') || '조건에 맞는 업무가 없어요.', `${notes.join(' · ')} · 0건`);
  }
  const candidateCount = senders?.length ?? 1;
  const confirm = needsConfirm({ mutating: true, targetCount: targets.length, candidateCount });
  const who = senders?.length === 1 ? `${contactLabel(senders[0], '')}님 ` : '';
  const question =
    op === 'complete'
      ? `${who}업무 ${targets.length}건을 완료로 바꿀까요?`
      : `${who}업무 ${targets.length}건을 ${formatKstShort(untilMs!)}까지 미룰까요?`;
  return {
    kind: 'status',
    op,
    untilMs,
    targets,
    confirm,
    question,
    note: `${notes.join(' · ')} · 미처리 ${targets.length}건`,
    interpretation,
  };
}

/**
 * PlanResponse → 해야 할 일. plan.action이 null이면 부르지 않는다(지원 외 · 되묻기는 부르는 쪽이 먼저 거른다).
 * data가 없으면(대시보드를 아직 못 불러옴) 대상을 찾을 수 없으므로 실패로 돌려준다.
 */
export function resolvePlan(plan: PlanResponse, data: DashboardSource | undefined, session: ResolveSession): Resolution {
  if (plan.action === 'T04') {
    const last = session.lastAction;
    if (!last) return fail('되돌릴 행동이 없어요', '이 패널에서 바꾼 것만 되돌릴 수 있어요. 바꾼 뒤 다른 것을 되돌렸다면 다시 되돌리지 않아요.', '되돌릴 행동 없음');
    return { kind: 'undo', last, note: `마지막 행동 · ${last.count}건` };
  }
  if (!data) return fail('업무 목록을 아직 불러오지 못했어요', '잠시 뒤 다시 말해 주세요.');
  switch (plan.action) {
    case 'T01':
      return summary(plan, data);
    case 'T03':
      return statusChange(plan, data, 'complete');
    case 'T05':
      return statusChange(plan, data, 'snooze');
    case 'T06': {
      if (data.awaiting === undefined) return fail('응답 대기 목록을 아직 볼 수 없어요', '서버에 응답 대기 기능이 생기면 볼 수 있어요.');
      const minDays = typeof plan.params.min_days === 'number' ? plan.params.min_days : 3;
      const items = data.awaiting.filter((a) => a.days >= minDays).sort((a, b) => b.days - a.days);
      return {
        kind: 'awaiting',
        title: items.length ? `${minDays}일 이상 답장이 없는 메일 ${items.length}건이에요` : `${minDays}일 이상 답장이 없는 메일은 없어요`,
        items,
        note: `보낸 메일 중 ${minDays}일 이상 답이 없는 것 ${items.length}건`,
      };
    }
    case 'T07': {
      const id = Number(plan.target.mail_ids[0]) as MailId;
      const mail = data.mails.find((m) => m.id === id);
      if (!mail) return fail('고른 메일을 찾지 못했어요', '메일 화면에서 메일을 고른 뒤 다시 말해 주세요.');
      const contact = data.contacts.find((c) => c.email === mail.sender);
      const texts = data.tasks.filter((t) => t.mailId === id && t.status === 'pending').map((t) => t.text);
      const tone = plan.params.tone === 'short' ? 'short' : 'polite';
      return {
        kind: 'draft',
        mailId: id,
        subject: mail.subject,
        to: contactLabel(contact, mail.sender),
        text: mockReplyDraft(texts, tone),
        note: `고른 메일 '${mail.subject}'`,
      };
    }
    default:
      return fail('지원하지 않는 요청이에요', '메일 업무를 찾고 처리하는 일만 할 수 있어요.');
  }
}

/** 지원 외 · 되묻기 때 보여 줄 예시(눌러서 실행) */
export const FALLBACK_EXAMPLES = ['오늘 뭐 해야 돼?', '답장 안 온 메일 있어?', '견적 건 내일 아침으로 미뤄'] as const;

/** 소개 줄 아래 예시 명령 칩 */
export const INTRO_EXAMPLES = ['오늘 뭐 해야 돼?', '김 팀장님 건 다 처리했어', '방금 거 취소해', '견적 건 내일 아침으로 미뤄', '답장 안 온 메일 있어?'] as const;

/** 되묻기(ambiguous) 안내. 어떤 행동 후보였는지에 따라 무엇을 더 말하면 되는지 알려 준다 */
export function ambiguousHint(candidates: readonly string[], hasSelectedMail: boolean): string {
  const c = candidates[0];
  if (c === 'T07' || ((c === 'T03' || c === 'T05') && !hasSelectedMail)) {
    return hasSelectedMail ? '어느 메일인지 한 통만 골라 주세요.' : "메일 화면에서 메일을 고른 뒤 '이거 완료'처럼 다시 말해 주세요.";
  }
  if (c === 'T05') return "'내일 아침으로 미뤄'처럼 언제까지인지 함께 말해 주세요.";
  if (c === 'T03') return "'김민준 팀장님 건 다 처리했어'처럼 누구의 무슨 업무인지 함께 말해 주세요.";
  return '조금 더 자세히 말해 주세요.';
}

/** 회신 초안을 메일 화면의 답장 작성으로 여는 주소(FE-5 메일 화면이 reply · draft를 읽는다) */
export function replyDraftPath(mailId: MailId, text: string): string {
  return `/mail/inbox/${mailId}?reply=1&draft=${encodeURIComponent(text)}`;
}
