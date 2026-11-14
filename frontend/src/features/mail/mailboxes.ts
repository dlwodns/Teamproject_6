// 메일 화면 왼쪽 메일함 · 가운데 목록의 판단(wireframe 13-7 · UX-D13). 화면 부품은 이 결과를 그리기만 한다.
// 시각은 데이터 기준 시각(as_of)으로 판단한다 — 모의 데이터(11/6 10:42)와 실제 서버가 같은 규칙을 탄다.
//
// 메일함 주소 이름(#/mail/:box): inbox · tasks · checks · superior · favorite · due · client · waiting · cat-<분류> · acc-<계정>.
// 서버가 그 칸을 보내지 않아 판단할 수 없는 메일함(확인 · 참고 구분 · 거래처 여부 · 응답 대기 · 계정)은 숨긴다(0통으로 보이지 않는다).
import { CATEGORIES, type Category, type Contact, type DashboardSource, type Mail, type Task } from '../../api/types.ts';
import { dueLabel, kstDayNumber } from '../tasks/deadline.ts';

export type FlagKind = 'superior' | 'favorite' | 'client';

/** ui/DueLabel의 종류와 같은 값(이 파일은 node --test로 시험하므로 ui를 불러오지 않는다) */
export type MailDueKind = 'urgent' | 'today' | 'later' | 'none' | 'done' | 'overdue-mail';

export interface DueView {
  kind: MailDueKind;
  text: string;
  /** 화면 읽기 · 말풍선용 전체 시각. 기한이 없거나 ASAP면 null */
  full: string | null;
}

// ── 업무 판단 ──

/** 아직 끝나지 않은 업무: 미처리 · 나중에. 완료 · 제외는 끝난 것 */
export const isOpenTask = (t: Task): boolean => t.status === 'pending' || t.status === 'snoozed';

/** ASAP: 기한 시각은 없고 원문 기한이 ASAP일 때만(components.md 3절 DueLabel) */
export const isAsap = (t: Task): boolean => t.dueAtMs === null && typeof t.dueRaw === 'string' && t.dueRaw.trim().toUpperCase() === 'ASAP';

/** 마감(UX-D13 · UX-D3 긴급 칸과 같은 조건): 미처리 업무 중 기한 지남 · ASAP · 오늘 마감 */
export function isUrgentTask(t: Task, asOfMs: number): boolean {
  if (t.status !== 'pending') return false;
  if (isAsap(t)) return true;
  if (t.dueAtMs === null) return false;
  return t.dueAtMs < asOfMs || kstDayNumber(t.dueAtMs) === kstDayNumber(asOfMs);
}

/** 급한 차례: 기한 지남 → ASAP → 오늘 → 그 뒤 → 기한 없음, 같은 차례면 기한이 이른 것부터 */
function urgencyRank(t: Task, asOfMs: number): number {
  if (isAsap(t)) return 1;
  if (t.dueAtMs === null) return 4;
  if (t.dueAtMs < asOfMs) return 0;
  return kstDayNumber(t.dueAtMs) === kstDayNumber(asOfMs) ? 2 : 3;
}

export function byUrgency(asOfMs: number) {
  return (a: Task, b: Task): number =>
    urgencyRank(a, asOfMs) - urgencyRank(b, asOfMs) || (a.dueAtMs ?? Infinity) - (b.dueAtMs ?? Infinity) || a.id - b.id;
}

/** 업무 한 건의 기한 라벨(UX-D10): 검정 D+N · ASAP / 파랑 오늘 HH:MM / 초록 내일 · 날짜 / 회색 기한 없음 */
export function taskDue(t: Task, asOfMs: number): DueView {
  if (isAsap(t)) return { kind: 'urgent', text: 'ASAP', full: null };
  const d = dueLabel(t.dueAtMs, asOfMs);
  const kind: MailDueKind = d.state === 'overdue' ? 'urgent' : d.state === 'today' ? 'today' : d.state === 'none' ? 'none' : 'later';
  return { kind, text: d.text, full: d.full };
}

// ── 메일 한 통 판단 ──

export interface MailContext {
  asOfMs: number;
  contactsByEmail: Map<string, Contact>;
  tasksByMail: Map<number, Task[]>;
}

export function mailContext(source: Pick<DashboardSource, 'asOfMs' | 'contacts' | 'tasks'>): MailContext {
  const tasksByMail = new Map<number, Task[]>();
  for (const t of source.tasks) {
    const list = tasksByMail.get(t.mailId);
    if (list) list.push(t);
    else tasksByMail.set(t.mailId, [t]);
  }
  return { asOfMs: source.asOfMs, contactsByEmail: new Map(source.contacts.map((c) => [c.email, c])), tasksByMail };
}

