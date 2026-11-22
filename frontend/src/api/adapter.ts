// 외부 응답([FE 임시] provisional.ts 형식) → 화면용 모델(types.ts).
// 형식이 맞지 않으면 ContractError를 던진다. 고쳐서 넘기거나 모의 데이터로 바꾸지 않는다.
import { ContractError } from './errors.ts';
import {
  AGENT_KINDS,
  AGENT_PROPOSED_KINDS,
  MAILING_LIST_KINDS,
  MEMORY_FACT_KINDS,
  NOTIFICATION_KINDS,
  SUGGESTION_RULES,
  type AgentMemory,
  type AgentSettings,
  type HideResult,
  type HistoryItem,
  type HistoryList,
  type MemoryChange,
  type MemoryMePatch,
  type MemoryOrigin,
  type MemoryPersonPatch,
  type Suggestion,
  type SuggestionButton,
  type SuggestionList,
  type ActionResult,
  type AgentCommandRequest,
  type AgentPerson,
  type AgentResult,
  type AgentTarget,
  type AppNotification,
  type BulkPreview,
  type BulkPreviewRequest,
  type ContactPatch,
  type MailDetail,
  type MailPatch,
  type MailSummary,
  type MailTranslation,
  type UploadedFile,
  type NotificationId,
  type ComposeMode,
  type MailAttachment,
  type OutlookSearchHit,
  type ReplyDraft,
  type ScheduledSend,
  type SendResult,
  type ReplyTemplate,
  type PolishedReply,
  type SentReply,
  type Settings,
  type SettingsPatch,
  type StatusChange,
  type TaskState,
  type UndoResult,
} from './contract.ts';
import type {
  ProvisionalAgentMemory,
  ProvisionalAgentSettings,
  ProvisionalHideResult,
  ProvisionalHistoryItem,
  ProvisionalHistoryList,
  ProvisionalMemoryChange,
  ProvisionalMemoryFact,
  ProvisionalMemoryMe,
  ProvisionalMemoryPerson,
  ProvisionalOrigin,
  ProvisionalSuggestion,
  ProvisionalSuggestionButton,
  ProvisionalSuggestionList,
  ProvisionalActionResult,
  ProvisionalAgentPerson,
  ProvisionalAgentResult,
  ProvisionalAgentSummaryItem,
  ProvisionalAgentTarget,
  ProvisionalAwaiting,
  ProvisionalContact,
  ProvisionalDashboardResponse,
  ProvisionalMail,
  ProvisionalMailDetail,
  ProvisionalMailPatch,
  ProvisionalMailSummary,
  ProvisionalNotification,
  ProvisionalNotificationsResponse,
  ProvisionalPreviewResult,
  ProvisionalReplyRequest,
  ProvisionalSentReply,
  ProvisionalSettings,
  ProvisionalTask,
  ProvisionalTaskState,
  ProvisionalTemplate,
  ProvisionalUndoResult,
} from './provisional.ts';
import {
  CATEGORIES,
  LANES,
  TASK_STATUSES,
  type Awaiting,
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
// FE-12 캘린더(BE-15). 다른 작업과 import 줄이 겹치지 않게 따로 둔다
import type { AccountSyncResult, MailAccount, MailAccountList } from './contract.ts'; // BE-7 메일 계정
import { CALENDAR_KINDS, type CalendarEventCreate, type CalendarEventResult, type CalendarItem, type CalendarRange } from './contract.ts';
import type { ProvisionalCalendarItem, ProvisionalCalendarRange, ProvisionalEventCreate, ProvisionalEventResult } from './provisional.ts';

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

/** 요청에 넣는 시각: epoch 밀리초 → +09:00이 붙은 한국 시각 ISO(BE-4는 시간대가 없으면 KST로 보지만, 늘 붙여 보낸다) */
export function toKstIso(ms: number): string {
  if (!Number.isFinite(ms)) throw new RangeError('시각이 숫자가 아니다');
  return `${new Date(ms + 9 * 3600_000).toISOString().slice(0, 19)}+09:00`;
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

function strList(value: unknown, field: string): string[] {
  return list(value, field).map((v, i) => str(v, `${field}[${i}]`));
}

function intList(value: unknown, field: string): number[] {
  return list(value, field).map((v, i) => int(v, `${field}[${i}]`));
}

// ── 선택 칸 읽기 ──
// 선택 칸은 화면 일부를 꾸미는 값이라, 모양이 틀려도 응답 전체를 버리지 않는다(필수 칸과 다르게 던지지 않는다).
// 규칙: 칸이 없으면 undefined(화면이 숨김), null이거나 FE가 모르는 값이면 null(화면이 '없음'으로 그림).
// 목록 · 참거짓처럼 null 자리가 없는 칸은 틀린 모양이면 undefined로 본다(틀린 값을 보이느니 숨긴다).

function optEnum<T extends string>(value: unknown, allowed: readonly T[]): T | null | undefined {
  if (value === undefined) return undefined;
  return typeof value === 'string' && (allowed as readonly string[]).includes(value) ? (value as T) : null;
}

function optText(value: unknown): string | null | undefined {
  if (value === undefined) return undefined;
  return typeof value === 'string' ? value : null;
}

function optTime(value: unknown): number | null | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== 'string' || !ISO_WITH_OFFSET.test(value)) return null;
  const ms = Date.parse(value);
  return Number.isNaN(ms) ? null : ms;
}

function optBool(value: unknown): boolean | undefined {
  return typeof value === 'boolean' ? value : undefined;
}

// null은 '보냈지만 없음'이라 빈 목록, 배열이 아니면 숨김. 글자가 아닌 항목만 뺀다
function optTextList(value: unknown): string[] | undefined {
  if (value === null) return [];
  if (!Array.isArray(value)) return undefined;
  return value.filter((v): v is string => typeof v === 'string');
}

/** undefined인 키를 지운다. '칸이 없었다'를 키가 없는 것으로 남겨 deepEqual · 'in' 검사와 맞춘다 */
function compact<T extends object>(o: T): T {
  for (const k of Object.keys(o) as (keyof T)[]) if (o[k] === undefined) delete o[k];
  return o;
}

export function toContact(raw: unknown, path: string): Contact {
  const r = record<ProvisionalContact>(raw, path);
  return compact({
    email: str(r.email, `${path}.email`),
    name: optStr(r.name, `${path}.name`),
    position: optStr(r.position, `${path}.position`),
    isSuperior: bool(r.is_superior, `${path}.is_superior`),
    isFavorite: bool(r.is_favorite, `${path}.is_favorite`),
    org: optText(r.org),
    isClient: optBool(r.is_client),
  });
}

function toMail(raw: unknown, path: string): Mail {
  const r = record<ProvisionalMail>(raw, path);
  return compact({
    id: int(r.id, `${path}.id`) as MailId,
    sourceId: str(r.source_id, `${path}.source_id`),
    direction: oneOf(r.direction, ['received', 'sent'] as const, `${path}.direction`),
    sender: str(r.sender, `${path}.sender`),
    subject: str(r.subject, `${path}.subject`),
    receivedAtMs: parseOffsetTime(r.received_at, `${path}.received_at`),
    // [FE 임시 계약] 미분류는 null 또는 필드 생략 둘 다 받는다(서버 직렬화 방식 미확정). 그 밖의 값은 5분류만
    category: r.category === null || r.category === undefined ? null : oneOf<Category>(r.category, CATEGORIES, `${path}.category`),
    lane: optEnum(r.lane, LANES),
    reasons: optTextList(r.reasons),
    to: optTextList(r.to),
    account: optText(r.account),
    lang: optText(r.lang),
    readAtMs: optTime(r.read_at),
    pinnedAtMs: optTime(r.pinned_at),
    folder: optText(r.folder),
    importance: optEnum(r.importance, IMPORTANCE),
  });
}

