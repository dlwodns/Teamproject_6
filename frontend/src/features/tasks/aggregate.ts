// 대시보드 집계. 숫자는 모두 실제 목록에서 센다(기대값 상수는 테스트에서만 쓴다).
//
// 상태 기준 [FE-1 임시] — 구조도 5절 상태 표를 따르되 완료율 분모는 문서에 없어 여기서 정했다.
// - 미처리(pending): 칸 · 미처리 수에 포함
// - 완료(done): 완료 수 · 완료율에만
// - 제외(excluded): 화면에 보이지 않음. 완료율 분모에서도 뺀다
// - 나중에(snoozed): 칸에서 빠짐. 아직 끝나지 않은 일이라 완료율 분모에는 넣는다
// - 완료율 = 완료 ÷ (미처리 + 나중에 + 완료)
//
// 칸 [FE-1]
// - 왼쪽 '우선 확인': 기한(지남 · 오늘 · 내일) · 상급자 · 즐겨찾기 — 미처리 업무만
// - 오른쪽 '업무 성격': 회신 · 요청 · 검토 · 기타 — 업무가 속한 메일의 category로 정한다(tasks에는 분류 칸이 없다)
// - 같은 업무가 여러 칸에 들어갈 수 있다. 칸 건수를 더해 전체 업무 수로 쓰지 않는다.
import type { Category, Contact, DashboardSource, Mail, MailId, Task, TaskId, TaskStatus } from '../../api/types.ts';
import { dueState, type DueState } from './deadline.ts';

/**
 * 공지 분류 메일에 업무가 있을 때 오른쪽 칸 배정 [FE-1 임시 정책].
 * D40은 공지 메일이 업무를 만들지 않고 대시보드에서 '공지' 칸을 뺀다고만 정했고, 그래도 업무가 생긴 경우의 칸은 정하지 않았다.
 * 누락 방지(D13)를 우선해 '기타'에 넣는다. 'exclude'로 바꾸면 오른쪽 칸에서만 빠지고 업무 수 · 왼쪽 칸에는 남는다.
 */
export type NoticeTaskPolicy = 'other' | 'exclude';
export const NOTICE_TASK_POLICY = 'other' as NoticeTaskPolicy;

export const NATURE_COLUMNS = ['회신', '요청', '검토', '기타'] as const;
export type NatureColumnKey = (typeof NATURE_COLUMNS)[number];

export const PRIORITY_COLUMNS = ['due', 'superior', 'favorite'] as const;
export type PriorityColumnKey = (typeof PRIORITY_COLUMNS)[number];

export const PRIORITY_LABELS: Record<PriorityColumnKey, string> = { due: '기한', superior: '상급자', favorite: '즐겨찾기' };

export interface TaskView {
  task: Task;
  mail: Mail;
  sender: Contact | undefined;
  due: DueState;
}

export interface ColumnView<K extends string> {
  key: K;
  label: string;
  items: TaskView[];
  overdue: number;
}

export interface DashboardView {
  asOfMs: number;
  mailCount: number;
  mailsWithoutTask: number;
  taskCount: number; // 고유 업무 레코드 수(상태 무관)
  status: Record<TaskStatus, number>;
  completion: { done: number; denominator: number; percent: number | null };
  due: { overdue: number; todayRemaining: number; tomorrow: number; soon: number };
  priority: ColumnView<PriorityColumnKey>[];
  nature: ColumnView<NatureColumnKey>[];
  notice: { policy: NoticeTaskPolicy; pendingTasks: number };
  unclassifiedPendingTasks: number;
}

export function natureColumnOf(category: Category | null): NatureColumnKey | null {
  if (category === null) return '기타'; // 분류 전 메일의 업무도 놓치지 않게 기타에 둔다
  if (category === '공지') return NOTICE_TASK_POLICY === 'other' ? '기타' : null;
  return category;
}

const DUE_ORDER: Record<DueState, number> = { overdue: 0, today: 1, tomorrow: 2, later: 3, none: 4 };

function byUrgency(a: TaskView, b: TaskView): number {
  return (
    DUE_ORDER[a.due] - DUE_ORDER[b.due] ||
    (a.task.dueAtMs ?? Infinity) - (b.task.dueAtMs ?? Infinity) ||
    a.task.id - b.task.id
  );
}

function column<K extends string>(key: K, label: string, items: TaskView[]): ColumnView<K> {
  const sorted = [...items].sort(byUrgency);
  return { key, label, items: sorted, overdue: sorted.filter((v) => v.due === 'overdue').length };
}

export function buildDashboard(src: DashboardSource): DashboardView {
  const mails = new Map<MailId, Mail>();
  for (const m of src.mails) {
    if (mails.has(m.id)) throw new Error(`메일 id 중복: ${m.id}`);
    mails.set(m.id, m);
  }
  const contacts = new Map(src.contacts.map((c) => [c.email, c]));
  const seen = new Set<TaskId>();
  const views: TaskView[] = src.tasks.map((task) => {
    if (seen.has(task.id)) throw new Error(`업무 id 중복: ${task.id}`);
    seen.add(task.id);
    const mail = mails.get(task.mailId);
    if (!mail) throw new Error(`업무 ${task.id}의 메일 ${task.mailId}가 목록에 없다`);
    return { task, mail, sender: contacts.get(mail.sender), due: dueState(task.dueAtMs, src.asOfMs) };
  });

  const status: Record<TaskStatus, number> = { pending: 0, done: 0, excluded: 0, snoozed: 0 };
  for (const v of views) status[v.task.status] += 1;
  const denominator = status.pending + status.snoozed + status.done;

  const pending = views.filter((v) => v.task.status === 'pending');
  const countDue = (s: DueState) => pending.filter((v) => v.due === s).length;
  const due = { overdue: countDue('overdue'), todayRemaining: countDue('today'), tomorrow: countDue('tomorrow'), soon: 0 };
  due.soon = due.todayRemaining + due.tomorrow;

  const mailIdsWithTask = new Set(src.tasks.map((t) => t.mailId));

  return {
    asOfMs: src.asOfMs,
    mailCount: src.mails.length,
    mailsWithoutTask: src.mails.filter((m) => !mailIdsWithTask.has(m.id)).length,
    taskCount: views.length,
    status,
    completion: {
      done: status.done,
      denominator,
      percent: denominator === 0 ? null : Math.round((status.done / denominator) * 100),
    },
    due,
    priority: [
      column('due', PRIORITY_LABELS.due, pending.filter((v) => v.due === 'overdue' || v.due === 'today' || v.due === 'tomorrow')),
      column('superior', PRIORITY_LABELS.superior, pending.filter((v) => v.sender?.isSuperior === true)),
      column('favorite', PRIORITY_LABELS.favorite, pending.filter((v) => v.sender?.isFavorite === true)),
    ],
    nature: NATURE_COLUMNS.map((key) => column(key, key, pending.filter((v) => natureColumnOf(v.mail.category) === key))),
    notice: { policy: NOTICE_TASK_POLICY, pendingTasks: pending.filter((v) => v.mail.category === '공지').length },
    unclassifiedPendingTasks: pending.filter((v) => v.mail.category === null).length,
  };
}

/** 표시용 발신자 이름. 예: 김민석 팀장 */
export function senderLabel(v: TaskView): string {
  const c = v.sender;
  if (!c?.name) return v.mail.sender;
  return c.position ? `${c.name} ${c.position}` : c.name;
}