export const tasksOf = (ctx: MailContext, mail: Mail): Task[] => ctx.tasksByMail.get(mail.id) ?? [];

/** 보낸 사람 이름(연락처에 이름이 없으면 주소) */
export function senderName(ctx: MailContext, mail: Mail): string {
  return ctx.contactsByEmail.get(mail.sender)?.name?.trim() || mail.sender;
}

/** 플래그 칩(UX-D13): 상급자 → 즐겨찾기 → 거래처. 마감은 칩이 아니라 기한 라벨 · 빠른 보기로만 */
export function mailFlags(ctx: MailContext, mail: Mail): FlagKind[] {
  const c = ctx.contactsByEmail.get(mail.sender);
  if (!c) return [];
  const flags: FlagKind[] = [];
  if (c.isSuperior) flags.push('superior');
  if (c.isFavorite) flags.push('favorite');
  if (c.isClient === true) flags.push('client');
  return flags;
}

/** 업무 메일인가: 확인 · 참고 구분(lane)이 오면 그것으로, 안 오면 업무가 나온 메일 */
export function isTaskMail(ctx: MailContext, mail: Mail): boolean {
  return mail.lane === undefined ? tasksOf(ctx, mail).length > 0 : mail.lane === '할 일';
}

/** 메일 목록 줄의 라벨(분류 칩 뒤): 업무 N + 가장 급한 기한 / 완료 / 확인 사유 / 참고 */
export type RowStatus =
  | { kind: 'tasks'; open: number; due: DueView | null }
  | { kind: 'done' }
  | { kind: 'reasons'; reasons: string[] }
  | { kind: 'reference' }
  | { kind: 'none' };

export function rowStatus(ctx: MailContext, mail: Mail): RowStatus {
  const tasks = tasksOf(ctx, mail);
  if (mail.lane === '확인') return { kind: 'reasons', reasons: mail.reasons && mail.reasons.length > 0 ? mail.reasons : ['확인'] };
  if (mail.lane === '참고') return { kind: 'reference' };
  if (tasks.length === 0) return { kind: 'none' };
  const open = tasks.filter(isOpenTask);
  if (open.length === 0) return tasks.some((t) => t.status === 'done') ? { kind: 'done' } : { kind: 'none' };
  const pending = open.filter((t) => t.status === 'pending').sort(byUrgency(ctx.asOfMs));
  return { kind: 'tasks', open: open.length, due: pending[0] ? taskDue(pending[0], ctx.asOfMs) : null };
}

/** 안 읽음: 서버가 읽은 시각을 보냈고 그 값이 비었을 때만(칸이 없으면 모름 → 굵게 하지 않는다) */
export const isUnread = (mail: Mail): boolean => mail.readAtMs === null;

// ── 메일함 ──

export interface BoxItem {
  slug: string;
  label: string;
  count: number;
  flag?: FlagKind;
}

export interface BoxSection {
  /** 묶음 제목(첫 묶음은 제목 없음) */
  title: string | null;
  items: BoxItem[];
}

const ACCOUNT_LABELS: Record<string, string> = { 사내: '사내 메일' };
export const accountLabel = (account: string): string => ACCOUNT_LABELS[account] ?? account;

type MailFilter = (mail: Mail) => boolean;

interface BoxDef {
  slug: string;
  label: string;
  /** 응답 대기는 받은 메일이 아니라 보낸 메일 목록이다 */
  kind: 'mails' | 'waiting';
  filter: MailFilter;
  flag?: FlagKind;
}

const received = (source: DashboardSource) => source.mails.filter((m) => m.direction === 'received');