function toTask(raw: unknown, path: string): Task {
  const r = record<ProvisionalTask>(raw, path);
  return compact({
    id: int(r.id, `${path}.id`) as TaskId,
    mailId: int(r.mail_id, `${path}.mail_id`) as MailId,
    text: str(r.text, `${path}.text`),
    dueAtMs: parseOptionalTime(r.due_at, `${path}.due_at`),
    status: oneOf<TaskStatus>(r.status, TASK_STATUSES, `${path}.status`),
    seenAtMs: parseOptionalTime(r.seen_at, `${path}.seen_at`),
    dueRaw: optText(r.due_raw),
    dueTimeStated: optBool(r.due_time_stated),
    // 업무 유형은 메일 분류와 같은 5분류. 모르는 값은 null(유형 칸에서 '기타'로 몰지 않는다)
    type: optEnum<Category>(r.type, CATEGORIES),
    evidenceText: optText(r.evidence_text),
  });
}

function toAwaiting(raw: unknown, path: string): Awaiting {
  const r = record<ProvisionalAwaiting>(raw, path);
  return {
    mailId: int(r.mail_id, `${path}.mail_id`) as MailId,
    subject: str(r.subject, `${path}.subject`),
    to: str(r.to, `${path}.to`),
    sentAtMs: parseOffsetTime(r.sent_at, `${path}.sent_at`),
    days: int(r.days, `${path}.days`),
  };
}

/** GET /api/awaiting 응답(FE 제안). 이 요청에서는 본 내용이라 형식이 틀리면 ContractError */
export function toAwaitingList(raw: unknown): Awaiting[] {
  return list(raw, '응답').map((a, i) => toAwaiting(a, `[${i}]`));
}

// 대시보드 안의 awaiting은 선택 칸: 없으면 undefined. 한 줄이라도 틀리면 통째로 undefined(일부만 세어 틀린 숫자를 보이지 않는다)
function optAwaiting(value: unknown): Awaiting[] | undefined {
  if (value === undefined || value === null) return undefined;
  try {
    return toAwaitingList(value);
  } catch (e) {
    if (e instanceof ContractError) return undefined;
    throw e;
  }
}

export function toDashboardSource(raw: unknown, origin: DataOrigin): DashboardSource {
  const r = record<ProvisionalDashboardResponse>(raw, '응답');
  return compact({
    origin,
    asOfMs: parseOffsetTime(r.as_of, 'as_of'),
    contacts: list(r.contacts, 'contacts').map((c, i) => toContact(c, `contacts[${i}]`)),
    mails: list(r.mails, 'mails').map((m, i) => toMail(m, `mails[${i}]`)),
    tasks: list(r.tasks, 'tasks').map((t, i) => toTask(t, `tasks[${i}]`)),
    awaiting: optAwaiting(r.awaiting),
  });
}

// ── BE-4 업무 상태(있음) ──

function toTaskState(raw: unknown, path: string): TaskState {
  const r = record<ProvisionalTaskState>(raw, path);
  return {
    id: int(r.id, `${path}.id`) as TaskId,
    status: oneOf<TaskStatus>(r.status, TASK_STATUSES, `${path}.status`),
    doneAtMs: parseOptionalTime(r.done_at, `${path}.done_at`),
    snoozedUntilMs: parseOptionalTime(r.snoozed_until, `${path}.snoozed_until`),
    statusChangedAtMs: parseOptionalTime(r.status_changed_at, `${path}.status_changed_at`),
  };
}

export function toActionResult(raw: unknown): ActionResult {
  const r = record<ProvisionalActionResult>(raw, '응답');
  return {
    actionId: r.action_id === null ? null : int(r.action_id, 'action_id'),
    tasks: list(r.tasks, 'tasks').map((t, i) => toTaskState(t, `tasks[${i}]`)),
  };
}

export function toUndoResult(raw: unknown): UndoResult {
  const r = record<ProvisionalUndoResult>(raw, '응답');
  return {
    actionId: int(r.action_id, 'action_id'),
    undoneActionId: int(r.undone_action_id, 'undone_action_id'),
    tasks: list(r.tasks, 'tasks').map((t, i) => toTaskState(t, `tasks[${i}]`)),
  };
}

export function toBulkPreview(raw: unknown): BulkPreview {
  const r = record<ProvisionalPreviewResult>(raw, '응답');
  return {
    previewId: str(r.preview_id, 'preview_id'),
    expiresAtMs: parseOffsetTime(r.expires_at, 'expires_at'),
    status: oneOf<TaskStatus>(r.status, TASK_STATUSES, 'status'),
    snoozedUntilMs: parseOptionalTime(r.snoozed_until, 'snoozed_until'),
    targets: list(r.targets, 'targets').map((raw, i) => {
      const t = record<ProvisionalPreviewResult['targets'][number]>(raw, `targets[${i}]`);
      return {
        id: int(t.id, `targets[${i}].id`) as TaskId,
        text: str(t.text, `targets[${i}].text`),
        status: oneOf<TaskStatus>(t.status, TASK_STATUSES, `targets[${i}].status`),
      };
    }),
  };
}

// ── BE-11 에이전트 명령(있음, #50) ──

function toAgentTarget(raw: unknown, path: string): AgentTarget {
  const r = record<ProvisionalAgentTarget>(raw, path);
  return {
    id: int(r.id, `${path}.id`) as TaskId,
    mailId: int(r.mail_id, `${path}.mail_id`) as MailId,
    text: str(r.text, `${path}.text`),
    status: oneOf<TaskStatus>(r.status, TASK_STATUSES, `${path}.status`),
    snoozedUntilMs: parseOptionalTime(r.snoozed_until, `${path}.snoozed_until`),
  };
}

function toAgentSummary(raw: unknown): AgentResult['summary'] {
  const r = record<NonNullable<ProvisionalAgentResult['summary']>>(raw, 'summary');
  return {
    items: list(r.items, 'summary.items').map((v, i) => {
      const path = `summary.items[${i}]`;
      const t = record<ProvisionalAgentSummaryItem>(v, path);
      return {
        taskId: int(t.task_id, `${path}.task_id`) as TaskId,
        mailId: int(t.mail_id, `${path}.mail_id`) as MailId,
        text: str(t.text, `${path}.text`),
        dueAtMs: parseOptionalTime(t.due_at, `${path}.due_at`),
        dueRaw: optStr(t.due_raw, `${path}.due_raw`),
        ...(typeof t.due_time_stated === 'boolean' && { dueTimeStated: t.due_time_stated }),
        section: optStr(t.section, `${path}.section`),
      };
    }),
    hint: optStr(r.hint, 'summary.hint'),
    ...summaryExtras(r),
  };
}

/**
 * 조율 중인 칸(T01 백엔드, FE-15): text(브리핑 문장) · refreshing(새로 정리 중). 아직 정해지지 않은 칸이라
 * 형식이 다르면 오류로 막지 않고 없는 것으로 본다. 없으면 키를 넣지 않아 지금 결과와 똑같다
 */
