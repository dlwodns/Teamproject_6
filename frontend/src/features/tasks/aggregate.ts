// 대시보드 v3.1 집계 (wireframe 13-1 · 13-3 · UX-D1 ~ UX-D3 · FE-D10). 화면 부품 밖 순수 함수라 node --test로 시험한다.
// 숫자는 모두 실제 목록에서 센다(기대값 상수는 테스트에서만 쓴다).
//
// 상태 기준
// - N1 업무 수: 메일을 받은 날(KST) 기준. 전체 = 제외가 아닌 업무, 처리 = 완료, 미처리 = 전체 − 처리(미처리 + 나중에)
// - 긴급 · 유형 칸: 미처리(pending)만. 나중에 · 완료 · 제외는 보이지 않는다
// - 같은 업무가 긴급과 유형 칸에 함께 보일 수 있다(중복 허용). 칸 건수를 더해 업무 수로 쓰지 않는다
//
// 유형 칸(Y1~Y4): 업무 유형(task.type)이 오면 그것으로, 안 오면 업무가 나온 메일의 분류(category)로 정한다.
// '공지'와 분류 전(null)은 '기타'에 둔다(FE-D10 · UX-D3, 누락 방지 D13).
//
// 응답 정합성: 메일 목록 안 id 중복, 업무 목록 안 id 중복은 계약 위반 → ContractError(대시보드 전체 오류).
// 업무가 가리키는 메일이 없으면 업무는 버리지 않는다: 긴급 칸에는 넣고(기한은 업무 값), 받은 날 · 발신자는 지어내지 않는다
// (N1에서 빠지고, 유형은 task.type이 있을 때만, 줄의 발신자 자리는 '메일 정보 없음').
import { ContractError } from '../../api/errors.ts';
import type { Awaiting, Category, Contact, DashboardSource, Mail, MailId, Task, TaskId } from '../../api/types.ts';
import { formatKstDay, formatKstTime, kstDayNumber, kstMondayOf, taskDueBadge, type TaskDueBadge } from './deadline.ts';

export const TYPE_COLUMNS = ['회신', '요청', '검토', '기타'] as const;
export type TypeColumnKey = (typeof TYPE_COLUMNS)[number];

/** 업무 줄 하나(R)에 필요한 것 */
export interface TaskRowModel {
  id: TaskId;
  mailId: MailId;
  text: string;
  /** 새 업무 점: 사용자가 아직 보지 않은 업무(seen_at 없음) */
  isNew: boolean;
  /** 발신자 표시 이름. 메일이 응답에 없으면 null('메일 정보 없음') */
  sender: string | null;
  type: TypeColumnKey | null;
  due: TaskDueBadge;
  dueAtMs: number | null;
}

/** 확인사항 줄(I1) — 업무가 아닌 메일 */
export type CheckLane = '확인' | '참고';
export const CHECK_LANES: readonly CheckLane[] = ['확인', '참고'];

export interface CheckItem {
  mailId: MailId;
  lane: CheckLane;
  subject: string;
  sender: string;
  /** 확인: 확인 사유(완료 보고 · 결과 회신 …), 참고: 공지 · 공유. 사유가 없으면 null */
  chip: string | null;
  receivedAtMs: number;
  /** 오늘 받았으면 HH:MM, 아니면 M/D(요일) */
  whenText: string;
  unread: boolean;
}

export interface ReceivedCounts {
  total: number;
  done: number;
  open: number;
}

export interface DashboardModel {
  asOfMs: number;
  /** 기준 시각의 KST 날짜 번호 */
  today: number;
  /** 업무별 받은 날 · 상태(N1 집계용). 제외 업무와 메일이 없는(받은 날을 모르는) 업무는 넣지 않는다 */
  received: { day: number; status: Task['status'] }[];
  urgent: TaskRowModel[];
  /** 즐겨찾기 칸: 즐겨찾기한 연락처가 보낸 메일의 미처리 업무(기한 순). 긴급 · 유형 칸과 겹쳐 보일 수 있다 */
  favorites: TaskRowModel[];
  types: Record<TypeColumnKey, TaskRowModel[]>;
  /**
   * 유형 칸 건수. 긴급 업무는 긴급 칸과 유형 칸에 함께 보이지만 세기는 긴급 칸에서만 한다(11-13 결정).
   * own = 그 유형에서 긴급이 아닌 업무 수(칸 머리 숫자), urgent = 같이 보이는 긴급 업무 수.
   * 그래서 긴급 + 유형 칸 숫자의 합 = 미처리 업무 수(유형이 있는 것)다
   */
  typeCounts: Record<TypeColumnKey, { own: number; urgent: number }>;
  /** 확인사항. null = 메일은 있는데 메일 칸(lane)이 하나도 없음(서버가 안 보냄) → 카드를 숨긴다 */
  checks: Record<CheckLane, CheckItem[]> | null;
  /** 응답 대기. null = 서버가 보내지 않음 → 카드를 숨긴다 */
  awaiting: Awaiting[] | null;
  /** 분류 대기(분류 전) 받은 메일 수 */
  unclassifiedMails: number;
}

