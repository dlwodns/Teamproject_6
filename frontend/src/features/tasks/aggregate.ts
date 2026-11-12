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
//
// 응답 정합성 [FE-1 임시 계약, be3_contract_comparison.md 4절]
// - 메일 목록 안 mail.id 중복, 업무 목록 안 task.id 중복은 응답 계약 위반 → ContractError(대시보드 전체 오류).
//   두 목록은 따로 검사한다: mail.id = 1과 task.id = 1은 함께 있어도 된다
// - 업무가 가리키는 메일이 목록에 없으면(계약 위반이지만 방어): 업무는 버리지 않고 '메일 정보 없음'으로 둔다.
//   업무 자체 값(상태 · 기한)으로 세는 집계 · 기한 칸에는 넣고, 메일이 있어야 정할 수 있는 칸(상급자 · 즐겨찾기 · 업무 성격)에는
//   넣지 않는다(분류 · 발신자를 지어내지 않음). 해당 업무는 missingMail.tasks로 따로 보여 준다.
import { ContractError } from '../../api/errors.ts';
import type { Category, Contact, DashboardSource, Mail, MailId, Task, TaskId, TaskStatus } from '../../api/types.ts';
import { dueLabel, type DueLabel, type DueState } from './deadline.ts';

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

interface TaskViewBase {
  task: Task;
  due: DueState;
  dueLabel: DueLabel;
}

/** 업무가 가리키는 메일이 목록에 있다. */
export interface TaskWithMail extends TaskViewBase {
  mailState: 'found';
  mail: Mail;
  sender: Contact | undefined; // 연락처 목록에 없는 발신자면 undefined
}

/** 업무가 가리키는 메일이 목록에 없다(응답 계약 위반 방어). 분류 · 발신자는 알 수 없다. */
export interface TaskMissingMail extends TaskViewBase {
  mailState: 'missing';
  mail: null;
  sender: null;
}

export type TaskView = TaskWithMail | TaskMissingMail;

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
  /** 메일 정보를 불러오지 못한 업무(제외 상태 빼고). 길이 = 영향받은 고유 업무 수 */
  missingMail: { tasks: TaskMissingMail[] };
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
  // 중복은 Map에 넣기 전에 찾는다(뒤 항목이 앞 항목을 조용히 덮지 않게)
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
  const mails = new Map(src.mails.map((m) => [m.id, m]));
  const contacts = new Map(src.contacts.map((c) => [c.email, c]));
  const views: TaskView[] = src.tasks.map((task): TaskView => {
    const label = dueLabel(task.dueAtMs, src.asOfMs);
    const due = label.state;
    const mail = mails.get(task.mailId);
    return mail
      ? { task, due, dueLabel: label, mailState: 'found', mail, sender: contacts.get(mail.sender) }
      : { task, due, dueLabel: label, mailState: 'missing', mail: null, sender: null };
  });

  const status: Record<TaskStatus, number> = { pending: 0, done: 0, excluded: 0, snoozed: 0 };
  for (const v of views) status[v.task.status] += 1;
  const denominator = status.pending + status.snoozed + status.done;

  const pending = views.filter((v) => v.task.status === 'pending');
  const pendingWithMail = pending.filter((v): v is TaskWithMail => v.mailState === 'found');
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
      column('superior', PRIORITY_LABELS.superior, pendingWithMail.filter((v) => v.sender?.isSuperior === true)),
      column('favorite', PRIORITY_LABELS.favorite, pendingWithMail.filter((v) => v.sender?.isFavorite === true)),
    ],
    nature: NATURE_COLUMNS.map((key) => column(key, key, pendingWithMail.filter((v) => natureColumnOf(v.mail.category) === key))),
    notice: { policy: NOTICE_TASK_POLICY, pendingTasks: pendingWithMail.filter((v) => v.mail.category === '공지').length },
    unclassifiedPendingTasks: pendingWithMail.filter((v) => v.mail.category === null).length,
    missingMail: {
      tasks: views.filter((v): v is TaskMissingMail => v.mailState === 'missing' && v.task.status !== 'excluded').sort(byUrgency),
    },
  };
}

/** 표시용 발신자 이름. 예: 김민석 팀장 */
export function senderLabel(v: TaskWithMail): string {
  const c = v.sender;
  if (!c?.name) return v.mail.sender;
  return c.position ? `${c.name} ${c.position}` : c.name;
}