export function summaryExtras(r: { text?: unknown; refreshing?: unknown }): { text?: string | null; refreshing?: boolean } {
  const out: { text?: string | null; refreshing?: boolean } = {};
  if (r.text === null) out.text = null;
  else if (typeof r.text === 'string') out.text = r.text.trim() || null;
  if (typeof r.refreshing === 'boolean') out.refreshing = r.refreshing;
  return out;
}

function toAgentDraft(raw: unknown): AgentResult['draft'] {
  const r = record<NonNullable<ProvisionalAgentResult['draft']>>(raw, 'draft');
  return {
    mailId: int(r.mail_id, 'draft.mail_id') as MailId,
    to: str(r.to, 'draft.to'),
    subject: str(r.subject, 'draft.subject'),
    text: str(r.text, 'draft.text'),
  };
}

function toAgentPerson(raw: unknown): AgentPerson {
  const r = record<ProvisionalAgentPerson>(raw, 'person');
  return {
    name: optStr(r.name, 'person.name'),
    email: str(r.email, 'person.email'),
    position: optStr(r.position, 'person.position'),
    isSuperior: r.is_superior === true,
    isFavorite: r.is_favorite === true,
    facts: (r.facts === undefined ? [] : list(r.facts, 'person.facts')).map((v, i) => {
      const f = record<ProvisionalAgentPerson['facts'][number]>(v, `person.facts[${i}]`);
      return {
        label: str(f.label, `person.facts[${i}].label`),
        value: str(f.value, `person.facts[${i}].value`),
        evidence: optStr(f.evidence, `person.facts[${i}].evidence`),
        mailId: f.mail_id === null || f.mail_id === undefined ? null : (int(f.mail_id, `person.facts[${i}].mail_id`) as MailId),
      };
    }),
    learnOff: r.learn_off === true,
    mails: (r.mails === undefined ? [] : list(r.mails, 'person.mails')).map((v, i) => {
      const m = record<ProvisionalAgentPerson['mails'][number]>(v, `person.mails[${i}]`);
      return {
        mailId: int(m.mail_id, `person.mails[${i}].mail_id`) as MailId,
        subject: str(m.subject, `person.mails[${i}].subject`),
        receivedAtMs: parseOptionalTime(m.received_at, `person.mails[${i}].received_at`),
      };
    }),
    mailTotal: r.mail_total === undefined ? 0 : int(r.mail_total, 'person.mail_total'),
  };
}

/** POST /api/agent/command 응답. FE 제안 kind는 그 칸(summary · awaiting · draft)이 있어야 받는다 */
export function toAgentResult(raw: unknown): AgentResult {
  const r = record<ProvisionalAgentResult>(raw, '응답');
  const kind = oneOf(r.kind, [...AGENT_KINDS, ...AGENT_PROPOSED_KINDS], 'kind');
  const source = optEnum(r.source, ['agent_rule', 'agent_model'] as const) ?? null;
  return compact({
    kind,
    action: optStr(r.action, 'action'),
    actionName: optStr(r.action_name, 'action_name'),
    source,
    title: str(r.title, 'title'),
    targets: r.targets === undefined ? [] : list(r.targets, 'targets').map((t, i) => toAgentTarget(t, `targets[${i}]`)),
    notes: r.notes === undefined ? [] : strList(r.notes, 'notes'),
    actionId: r.action_id === null || r.action_id === undefined ? null : int(r.action_id, 'action_id'),
    previewId: optStr(r.preview_id, 'preview_id'),
    expiresAtMs: parseOptionalTime(r.expires_at, 'expires_at'),
    summary: kind === 'summary' ? toAgentSummary(r.summary) : undefined,
    awaiting: kind === 'awaiting' ? toAwaitingList(r.awaiting) : undefined,
    draft: kind === 'draft' ? toAgentDraft(r.draft) : undefined,
    person: kind === 'person' ? toAgentPerson(r.person) : undefined,
    mails: (r.mails === undefined || r.mails === null ? [] : list(r.mails, 'mails')).map((v, i) => {
      const m = record<NonNullable<ProvisionalAgentResult['mails']>[number]>(v, `mails[${i}]`);
      return {
        mailId: int(m.mail_id, `mails[${i}].mail_id`) as MailId,
        subject: str(m.subject, `mails[${i}].subject`),
        who: str(m.who, `mails[${i}].who`),
        direction: oneOf(m.direction, ['received', 'sent'] as const, `mails[${i}].direction`),
        atMs: parseOptionalTime(m.at, `mails[${i}].at`),
      };
    }),
    lines: r.lines === undefined ? [] : strList(r.lines, 'lines'),
  });
}

/** 명령 요청 본문. 고른 메일 · 직전 결과는 메일 id 정수 목록(없으면 빈 목록) */
export function agentCommandBody(request: AgentCommandRequest): { text: string; selected_mail_ids: number[]; last_result_ids: number[] } {
  return {
    text: request.text,
    selected_mail_ids: [...(request.selectedMailIds ?? [])],
    last_result_ids: [...(request.lastResultIds ?? [])],
    ...reminderCommandFields(request), // FE-16: 고른 리마인더
  };
}

/** BE-4 ExecuteRequest. task_ids가 없으면 미리보기 대상 전부 */
export function executeBody(previewId: string, taskIds?: readonly TaskId[]): { preview_id: string; task_ids?: number[] } {
  return { preview_id: previewId, ...(taskIds === undefined ? {} : { task_ids: [...taskIds] }) };
}

// ── FE 제안 요청 ──

export function toNotification(raw: unknown, path = '응답'): AppNotification {
  const r = record<ProvisionalNotification>(raw, path);
  return {
    id: int(r.id, `${path}.id`) as NotificationId,
    kind: oneOf(r.kind, NOTIFICATION_KINDS, `${path}.kind`),
    title: str(r.title, `${path}.title`),
    body: optStr(r.body, `${path}.body`),
    taskIds: intList(r.task_ids, `${path}.task_ids`) as TaskId[],
    rule: optStr(r.rule, `${path}.rule`),
    scheduledAtMs: parseOptionalTime(r.scheduled_at, `${path}.scheduled_at`),
    readAtMs: parseOptionalTime(r.read_at, `${path}.read_at`),
    answeredAtMs: parseOptionalTime(r.answered_at, `${path}.answered_at`),
    createdAtMs: parseOffsetTime(r.created_at, `${path}.created_at`),
    ...notificationReminderFields(r), // FE-16: type · group · reminder_key
  };
}

export function toNotifications(raw: unknown): AppNotification[] {
  const r = record<ProvisionalNotificationsResponse>(raw, '응답');
  return list(r.items, 'items').map((n, i) => toNotification(n, `items[${i}]`));
}

function toTemplate(raw: unknown, path: string): ReplyTemplate {
  const r = record<ProvisionalTemplate>(raw, path);
  return {
    key: str(r.key, `${path}.key`),
    name: str(r.name, `${path}.name`),
    pattern: str(r.pattern, `${path}.pattern`),
  };
}