/** 지금 데이터로 보일 수 있는 메일함 전부(차례대로). 판단할 칸이 없는 메일함은 빠진다 */
function boxDefs(source: DashboardSource, ctx: MailContext): BoxDef[] {
  const mails = received(source);
  const contact = (m: Mail) => ctx.contactsByEmail.get(m.sender);
  const defs: BoxDef[] = [
    { slug: 'inbox', label: '받은편지함', kind: 'mails', filter: () => true },
    { slug: 'tasks', label: '업무', kind: 'mails', filter: (m) => isTaskMail(ctx, m) },
  ];
  if (mails.some((m) => m.lane !== undefined)) {
    defs.push({ slug: 'checks', label: '확인사항', kind: 'mails', filter: (m) => m.lane === '확인' || m.lane === '참고' });
  }
  defs.push(
    { slug: 'superior', label: '상급자', kind: 'mails', flag: 'superior', filter: (m) => contact(m)?.isSuperior === true },
    { slug: 'favorite', label: '즐겨찾기', kind: 'mails', flag: 'favorite', filter: (m) => contact(m)?.isFavorite === true },
    { slug: 'due', label: '마감', kind: 'mails', filter: (m) => tasksOf(ctx, m).some((t) => isUrgentTask(t, ctx.asOfMs)) },
  );
  if (source.contacts.some((c) => c.isClient !== undefined)) {
    defs.push({ slug: 'client', label: '거래처', kind: 'mails', flag: 'client', filter: (m) => contact(m)?.isClient === true });
  }
  if (source.awaiting !== undefined) defs.push({ slug: 'waiting', label: '응답 대기', kind: 'waiting', filter: () => false });
  for (const c of CATEGORIES) defs.push({ slug: `cat-${c}`, label: c, kind: 'mails', filter: (m) => m.category === c });
  for (const a of accountsOf(mails)) defs.push({ slug: `acc-${a}`, label: accountLabel(a), kind: 'mails', filter: (m) => m.account === a });
  return defs;
}

/** 메일에 나온 계정(처음 나온 차례). 계정 칸이 없으면 빈 목록 → 계정 묶음을 숨긴다 */
export function accountsOf(mails: readonly Mail[]): string[] {
  const seen: string[] = [];
  for (const m of mails) if (typeof m.account === 'string' && m.account !== '' && !seen.includes(m.account)) seen.push(m.account);
  return seen;
}

const SECTION_OF = (slug: string): string | null => {
  if (slug === 'inbox' || slug === 'tasks' || slug === 'checks') return null;
  if (slug.startsWith('cat-')) return '분류';
  if (slug.startsWith('acc-')) return '계정';
  return '빠른 보기';
};

function countOf(def: BoxDef, source: DashboardSource): number {
  return def.kind === 'waiting' ? (source.awaiting?.length ?? 0) : received(source).filter(def.filter).length;
}

/** 왼쪽 메일함: 묶음별 이름 · 건수 */
export function mailboxSections(source: DashboardSource, ctx = mailContext(source)): BoxSection[] {
  const sections: BoxSection[] = [];
  for (const def of boxDefs(source, ctx)) {
    const title = SECTION_OF(def.slug);
    let section = sections.find((s) => s.title === title);
    if (!section) {
      section = { title, items: [] };
      sections.push(section);
    }
    section.items.push({ slug: def.slug, label: def.label, count: countOf(def, source), ...(def.flag ? { flag: def.flag } : {}) });
  }
  return sections;
}

export interface ResolvedBox {
  slug: string;
  label: string;
  kind: 'mails' | 'waiting';
  /** 받은 시각 최근 순 */
  mails: Mail[];
}

/** 주소의 메일함 이름 → 메일함. 모르는 이름 · 지금 숨긴 메일함은 받은편지함 */
export function resolveBox(source: DashboardSource, slug: string | undefined, ctx = mailContext(source)): ResolvedBox {
  const defs = boxDefs(source, ctx);
  const def = defs.find((d) => d.slug === slug) ?? defs[0]!;
  const mails = def.kind === 'waiting' ? [] : received(source).filter(def.filter).sort((a, b) => b.receivedAtMs - a.receivedAtMs || b.id - a.id);
  return { slug: def.slug, label: def.label, kind: def.kind, mails };
}

/** 주소 이름이 분류 메일함인가(분류 이름 확인용) */
export const isCategory = (v: string): v is Category => (CATEGORIES as readonly string[]).includes(v);

// ── 시각 표시 ──

const pad = (n: number) => String(n).padStart(2, '0');
const KST = 9 * 3600_000;

/** 목록 줄 시각: 기준일과 같은 날이면 HH:MM, 아니면 M/D HH:MM (KST) */
export function formatListTime(ms: number, asOfMs: number): string {
  const d = new Date(ms + KST);
  const time = `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
  return kstDayNumber(ms) === kstDayNumber(asOfMs) ? time : `${d.getUTCMonth() + 1}/${d.getUTCDate()} ${time}`;
}

/** 메일함 열고 닫기 단축키 표시: Mac은 ⌘B, 그 밖은 Ctrl B */
export function mailboxShortcutLabel(platform: string): string {
  return /mac|iphone|ipad/i.test(platform) ? '⌘B' : 'Ctrl B';
}