/** 표시용 이름. 예: 김민준 팀장. 연락처에 이름이 없으면 메일 주소 */
export function senderName(contact: Contact | undefined, email: string): string {
  if (!contact?.name) return email;
  return contact.position ? `${contact.name} ${contact.position}` : contact.name;
}

function toTypeColumn(category: Category | null): TypeColumnKey {
  return category === null || category === '공지' ? '기타' : category;
}

/** 업무가 들어갈 유형 칸. 업무 유형이 없고 메일도 없으면 정할 수 없다(null) */
export function typeColumnOf(task: Pick<Task, 'type'>, mail: Pick<Mail, 'category'> | undefined): TypeColumnKey | null {
  if (task.type !== undefined && task.type !== null) return toTypeColumn(task.type);
  if (mail) return toTypeColumn(mail.category);
  return null;
}

// ── 정렬 ──

function urgentRank(r: TaskRowModel): number {
  if (r.due.state === 'overdue') return 0;
  if (r.due.state === 'asap') return 1;
  return 2;
}

/** 긴급(U1): 기한 지남(오래된 순) → ASAP → 오늘 마감(시각 순). 같으면 업무 번호 순 */
export function compareUrgent(a: TaskRowModel, b: TaskRowModel): number {
  return urgentRank(a) - urgentRank(b) || (a.dueAtMs ?? 0) - (b.dueAtMs ?? 0) || a.id - b.id;
}

const TYPE_RANK: Record<TaskDueBadge['state'], number> = { overdue: 0, asap: 1, today: 2, tomorrow: 2, later: 2, raw: 3, none: 4 };

/** 유형 칸: 기한 지남 → ASAP → 기한 이른 순 → 시각 모르는 원문 기한 → 기한 없음 */
export function compareByDue(a: TaskRowModel, b: TaskRowModel): number {
  return TYPE_RANK[a.due.state] - TYPE_RANK[b.due.state] || (a.dueAtMs ?? 0) - (b.dueAtMs ?? 0) || a.id - b.id;
}

/** 긴급 = 기한 지남 · ASAP · 오늘 마감(아직 안 지남) */
export function isUrgent(r: TaskRowModel): boolean {
  return r.due.state === 'overdue' || r.due.state === 'asap' || r.due.state === 'today';
}

// ── 만들기 ──

function assertUniqueIds(src: DashboardSource): void {
  const mailIds = new Set<MailId>();
  for (const m of src.mails) {
    if (mailIds.has(m.id)) throw new ContractError(`메일 id 중복: ${m.id}`);
    mailIds.add(m.id);
  }
  const taskIds = new Set<TaskId>();
  for (const t of src.tasks) {
    if (taskIds.has(t.id)) throw new ContractError(`업무 id 중복: ${t.id}`);
    taskIds.add(t.id);
  }
}

function checkChip(mail: Mail, lane: CheckLane): string | null {
  if (lane === '참고') return mail.category === '공지' ? '공지' : '공유';
  return mail.reasons?.[0] ?? null;
}