export function toSettings(raw: unknown): Settings {
  const r = record<ProvisionalSettings>(raw, '응답');
  return compact({
    remindTime: str(r.remind_time, 'remind_time'),
    eveningTime: r.evening_time === undefined ? undefined : str(r.evening_time, 'evening_time'),
    awaitingReplyDays: int(r.awaiting_reply_days, 'awaiting_reply_days'),
    quietStart: optStr(r.quiet_start, 'quiet_start'),
    quietEnd: optStr(r.quiet_end, 'quiet_end'),
    reduceMotion: bool(r.reduce_motion, 'reduce_motion'),
    sttMode: str(r.stt_mode, 'stt_mode'),
    templates: r.templates === undefined ? undefined : list(r.templates, 'templates').map((t, i) => toTemplate(t, `templates[${i}]`)),
    replyConfirmSkipUntilMs:
      r.reply_confirm_skip_until === undefined ? undefined : parseOptionalTime(r.reply_confirm_skip_until, 'reply_confirm_skip_until'),
    readBody: r.read_body === undefined ? undefined : bool(r.read_body, 'read_body'),
    workStart: r.work_start === undefined ? undefined : str(r.work_start, 'work_start'),
    workEnd: r.work_end === undefined ? undefined : str(r.work_end, 'work_end'),
    workDays: r.work_days === undefined ? undefined : str(r.work_days, 'work_days'),
    awayUntilMs: r.away_until === undefined ? undefined : parseOptionalTime(r.away_until, 'away_until'),
    mailSignature: r.mail_signature === undefined ? undefined : optStr(r.mail_signature, 'mail_signature'),
    mailSignatures: Array.isArray(r.mail_signatures)
      ? r.mail_signatures.map((x, i) => ({
          key: str(x.key, `mail_signatures[${i}].key`),
          name: str(x.name, `mail_signatures[${i}].name`),
          text: str(x.text, `mail_signatures[${i}].text`),
          forNew: x.for_new === true,
          forReply: x.for_reply === true,
        }))
      : undefined,
  });
}

const IMPORTANCE = ['low', 'normal', 'high'] as const;

export function toMailDetail(raw: unknown): MailDetail {
  const r = record<ProvisionalMailDetail>(raw, '응답');
  const mail = toMail(raw, '응답');
  return {
    ...mail,
    to: mail.to ?? [],
    body: typeof r.body === 'string' ? r.body.split('\n') : strList(r.body, 'body'),
    lang: mail.lang ?? null,
    lane: mail.lane ?? null,
    reasons: mail.reasons ?? [],
    tasks: list(r.tasks, 'tasks').map((t, i) => toTask(t, `tasks[${i}]`)),
    summary: r.summary == null ? null : toMailSummary(r.summary),
    bodyHtml: typeof r.body_html === 'string' && r.body_html.trim() ? r.body_html : null,
    cc: Array.isArray(r.cc) ? r.cc.filter((x): x is string => typeof x === 'string') : [],
  };
}

/** 답장 보내기 응답(FE 제안): 저장된 보낸 메일 */
export function toSentReply(raw: unknown): SentReply {
  const r = record<ProvisionalSentReply>(raw, '응답');
  // id null = Outlook으로 나갔지만 서버 기록이 실패(recorded=false). 다시 보내라고 하지 않는다
  return { id: r.id === null ? null : (int(r.id, 'id') as MailId), sentAtMs: parseOffsetTime(r.sent_at, 'sent_at') };
}

/** AI-32 번역 응답(TranslationView) */
export function toMailTranslation(raw: unknown): MailTranslation {
  const r = record<{ text: unknown; lang: unknown; source: unknown; fallback: unknown; truncated?: unknown }>(raw, '응답');
  return {
    truncated: r.truncated === true,
    text: typeof r.text === 'string' ? r.text : str(r.text, 'text'),
    lang: r.lang === undefined ? null : optStr(r.lang, 'lang'),
    source: oneOf(r.source, ['exaone', 'saved', 'none'] as const, 'source'),
    fallback: r.fallback === undefined ? null : optStr(r.fallback, 'fallback'),
  };
}

/** 답장 다듬기 응답(#95 PolishView) */
export function toPolishedReply(raw: unknown): PolishedReply {
  const r = record<{ text: unknown; changed: unknown; source: unknown; fallback: unknown }>(raw, '응답');
  return {
    text: str(r.text, 'text'),
    changed: bool(r.changed, 'changed'),
    source: oneOf(r.source, ['exaone', 'none'] as const, 'source'),
    fallback: optStr(r.fallback, 'fallback'),
  };
}

/** 요약 응답. null은 '요약할 것이 없음'(빈 요약을 지어내지 않는다) */
export function toMailSummary(raw: unknown): MailSummary | null {
  if (raw === null) return null;
  const r = record<ProvisionalMailSummary>(raw, '응답');
  return {
    lang: str(r.lang, 'lang'),
    gist: str(r.gist, 'gist'),
    asks: strList(r.asks, 'asks'),
    dueText: optStr(r.due_text, 'due_text'),
  };
}

// ── 요청 본문: 화면 모델 → 서버 형식(snake_case · +09:00 ISO). 값이 없는 칸은 보내지 않는다 ──

/**
 * BE-4 StatusChange. source는 BE-4 요청 스키마에 없어 보내지 않는다(값 이름도 아직 다름, contract.ts ActionSource).
 * via(어느 화면에서 눌렀나, PL-16)는 BE-4 요청에 있는 칸이라 값이 있을 때만 보낸다
 */
export function statusChangeBody(change: StatusChange): { status: string; snoozed_until?: string; via?: string } {
  return {
    status: change.status,
    ...(change.snoozedUntilMs === undefined ? {} : { snoozed_until: toKstIso(change.snoozedUntilMs) }),
    ...(change.via === undefined ? {} : { via: change.via }),
  };
}

export function bulkPreviewBody(request: BulkPreviewRequest): { task_ids: number[]; status: string; snoozed_until?: string; via?: string } {
  return { task_ids: [...request.taskIds], ...statusChangeBody(request) };
}

export function settingsPatchToRaw(patch: SettingsPatch): Partial<ProvisionalSettings> {
  const raw: Partial<ProvisionalSettings> = {};
  if (patch.remindTime !== undefined) raw.remind_time = patch.remindTime;
  if (patch.eveningTime !== undefined) raw.evening_time = patch.eveningTime;
  if (patch.awaitingReplyDays !== undefined) raw.awaiting_reply_days = patch.awaitingReplyDays;
  if (patch.quietStart !== undefined) raw.quiet_start = patch.quietStart;
  if (patch.quietEnd !== undefined) raw.quiet_end = patch.quietEnd;
  if (patch.reduceMotion !== undefined) raw.reduce_motion = patch.reduceMotion;
  if (patch.sttMode !== undefined) raw.stt_mode = patch.sttMode;
  if (patch.templates !== undefined) raw.templates = patch.templates.map((t) => ({ key: t.key, name: t.name, pattern: t.pattern }));
  if (patch.readBody !== undefined) raw.read_body = patch.readBody;
  if (patch.workStart !== undefined) raw.work_start = patch.workStart;
  if (patch.workEnd !== undefined) raw.work_end = patch.workEnd;
  if (patch.workDays !== undefined) raw.work_days = patch.workDays;
  if (patch.mailSignature !== undefined) raw.mail_signature = patch.mailSignature;
  if (patch.mailSignatures !== undefined)
    raw.mail_signatures = patch.mailSignatures.map((x) => ({ key: x.key, name: x.name, text: x.text, for_new: x.forNew, for_reply: x.forReply }));
  if (patch.awayUntilMs !== undefined) raw.away_until = patch.awayUntilMs === null ? null : toKstIso(patch.awayUntilMs);
  if (patch.replyConfirmSkipUntilMs !== undefined) {
    raw.reply_confirm_skip_until = patch.replyConfirmSkipUntilMs === null ? null : toKstIso(patch.replyConfirmSkipUntilMs);
  }
  return raw;
}

export function contactPatchBody(patch: ContactPatch): { is_superior?: boolean; is_favorite?: boolean } {
  return {
    ...(patch.isSuperior === undefined ? {} : { is_superior: patch.isSuperior }),
    ...(patch.isFavorite === undefined ? {} : { is_favorite: patch.isFavorite }),
  };
}

