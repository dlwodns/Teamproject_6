// 외부 응답([FE 임시] provisional.ts 형식) → 화면용 모델(types.ts).
// 형식이 맞지 않으면 ContractError를 던진다. 고쳐서 넘기거나 모의 데이터로 바꾸지 않는다.
import { ContractError } from './errors.ts';
import type { ProvisionalContact, ProvisionalDashboardResponse, ProvisionalMail, ProvisionalTask } from './provisional.ts';
import {
  CATEGORIES,
  TASK_STATUSES,
  type Category,
  type Contact,
  type DashboardSource,
  type DataOrigin,
  type Mail,
  type MailId,
  type Task,
  type TaskId,
  type TaskStatus,
} from './types.ts';

// 시간대가 반드시 붙은 ISO 시각만 받는다. 시간대가 없으면 브라우저 시간대로 읽혀 값이 바뀌므로 거절한다(D47).
const ISO_WITH_OFFSET = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})$/;

export function parseOffsetTime(value: unknown, field: string): number {
  if (typeof value !== 'string' || !ISO_WITH_OFFSET.test(value)) {
    throw new ContractError(`${field}: 시간대가 붙은 ISO 시각이 아니다 (받은 값 종류: ${typeof value})`);
  }
  const ms = Date.parse(value);
  if (Number.isNaN(ms)) throw new ContractError(`${field}: 읽을 수 없는 시각`);
  return ms;
}

function parseOptionalTime(value: unknown, field: string): number | null {
  return value === null || value === undefined ? null : parseOffsetTime(value, field);
}

/**
 * 검증 전 응답 객체. 키는 임시 DTO(provisional.ts)의 필드 이름으로만 읽을 수 있고 값은 unknown이다.
 * DTO 필드 이름이 바뀌면 여기서 읽는 이름도 컴파일 오류로 드러난다. 값은 아래 헬퍼로 하나씩 검증한다.
 */
type Unchecked<T> = { readonly [K in keyof T]?: unknown };

function record<T>(value: unknown, field: string): Unchecked<T> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new ContractError(`${field}: 객체가 아니다`);
  }
  return value as Unchecked<T>;
}

function list(value: unknown, field: string): unknown[] {
  if (!Array.isArray(value)) throw new ContractError(`${field}: 배열이 아니다`);
  return value;
}

function str(value: unknown, field: string): string {
  if (typeof value !== 'string') throw new ContractError(`${field}: 문자열이 아니다`);
  return value;
}

function optStr(value: unknown, field: string): string | null {
  return value === null || value === undefined ? null : str(value, field);
}

function int(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isInteger(value)) throw new ContractError(`${field}: 정수가 아니다`);
  return value;
}

function bool(value: unknown, field: string): boolean {
  if (typeof value !== 'boolean') throw new ContractError(`${field}: 참/거짓 값이 아니다`);
  return value;
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[], field: string): T {
  if (typeof value !== 'string' || !(allowed as readonly string[]).includes(value)) {
    throw new ContractError(`${field}: 허용하지 않는 값 (받은 값 종류: ${typeof value})`);
  }
  return value as T;
}

function toContact(raw: unknown, i: number): Contact {
  const r = record<ProvisionalContact>(raw, `contacts[${i}]`);
  return {
    email: str(r.email, `contacts[${i}].email`),
    name: optStr(r.name, `contacts[${i}].name`),
    position: optStr(r.position, `contacts[${i}].position`),
    isSuperior: bool(r.is_superior, `contacts[${i}].is_superior`),
    isFavorite: bool(r.is_favorite, `contacts[${i}].is_favorite`),
  };
}

function toMail(raw: unknown, i: number): Mail {
  const r = record<ProvisionalMail>(raw, `mails[${i}]`);
  return {
    id: int(r.id, `mails[${i}].id`) as MailId,
    sourceId: str(r.source_id, `mails[${i}].source_id`),
    direction: oneOf(r.direction, ['received', 'sent'] as const, `mails[${i}].direction`),
    sender: str(r.sender, `mails[${i}].sender`),
    subject: str(r.subject, `mails[${i}].subject`),
    receivedAtMs: parseOffsetTime(r.received_at, `mails[${i}].received_at`),
    // [FE 임시 계약] 미분류는 null 또는 필드 생략 둘 다 받는다(서버 직렬화 방식 미확정). 그 밖의 값은 5분류만
    category: r.category === null || r.category === undefined ? null : oneOf<Category>(r.category, CATEGORIES, `mails[${i}].category`),
  };
}

function toTask(raw: unknown, i: number): Task {
  const r = record<ProvisionalTask>(raw, `tasks[${i}]`);
  return {
    id: int(r.id, `tasks[${i}].id`) as TaskId,
    mailId: int(r.mail_id, `tasks[${i}].mail_id`) as MailId,
    text: str(r.text, `tasks[${i}].text`),
    dueAtMs: parseOptionalTime(r.due_at, `tasks[${i}].due_at`),
    status: oneOf<TaskStatus>(r.status, TASK_STATUSES, `tasks[${i}].status`),
    seenAtMs: parseOptionalTime(r.seen_at, `tasks[${i}].seen_at`),
  };
}

export function toDashboardSource(raw: unknown, origin: DataOrigin): DashboardSource {
  const r = record<ProvisionalDashboardResponse>(raw, '응답');
  return {
    origin,
    asOfMs: parseOffsetTime(r.as_of, 'as_of'),
    contacts: list(r.contacts, 'contacts').map(toContact),
    mails: list(r.mails, 'mails').map(toMail),
    tasks: list(r.tasks, 'tasks').map(toTask),
  };
}