export function buildDashboard(src: DashboardSource): DashboardModel {
  assertUniqueIds(src);
  const mails = new Map(src.mails.map((m) => [m.id, m]));
  const contacts = new Map(src.contacts.map((c) => [c.email, c]));
  const today = kstDayNumber(src.asOfMs);

  const received: DashboardModel['received'] = [];
  const pendingRows: TaskRowModel[] = [];
  const favorites: TaskRowModel[] = [];
  for (const task of src.tasks) {
    const mail = mails.get(task.mailId);
    if (mail && task.status !== 'excluded') received.push({ day: kstDayNumber(mail.receivedAtMs), status: task.status });
    if (task.status !== 'pending') continue;
    const row: TaskRowModel = {
      id: task.id,
      mailId: task.mailId,
      text: task.text,
      isNew: task.seenAtMs === null,
      sender: mail ? senderName(contacts.get(mail.sender), mail.sender) : null,
      type: typeColumnOf(task, mail),
      due: taskDueBadge(task.dueAtMs, task.dueRaw, src.asOfMs),
      dueAtMs: task.dueAtMs,
    };
    pendingRows.push(row);
    if (mail && contacts.get(mail.sender)?.isFavorite) favorites.push(row);
  }

  const types = { 회신: [], 요청: [], 검토: [], 기타: [] } as Record<TypeColumnKey, TaskRowModel[]>;
  for (const r of pendingRows) if (r.type) types[r.type].push(r);
  for (const k of TYPE_COLUMNS) types[k].sort(compareByDue);

  const receivedMails = src.mails.filter((m) => m.direction === 'received');
  let checks: DashboardModel['checks'] = null;
  // 메일이 하나도 없으면 확인사항도 정말 없으므로 '없음'으로 보인다. 메일이 있는데 lane이 하나도 없으면 서버가 안 보낸 것 → 숨김
  if (src.mails.length === 0 || src.mails.some((m) => m.lane !== undefined)) {
    const byLane: Record<CheckLane, CheckItem[]> = { 확인: [], 참고: [] };
    for (const m of receivedMails) {
      if (m.lane !== '확인' && m.lane !== '참고') continue;
      const day = kstDayNumber(m.receivedAtMs);
      byLane[m.lane].push({
        mailId: m.id,
        lane: m.lane,
        subject: m.subject,
        sender: senderName(contacts.get(m.sender), m.sender),
        chip: checkChip(m, m.lane),
        receivedAtMs: m.receivedAtMs,
        whenText: day === today ? formatKstTime(m.receivedAtMs) : formatKstDay(day),
        unread: m.readAtMs === null,
      });
    }
    // 최근에 받은 메일부터
    for (const lane of CHECK_LANES) byLane[lane].sort((a, b) => b.receivedAtMs - a.receivedAtMs || b.mailId - a.mailId);
    checks = byLane;
  }

  const awaiting =
    src.awaiting === undefined ? null : [...src.awaiting].sort((a, b) => b.days - a.days || a.sentAtMs - b.sentAtMs || a.mailId - b.mailId);

  return {
    asOfMs: src.asOfMs,
    today,
    received,
    urgent: pendingRows.filter(isUrgent).sort(compareUrgent),
    favorites: favorites.sort(compareByDue),
    types,
    typeCounts: Object.fromEntries(
      TYPE_COLUMNS.map((k) => {
        const urgent = types[k].filter(isUrgent).length;
        return [k, { own: types[k].length - urgent, urgent }];
      }),
    ) as DashboardModel['typeCounts'],
    checks,
    awaiting,
    unclassifiedMails: receivedMails.filter((m) => m.category === null).length,
  };
}

// ── N1 업무 수 ──

export type Period = 'today' | 'week' | 'day';

export const PERIOD_OPTIONS: readonly { value: Period; label: string }[] = [
  { value: 'today', label: '오늘' },
  { value: 'week', label: '이번 주' },
  { value: 'day', label: '날짜' },
];

/** 받은 날 범위(KST 날짜 번호, 양 끝 포함) */
export interface DayRange {
  from: number;
  to: number;
}

/** 오늘 = 기준일, 이번 주 = 그 주 월요일 ~ 기준일, 날짜 = 고른 하루 */
export function periodRange(period: Period, today: number, pickedDay: number): DayRange {
  if (period === 'today') return { from: today, to: today };
  if (period === 'week') return { from: kstMondayOf(today), to: today };
  return { from: pickedDay, to: pickedDay };
}

/** 카드 위 작은 글자. 예: 오늘 11/6(금) · 11/2(월) ~ 11/6(금) · 11/5(목) */
export function periodLabel(period: Period, range: DayRange): string {
  if (period === 'today') return `오늘 ${formatKstDay(range.from)}`;
  if (period === 'week' && range.from !== range.to) return `${formatKstDay(range.from)} ~ ${formatKstDay(range.to)}`;
  return formatKstDay(range.from);
}

/** '날짜'를 처음 고르면 전날부터(V-4) */
export function defaultPickedDay(today: number): number {
  return today - 1;
}

/** 날짜 ◀ ▶: 기준일 뒤로는 가지 않는다 */
export function stepDay(day: number, delta: -1 | 1, today: number): number {
  return Math.min(day + delta, today);
}

export function countReceived(model: Pick<DashboardModel, 'received'>, range: DayRange): ReceivedCounts {
  let total = 0;
  let done = 0;
  for (const r of model.received) {
    if (r.day < range.from || r.day > range.to) continue;
    total += 1;
    if (r.status === 'done') done += 1;
  }
  return { total, done, open: total - done };
}

/** 처리 비율 막대 폭(0~100). 업무가 없으면 0 */
export function doneRatioPercent(c: ReceivedCounts): number {
  return c.total === 0 ? 0 : Math.round((c.done / c.total) * 100);
}

/** 더보기 사이드바 제목. 예: 요청 · 6 */
export function moreTitle(name: string, count: number): string {
  return `${name} · ${count}`;
}