/** 보내기 요청 본문. to는 전달 · 새 메일에만 싣는다(답장 요청은 extra=forbid라 422) */
export function replyBody(draft: ReplyDraft, mode: ComposeMode = 'reply'): ProvisionalReplyRequest {
  return {
    account: draft.account,
    subject: draft.subject,
    content: draft.content,
    template_key: draft.templateKey,
    ...(draft.cc === null ? {} : { cc: draft.cc ?? [] }), // 없으면 서버가 원 메일의 참조를 쓴다(전체 답장)
    bcc: draft.bcc ?? [],
    attachments: (draft.attachments ?? []).map((a) => ({ name: a.name, content_type: a.contentType, content_b64: a.contentB64 })),
    ...(mode === 'forward' || mode === 'new' ? { to: draft.to ?? [] } : {}),
    ...(draft.sendAtMs == null ? {} : { send_at: toKstIso(draft.sendAtMs) }),
    ...(draft.contentHtml ? { content_html: draft.contentHtml } : {}),
    ...(draft.importance && draft.importance !== 'normal' ? { importance: draft.importance } : {}),
    ...(draft.largeAttachments?.length ? { large_attachments: draft.largeAttachments } : {}),
    ...(draft.readReceipt ? { read_receipt: true } : {}),
    ...(draft.deliveryReceipt ? { delivery_receipt: true } : {}),
  };
}

/** AI-32 큰 첨부 올리기 응답 */
export function toUploadedFile(raw: unknown): UploadedFile {
  const r = record<{ id: unknown; name: unknown; size: unknown }>(raw, '응답');
  return { id: str(r.id, 'id'), name: str(r.name, 'name'), size: int(r.size, 'size') };
}

const SCHEDULE_STATUSES = ['pending', 'sending', 'sent', 'failed', 'unknown', 'canceled'] as const;
const COMPOSE_MODES = ['reply', 'replyAll', 'forward', 'new'] as const;

export function toScheduledSend(raw: unknown, path = '응답'): ScheduledSend {
  const r = record<{ scheduled_id: unknown; kind: unknown; mail_id: unknown; subject: unknown; to: unknown; send_at: unknown; status: unknown; error: unknown }>(raw, path);
  return {
    scheduledId: int(r.scheduled_id, `${path}.scheduled_id`),
    kind: oneOf(r.kind, COMPOSE_MODES, `${path}.kind`),
    mailId: r.mail_id === null || r.mail_id === undefined ? null : (int(r.mail_id, `${path}.mail_id`) as MailId),
    subject: str(r.subject, `${path}.subject`),
    to: str(r.to, `${path}.to`),
    sendAtMs: parseOffsetTime(r.send_at, `${path}.send_at`),
    status: oneOf(r.status, SCHEDULE_STATUSES, `${path}.status`),
    error: optStr(r.error ?? null, `${path}.error`),
  };
}

/** 보내기 응답: scheduled_id가 있으면 예약(202), 아니면 보낸 메일 */
export function toSendResult(raw: unknown): SendResult {
  const r = record<{ scheduled_id?: unknown }>(raw, '응답');
  return r.scheduled_id === undefined ? toSentReply(raw) : toScheduledSend(raw);
}

export function toScheduledSends(raw: unknown): ScheduledSend[] {
  return list(raw, '응답').map((x, i) => toScheduledSend(x, `[${i}]`));
}

export function toAttachments(raw: unknown): MailAttachment[] {
  return list(raw, '응답').map((x, i) => {
    const r = record<{ id: unknown; name: unknown; content_type: unknown; size: unknown }>(x, `[${i}]`);
    return { id: str(r.id, `[${i}].id`), name: str(r.name, `[${i}].name`), contentType: optStr(r.content_type ?? null, `[${i}].content_type`), size: int(r.size, `[${i}].size`) };
  });
}

export function toSearchHits(raw: unknown): OutlookSearchHit[] {
  return list(raw, '응답').map((x, i) => {
    const p = `[${i}]`;
    const r = record<{ mail_id: unknown; subject: unknown; sender: unknown; received_at: unknown; web_link: unknown }>(x, p);
    const webLink = optStr(r.web_link ?? null, `${p}.web_link`);
    return {
      mailId: r.mail_id === null || r.mail_id === undefined ? null : (int(r.mail_id, `${p}.mail_id`) as MailId),
      subject: str(r.subject, `${p}.subject`),
      sender: str(r.sender, `${p}.sender`),
      receivedAtMs: parseOptionalTime(r.received_at ?? null, `${p}.received_at`),
      webLink: webLink && webLink.startsWith('https://') ? webLink : null, // 다른 스킴(javascript: 등)은 링크로 두지 않는다
    };
  });
}

// ── 에이전트 패널(있음, PL-16 #44) ──

function toSuggestionButton(raw: unknown, path: string): SuggestionButton {
  const r = record<ProvisionalSuggestionButton>(raw, path);
  const t = record<ProvisionalSuggestionButton['target']>(r.target, `${path}.target`);
  const params = r.params === undefined || r.params === null ? {} : record<Record<string, unknown>>(r.params, `${path}.params`);
  return {
    label: str(r.label, `${path}.label`),
    kind: oneOf(r.kind, ['action', 'navigate', 'hide'] as const, `${path}.kind`),
    action: str(r.action, `${path}.action`),
    primary: bool(r.primary, `${path}.primary`),
    params: { ...params } as Record<string, unknown>,
    target: {
      taskIds: intList(t.task_ids, `${path}.target.task_ids`) as TaskId[],
      mailIds: intList(t.mail_ids, `${path}.target.mail_ids`) as MailId[],
    },
  };
}

function toSuggestion(raw: unknown, path: string): Suggestion {
  const r = record<ProvisionalSuggestion>(raw, path);
  return {
    key: str(r.key, `${path}.key`),
    rule: oneOf(r.rule, SUGGESTION_RULES, `${path}.rule`),
    via: str(r.via, `${path}.via`),
    createdAtMs: parseOffsetTime(r.created_at, `${path}.created_at`),
    title: str(r.title, `${path}.title`),
    detail: r.detail === undefined ? [] : strList(r.detail, `${path}.detail`),
    taskIds: intList(r.task_ids, `${path}.task_ids`) as TaskId[],
    mailIds: intList(r.mail_ids, `${path}.mail_ids`) as MailId[],
    buttons: list(r.buttons, `${path}.buttons`).map((b, i) => toSuggestionButton(b, `${path}.buttons[${i}]`)),
    menu: r.menu === undefined ? [] : list(r.menu, `${path}.menu`).map((b, i) => toSuggestionButton(b, `${path}.menu[${i}]`)),
  };
}

/** GET /api/suggestions 응답(계약 3.1) */
export function toSuggestionList(raw: unknown): SuggestionList {
  const r = record<ProvisionalSuggestionList>(raw, '응답');
  return {
    suggestions: list(r.suggestions, 'suggestions').map((s, i) => toSuggestion(s, `suggestions[${i}]`)),
    more: int(r.more, 'more'),
    total: int(r.total, 'total'),
    generatedAtMs: parseOffsetTime(r.generated_at, 'generated_at'),
  };
}

export function toHideResult(raw: unknown): HideResult {
  const r = record<ProvisionalHideResult>(raw, '응답');
  return { key: str(r.key, 'key'), hiddenUntilMs: parseOffsetTime(r.hidden_until, 'hidden_until') };
}

function toHistoryItem(raw: unknown, path: string): HistoryItem {
  const r = record<ProvisionalHistoryItem>(raw, path);
  const optInt = (v: unknown, f: string) => (v === null || v === undefined ? null : int(v, f));
  return {
    id: str(r.id, `${path}.id`),
    state: oneOf(r.state, ['waiting', 'done', 'undone'] as const, `${path}.state`),
    action: str(r.action, `${path}.action`),
    actionId: optInt(r.action_id, `${path}.action_id`),
    previewId: optStr(r.preview_id, `${path}.preview_id`),
    text: str(r.text, `${path}.text`),
    via: str(r.via, `${path}.via`),
    viaLabel: str(r.via_label, `${path}.via_label`),
    auto: bool(r.auto, `${path}.auto`),
    atMs: parseOffsetTime(r.at, `${path}.at`),
    expiresAtMs: parseOptionalTime(r.expires_at, `${path}.expires_at`),
    canUndo: bool(r.can_undo, `${path}.can_undo`),
    redoActionId: optInt(r.redo_action_id, `${path}.redo_action_id`),
  };
}

/** GET /api/actions/history 응답(계약 3.2) */
export function toHistoryList(raw: unknown): HistoryList {
  const r = record<ProvisionalHistoryList>(raw, '응답');
  return { days: int(r.days, 'days'), items: list(r.items, 'items').map((x, i) => toHistoryItem(x, `items[${i}]`)) };
}

function toOrigin(raw: unknown, path: string): MemoryOrigin {
  const r = record<ProvisionalOrigin>(raw, path);
  return { atMs: parseOptionalTime(r.at, `${path}.at`), text: str(r.text, `${path}.text`) };
}

function toMemoryFact(raw: unknown, path: string) {
  const r = record<ProvisionalMemoryFact>(raw, path);
  return {
    kind: oneOf(r.kind, MEMORY_FACT_KINDS, `${path}.kind`),
    label: str(r.label, `${path}.label`),
    value: str(r.value, `${path}.value`),
    evidence: optStr(r.evidence, `${path}.evidence`),
  };
}

/** GET /api/agent/memory 응답(계약 3.3) */
export function toAgentMemory(raw: unknown, path = '응답'): AgentMemory {
  const r = record<ProvisionalAgentMemory>(raw, path);
  const me = record<ProvisionalMemoryMe>(r.me, `${path}.me`);
  return {
    learnFromMail: bool(r.learn_from_mail, `${path}.learn_from_mail`),
    me: {
      name: str(me.name, `${path}.me.name`),
      department: optStr(me.department, `${path}.me.department`),
      position: optStr(me.position, `${path}.me.position`),
      mailingLists: list(me.mailing_lists, `${path}.me.mailing_lists`).map((v, i) => {
        const m = record<{ address: string; kind: string }>(v, `${path}.me.mailing_lists[${i}]`);
        return { address: str(m.address, 'address'), kind: oneOf(m.kind, MAILING_LIST_KINDS, 'kind') };
      }),
      uses: str(me.uses, `${path}.me.uses`),
      usedBy: strList(me.used_by, `${path}.me.used_by`),
      origin: toOrigin(me.origin, `${path}.me.origin`),
    },
    people: list(r.people, `${path}.people`).map((v, i) => {
      const p = record<ProvisionalMemoryPerson>(v, `${path}.people[${i}]`);
      const at = `${path}.people[${i}]`;
      return {
        contactId: int(p.contact_id, `${at}.contact_id`),
        name: optStr(p.name, `${at}.name`),
        email: str(p.email, `${at}.email`),
        position: optStr(p.position, `${at}.position`),
        isSuperior: bool(p.is_superior, `${at}.is_superior`),
        isFavorite: bool(p.is_favorite, `${at}.is_favorite`),
        facts: p.facts === undefined ? [] : list(p.facts, `${at}.facts`).map((f, j) => toMemoryFact(f, `${at}.facts[${j}]`)),
        uses: str(p.uses, `${at}.uses`),
        usedBy: strList(p.used_by, `${at}.used_by`),
        origin: toOrigin(p.origin, `${at}.origin`),
      };
    }),
  };
}

export function toMemoryChange(raw: unknown): MemoryChange {
  const r = record<ProvisionalMemoryChange>(raw, '응답');
  return {
    actionId: r.action_id === null || r.action_id === undefined ? null : int(r.action_id, 'action_id'),
    memory: toAgentMemory(r.memory, 'memory'),
  };
}

export function toAgentSettings(raw: unknown): AgentSettings {
  const r = record<ProvisionalAgentSettings>(raw, '응답');
  return { learnFromMail: bool(r.learn_from_mail, 'learn_from_mail') };
}

export function memoryMePatchBody(patch: MemoryMePatch): { department?: string | null; position?: string | null; mailing_lists?: { address: string; kind: string }[] | null } {
  return {
    ...(patch.department === undefined ? {} : { department: patch.department }),
    ...(patch.position === undefined ? {} : { position: patch.position }),
    ...(patch.mailingLists === undefined ? {} : { mailing_lists: patch.mailingLists === null ? null : patch.mailingLists.map((m) => ({ ...m })) }),
  };
}

export function memoryPersonPatchBody(patch: MemoryPersonPatch): { is_superior?: boolean; is_favorite?: boolean; facts?: Record<string, string | null> } {
  return {
    ...contactPatchBody(patch),
    ...(patch.facts === undefined ? {} : { facts: { ...patch.facts } as Record<string, string | null> }),
  };
}

// ── FE-5d 메일 읽음 · 고정(FE 제안) ──

/** PATCH /api/mails/{id} 응답: 바뀐 메일 한 통(목록 칸 그대로) */
export function toMailItem(raw: unknown): Mail {
  return toMail(raw, '응답');
}

/** GET /api/mails/hidden 응답(BE-7): 보관 · 지운 받은 메일 목록 */
export function toMailList(raw: unknown): Mail[] {
  return list(raw, '응답').map((m, i) => toMail(m, `[${i}]`));
}

/** 요청 본문. 값이 없는 칸은 보내지 않는다 */
export function mailPatchBody(patch: MailPatch): ProvisionalMailPatch {
  return {
    ...(patch.read === undefined ? {} : { read: patch.read }),
    ...(patch.pinned === undefined ? {} : { pinned: patch.pinned }),
  };
}

// ── FE-12 캘린더(BE-15) ──

const DAY = /^\d{4}-\d{2}-\d{2}$/;

function toCalendarItem(raw: unknown, path: string): CalendarItem {
  const r = record<ProvisionalCalendarItem>(raw, path);
  const optInt = (v: unknown, f: string) => (v === null || v === undefined ? null : int(v, f));
  return {
    kind: oneOf(r.kind, CALENDAR_KINDS, `${path}.kind`),
    title: str(r.title, `${path}.title`),
    startMs: parseOffsetTime(r.start, `${path}.start`),
    endMs: parseOptionalTime(r.end, `${path}.end`),
    timeStated: bool(r.time_stated, `${path}.time_stated`),
    mailId: optInt(r.mail_id, `${path}.mail_id`) as MailId | null,
    taskId: optInt(r.task_id, `${path}.task_id`) as TaskId | null,
    eventId: optInt(r.event_id, `${path}.event_id`),
    subject: optStr(r.subject, `${path}.subject`),
    auto: bool(r.auto, `${path}.auto`),
  };
}

/** GET /api/calendar 응답 */
export function toCalendarRange(raw: unknown): CalendarRange {
  const r = record<ProvisionalCalendarRange>(raw, '응답');
  const day = (v: unknown, f: string) => {
    const t = str(v, f);
    if (!DAY.test(t)) throw new ContractError(`${f}: YYYY-MM-DD가 아니다`);
    return t;
  };
  return {
    start: day(r.start, 'start'),
    end: day(r.end, 'end'),
    asOfMs: parseOffsetTime(r.as_of, 'as_of'),
    items: list(r.items, 'items').map((x, i) => toCalendarItem(x, `items[${i}]`)),
  };
}

/** POST · DELETE /api/calendar/events 응답 */
export function toCalendarEventResult(raw: unknown): CalendarEventResult {
  const r = record<ProvisionalEventResult>(raw, '응답');
  return { actionId: int(r.action_id, 'action_id'), item: toCalendarItem(r.item, 'item') };
}

export function calendarEventBody(req: CalendarEventCreate): ProvisionalEventCreate {
  return compact({
    start: toKstIso(req.startMs),
    end: req.endMs == null ? undefined : toKstIso(req.endMs),
    title: req.title ?? undefined,
    mail_id: req.mailId ?? undefined,
    task_id: req.taskId ?? undefined,
    via: req.via ?? undefined,
  });
}

// ── 리마인더 (FE-16 · BE-12 계약) ──
// 명세 7.2절 응답 → 화면 모델. 위쪽과 같은 규칙: 필수 칸이 틀리면 ContractError, 선택 칸은 숨기거나 채운다.
// 서버가 FE가 모르는 유형을 보내면 그 항목만 뺀다(새 유형이 생겨도 목록 전체가 깨지지 않게). 묶음이 틀리면 유형으로 정한다.
// 다른 작업과 겹치지 않게 이 블록에서 따로 불러온다(import는 파일 어디에 있어도 맨 위로 올라간다).
import {
  BRIEFING_KINDS,
  DISMISS_REASONS,
  REMINDER_GROUPS,
  REMINDER_STATES,
  REMINDER_TYPES,
  TASK_TYPES,
  type Briefing,
  type BriefingItem,
  type BriefingSection,
  type DismissReason,
  type ReminderAction,
  type ReminderChange,
  type ReminderGroup,
  type ReminderItem,
  type ReminderList,
  type ReminderState,
  type ReminderType,
  type ReminderTypeNotify,
} from './contract.ts';
import type {
  ProvisionalBriefing,
  ProvisionalBriefingItem,
  ProvisionalBriefingSection,
  ProvisionalReadAll,
  ProvisionalReminderAction,
  ProvisionalReminderChange,
  ProvisionalReminderItem,
  ProvisionalRemindersResponse,
  ProvisionalReminderTypeNotify,
} from './provisional.ts';

/** 유형 → 묶음(명세 3절 표). 서버 group이 틀리거나 없을 때만 쓴다 */
export const REMINDER_TYPE_GROUP: Record<ReminderType, ReminderGroup> = {
  overdue: 'due',
  due_soon: 'due',
  due_changed: 'due',
  due_cluster: 'due',
  no_reply: 'waiting',
  their_promise: 'waiting',
  my_promise: 'promise',
  delegated: 'promise',
  snooze_due: 'revisit',
  priority_sender: 'revisit',
  cc_mention: 'revisit',
  stale: 'revisit',
  stalled_thread: 'revisit',
  meeting_prep: 'prepare',
  recurring: 'prepare',
  resolved: 'cleanup',
  reply_confirm: 'cleanup',
};

const isReminderType = (v: unknown): v is ReminderType => typeof v === 'string' && (REMINDER_TYPES as readonly string[]).includes(v);

function toReminderAction(raw: unknown, path: string): ReminderAction {
  const r = record<ProvisionalReminderAction>(raw, path);
  return {
    id: str(r.id, `${path}.id`),
    label: str(r.label, `${path}.label`),
    action: str(r.action, `${path}.action`),
    primary: bool(r.primary, `${path}.primary`),
    ...dismissReasonOf(r.params),
    ...dayRangeOf(r.params),
  };
}

/** BE-12는 T13(기한 몰림 [당일 업무 보기]) 날짜 범위를 params.start · end에 담는다. 문자열이 아니면 칸을 두지 않는다(버튼이 그려지지 않는다) */
function dayRangeOf(params: unknown): { range?: { start: string; end: string } } {
  if (params === null || typeof params !== 'object') return {};
  const { start, end } = params as { start?: unknown; end?: unknown };
  return typeof start === 'string' && typeof end === 'string' ? { range: { start, end } } : {};
}

/** BE-12는 dismiss 버튼의 이유를 params.reason에 담는다. 모르는 이유면 칸을 두지 않는다(그때는 버튼 id로 정한다) */
function dismissReasonOf(params: unknown): { reason?: DismissReason } {
  if (params === null || typeof params !== 'object') return {};
  const reason = optEnum((params as { reason?: unknown }).reason, DISMISS_REASONS);
  return reason ? { reason } : {};
}

/** 항목 하나. 모르는 유형이면 null(목록에서 뺀다) */
export function toReminderItem(raw: unknown, path: string): ReminderItem | null {
  const r = record<ProvisionalReminderItem>(raw, path);
  if (!isReminderType(r.type)) return null;
  const type = r.type;
  const group = optEnum(r.group, REMINDER_GROUPS) ?? REMINDER_TYPE_GROUP[type];
  const taskId = r.task_id === null || r.task_id === undefined ? null : int(r.task_id, `${path}.task_id`);
  const many = r.task_ids === undefined || r.task_ids === null ? null : intList(r.task_ids, `${path}.task_ids`);
  const cp = r.counterpart === null || r.counterpart === undefined ? null : record<{ name: string; position: string | null }>(r.counterpart, `${path}.counterpart`);
  return {
    key: str(r.key, `${path}.key`),
    type,
    group,
    title: str(r.title, `${path}.title`),
    reason: str(r.reason, `${path}.reason`),
    evidence: optStr(r.evidence, `${path}.evidence`),
    taskId: taskId as TaskId | null,
    taskIds: (many ?? (taskId === null ? [] : [taskId])) as TaskId[],
    taskType: optEnum(r.task_type, TASK_TYPES) ?? null,
    mailId: (r.mail_id === null || r.mail_id === undefined ? null : int(r.mail_id, `${path}.mail_id`)) as MailId | null,
    commitmentId: r.commitment_id === null || r.commitment_id === undefined ? null : int(r.commitment_id, `${path}.commitment_id`),
    dueAtMs: parseOptionalTime(r.due_at, `${path}.due_at`),
    counterpart: cp ? { name: str(cp.name, `${path}.counterpart.name`), position: optStr(cp.position, `${path}.counterpart.position`) } : null,
    createdAtMs: parseOffsetTime(r.created_at, `${path}.created_at`),
    state: oneOf(r.state, REMINDER_STATES, `${path}.state`),
    notifyCount: int(r.notify_count, `${path}.notify_count`),
    lastNotifiedAtMs: optTime(r.last_notified_at) ?? null,
    actions: list(r.actions, `${path}.actions`).map((a, i) => toReminderAction(a, `${path}.actions[${i}]`)),
  };
}

/** GET /api/reminders. 건수가 빠진 묶음은 0으로 채운다(서버가 0건 묶음을 생략해도 메뉴 칸은 남는다) */
export function toReminderList(raw: unknown): ReminderList {
  const r = record<ProvisionalRemindersResponse>(raw, '응답');
  const counts = record<Record<string, number>>(r.counts, 'counts');
  const count = (k: string) => (counts[k] === undefined ? 0 : int(counts[k], `counts.${k}`));
  const items = list(r.items, 'items')
    .map((x, i) => toReminderItem(x, `items[${i}]`))
    .filter((x): x is ReminderItem => x !== null);
  const muted = r.muted_types === undefined ? undefined : list(r.muted_types, 'muted_types').filter(isReminderType);
  return {
    asOfMs: parseOffsetTime(r.as_of, 'as_of'),
    counts: {
      all: count('all'),
      due: count('due'),
      waiting: count('waiting'),
      promise: count('promise'),
      revisit: count('revisit'),
      prepare: count('prepare'),
      cleanup: count('cleanup'),
    },
    items,
    ...(muted === undefined ? {} : { mutedTypes: muted }),
  };
}

/** BE-12의 dismiss · apply 응답에는 state가 없다. 보내면(모의) 읽는다 */
function stateOf(value: unknown): { state?: ReminderState } {
  const state = optEnum(value, REMINDER_STATES);
  return state ? { state } : {};
}

export function toReminderChange(raw: unknown): ReminderChange {
  const r = record<ProvisionalReminderChange>(raw, '응답');
  return {
    key: str(r.key, 'key'),
    ...stateOf(r.state),
    actionId: r.action_id === null || r.action_id === undefined ? null : int(r.action_id, 'action_id'),
  };
}

export function toReminderTypeNotify(raw: unknown): ReminderTypeNotify {
  const r = record<ProvisionalReminderTypeNotify>(raw, '응답');
  return { type: oneOf(r.type, REMINDER_TYPES, 'type'), notify: bool(r.notify, 'notify') };
}

/** dismiss 요청 본문. 이유는 정해진 넷 중 하나만 */
export function dismissBody(reason: string): { reason: string } {
  return { reason: oneOf(reason, DISMISS_REASONS, 'reason') };
}

function toBriefingItem(raw: unknown, path: string): BriefingItem {
  const r = record<ProvisionalBriefingItem>(raw, path);
  return {
    title: str(r.title, `${path}.title`),
    detail: optStr(r.reason ?? r.detail, `${path}.reason`),
    taskId: (r.task_id === null || r.task_id === undefined ? null : int(r.task_id, `${path}.task_id`)) as TaskId | null,
    mailId: (r.mail_id === null || r.mail_id === undefined ? null : int(r.mail_id, `${path}.mail_id`)) as MailId | null,
    reminderKey: optStr(r.reminder_key, `${path}.reminder_key`),
    dueAtMs: parseOptionalTime(r.due_at, `${path}.due_at`),
  };
}

function toBriefingSection(raw: unknown, path: string): BriefingSection {
  const r = record<ProvisionalBriefingSection>(raw, path);
  return {
    id: str(r.id, `${path}.id`),
    title: str(r.label ?? r.title, `${path}.label`),
    count: int(r.count, `${path}.count`),
    items: list(r.items, `${path}.items`).map((x, i) => toBriefingItem(x, `${path}.items[${i}]`)),
  };
}

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

export function toBriefing(raw: unknown): Briefing {
  const r = record<ProvisionalBriefing>(raw, '응답');
  const date = str(r.date, 'date');
  if (!DATE_ONLY.test(date)) throw new ContractError('date: YYYY-MM-DD 형식이 아니다');
  const scheduledAtMs = parseOptionalTime(r.scheduled_at, 'scheduled_at');
  const asOfMs = parseOptionalTime(r.as_of, 'as_of');
  // BE-12는 요청할 때 만들어 as_of만 보낸다. 예정 시각(scheduled_at, BE-12가 더하는 칸)보다 이르면 아직 만든 것이 아니다.
  // generated_at을 따로 보내면(null 포함) 그것을 따른다
  const notYet = scheduledAtMs !== null && asOfMs !== null && asOfMs < scheduledAtMs;
  return {
    kind: oneOf(r.kind, BRIEFING_KINDS, 'kind'),
    date,
    scheduledAtMs,
    generatedAtMs: r.generated_at !== undefined ? parseOptionalTime(r.generated_at, 'generated_at') : notYet ? null : asOfMs,
    asOfMs,
    text: optStr(r.summary ?? r.text, 'summary'),
    headline: optStr(r.headline, 'headline'),
    headlineAtMs: parseOptionalTime(r.headline_at, 'headline_at'),
    sections: list(r.sections, 'sections').map((s, i) => toBriefingSection(s, `sections[${i}]`)),
  };
}

export function toReadAllCount(raw: unknown): number {
  return int(record<ProvisionalReadAll>(raw, '응답').updated, 'updated');
}

/** 알림의 리마인더 칸(선택). 모르는 유형 · 묶음은 null, 칸이 없으면 키를 두지 않는다 */
export function notificationReminderFields(r: { type?: unknown; group?: unknown; reminder_key?: unknown }): Pick<AppNotification, 'type' | 'group' | 'reminderKey'> {
  return compact({
    type: optEnum(r.type, REMINDER_TYPES),
    group: optEnum(r.group, REMINDER_GROUPS),
    reminderKey: optText(r.reminder_key),
  });
}

/** 에이전트 명령 본문에 고른 리마인더(task_ids · reminder_key)를 더한다. 없으면 칸을 보내지 않는다 */
export function reminderCommandFields(request: AgentCommandRequest): { task_ids?: number[]; reminder_key?: string } {
  return {
    ...(request.taskIds && request.taskIds.length > 0 ? { task_ids: [...request.taskIds] } : {}),
    ...(request.reminderKey ? { reminder_key: request.reminderKey } : {}),
  };
}

// ── BE-7 메일 계정 ──

export function toMailAccount(raw: unknown, path = '응답'): MailAccount {
  const r = record<{ id: unknown; provider: unknown; email: unknown; aliases?: unknown; connected: unknown; last_synced_at: unknown }>(raw, path);
  return {
    id: int(r.id, `${path}.id`),
    provider: str(r.provider, `${path}.provider`),
    email: str(r.email, `${path}.email`),
    aliases: r.aliases === undefined ? [] : list(r.aliases, `${path}.aliases`).map((x, i) => str(x, `${path}.aliases[${i}]`)),
    connected: bool(r.connected, `${path}.connected`),
    lastSyncedMs: parseOptionalTime(r.last_synced_at, `${path}.last_synced_at`),
  };
}

export function toMailAccounts(raw: unknown): MailAccountList {
  const r = record<{ outlook_enabled: unknown; items: unknown }>(raw, '응답');
  return {
    outlookEnabled: bool(r.outlook_enabled, 'outlook_enabled'),
    items: list(r.items, 'items').map((a, i) => toMailAccount(a, `items[${i}]`)),
  };
}

export function toConnectUrl(raw: unknown): string {
  const url = str(record<{ url: unknown }>(raw, '응답').url, 'url');
  if (!url.startsWith('https://login.microsoftonline.com/')) throw new ContractError('url: Microsoft 로그인 주소가 아니다');
  return url;
}

export function toAccountSyncResult(raw: unknown): AccountSyncResult {
  const r = record<{ added: unknown; updated: unknown; removed: unknown; last_synced_at: unknown }>(raw, '응답');
  return {
    added: int(r.added, 'added'),
    updated: int(r.updated, 'updated'),
    removed: int(r.removed, 'removed'),
    lastSyncedMs: parseOptionalTime(r.last_synced_at, 'last_synced_at'),
  };
}
