// 모의 모드: src/api/mock/*.json을 메모리에 올려 계약(contract.ts)의 요청 전부를 흉내 낸다.
// 실제 모드와 같은 adapter를 거친다 — 모의도 서버 응답 모양(snake_case · +09:00 ISO)을 먼저 만들고 adapter로 바꾼다.
// 그래야 모의에서 되는 화면이 실제 서버 형식에서도 같은 변환을 탄다.
//
// 데이터 묶음(VITE_MOCK_DATASET)
//   v2(기본): 시안 cne_v31 시연 데이터. 메일 본문 · 요약(mails.v2), 응답 대기, 알림, 설정이 있다
//   v1:       더미 100통(집계 테스트용). 본문 · 응답 대기가 없어 그 요청은 NotAvailableError(실제 서버에 없는 것과 같게)
//
// 상태 바꾸기는 BE-4(backend/app/services/task_status.py)와 같은 규칙으로 흉내 낸다. 화면이 실제 서버로 옮겨도
// 같은 결과 · 같은 오류 코드(404 · 409 · 422)를 받게 하려는 것이다.
import {
  toActionResult,
  toAgentResult,
  toAwaitingList,
  toBulkPreview,
  toContact,
  toDashboardSource,
  toKstIso,
  toMailDetail,
  toMailSummary,
  toNotification,
  settingsPatchToRaw,
  toNotifications,
  toSentReply,
  toSettings,
  toUndoResult,
  replyBody,
  toAgentMemory,
  toAgentSettings,
  toHideResult,
  toHistoryList,
  toMemoryChange,
  toSuggestionList,
  toMailItem,
} from './adapter.ts';
import type { ApiClient } from './contract.ts';
import { AgentUnavailableError, ConfigError, HttpError, NotAvailableError } from './errors.ts';
import { executePlan, type AgentStore } from './mock/agentExecutor.ts';
import {
  AUTO_SOURCES,
  computeSuggestions,
  FIRST_ORIGIN,
  guessListKind,
  hideRow,
  LIST_ADDRESS,
  MEMORY_USED_BY,
  MEMORY_USES,
  memoryHistoryText,
  originText,
  SUGGESTION_KEY,
  taskHistoryText,
  topActions,
  viaLabel,
  waitingHistoryText,
  type HideRow,
  type SuggestionInput,
} from './mock/agentPanelRules.ts';
import { kstNaive, MOCK_DELAY_MS, mockDelayMs, planCommand } from './mock/agentPlanner.ts';
import { createReminderMock, narrowToTasks, type ReminderFixture } from './mock/reminderMock.ts';
import type {
  ProvisionalAgentMemory,
  ProvisionalHistoryItem,
  ProvisionalAwaiting,
  ProvisionalDashboardResponse,
  ProvisionalMailSummary,
  ProvisionalNotification,
  ProvisionalReplyRequest,
  ProvisionalSettings,
  ProvisionalTask,
  ProvisionalTaskState,
} from './provisional.ts';
import { TASK_STATUSES, type DataOrigin, type TaskStatus } from './types.ts';
import { MAILING_LIST_KINDS, type MailingList, type MailingListKind, type MemoryFactKind } from './contract.ts';
// FE-12 캘린더(BE-15 흉내). 다른 작업과 import 줄이 겹치지 않게 따로 둔다
import { calendarEventBody, toCalendarEventResult, toCalendarRange } from './adapter.ts';
import { calendarItems, checkRange, DEFAULT_EVENT_MS, MOCK_MEETINGS, type MockEvent } from './mock/calendarMock.ts';

/**
 * 화면 상태 확인용: mock=loading | empty | error 를 주소에 붙이면 그 상태를 흉내 낸다(모의 모드에서만, 페이지를 불러올 때 읽음).
 * 두 위치를 모두 읽는다: 일반 쿼리 `/?mock=error#/dashboard`, 해시 안 쿼리 `/#/dashboard?mock=error`.
 * 둘 다 있으면 해시 안 값을 우선한다. 그 밖의 값은 무시한다(정상 모의 데이터).
 * loading · error는 모든 요청에(서버가 멈춤 · 고장), empty는 목록 요청(대시보드 · 알림 · 응답 대기)에만 걸린다.
 */
export type MockPreview = 'loading' | 'empty' | 'error' | null;

export function readMockPreview(search: string, hash = ''): MockPreview {
  const q = hash.indexOf('?');
  const fromHash = q >= 0 ? new URLSearchParams(hash.slice(q + 1)).get('mock') : null;
  const v = fromHash ?? new URLSearchParams(search).get('mock');
  return v === 'loading' || v === 'empty' || v === 'error' ? v : null;
}

export type MockDataset = 'v1' | 'v2';

/** VITE_MOCK_DATASET: v2(기본) | v1. 그 밖의 값은 설정 오류(다른 묶음으로 몰래 바꾸지 않는다) */
export function readMockDataset(value: string | undefined): MockDataset {
  const v = value?.trim() || 'v2';
  if (v !== 'v1' && v !== 'v2') throw new ConfigError(`VITE_MOCK_DATASET은 v1 또는 v2여야 한다 (지금: ${v})`);
  return v;
}

interface MockMailFixture {
  to: string[];
  body: string[];
  lang: string;
  summary: ProvisionalMailSummary | null;
  summary_fail_first?: boolean; // 첫 요약 요청만 실패시켜 '요약 실패 → 다시 시도' 화면을 확인한다
}

interface DashboardFixture {
  meta: { dataset: string; version: string };
  response: ProvisionalDashboardResponse;
}

export interface MockFixtures {
  dashboard: DashboardFixture;
  mails: Record<string, MockMailFixture> | null; // null = 이 묶음에는 본문이 없다
  notifications: { items: ProvisionalNotification[] };
  settings: ProvisionalSettings;
}

// JSON은 처음 쓸 때 불러온다(모의 모드가 아니면 번들에서 따로 떨어져 받지 않는다).
// JSON의 모양은 adapter가 응답을 만들 때 검사하므로 여기서는 형식만 붙인다.
export async function loadMockFixtures(dataset: MockDataset): Promise<MockFixtures> {
  // Node(테스트)는 JSON을 불러올 때 형식 표시(with type json)가 꼭 있어야 하고, Vite 개발 서버는 JSON을 JS 모듈로 바꿔 주므로
  // 표시가 붙어 있으면 브라우저가 'JSON이 아니다'라며 거부한다(개발 서버에서만 모의 데이터가 안 뜨던 원인). 그래서 개발 서버에서만 뺀다
  const json = import.meta.env?.DEV ? undefined : ({ with: { type: 'json' } } as const);
  const [notifications, settings] = await Promise.all([
    import('./mock/notifications.v1.json', json),
    import('./mock/settings.v1.json', json),
  ]);
  const common = {
    notifications: notifications.default as MockFixtures['notifications'],
    settings: settings.default as ProvisionalSettings,
  };
  if (dataset === 'v1') {
    const dashboard = await import('./mock/dashboard.v1.json', json);
    return { ...common, dashboard: dashboard.default as unknown as DashboardFixture, mails: null };
  }
  const [dashboard, mails] = await Promise.all([import('./mock/dashboard.v2.json', json), import('./mock/mails.v2.json', json)]);
  return {
    ...common,
    dashboard: dashboard.default as unknown as DashboardFixture,
    mails: mails.default as unknown as Record<string, MockMailFixture>,
  };
}

export interface MockOptions {
  preview?: MockPreview;
  dataset?: MockDataset;
  /** 응답 지연(ms). 숫자 하나 또는 [최소, 최대]. 기본 150~300ms(불러오는 중 표시가 실제처럼 잠깐 보이게), 테스트는 0 */
  latencyMs?: number | readonly [number, number];
  /** 테스트용: JSON 대신 넣을 자료 */
  fixtures?: MockFixtures;
  /** 테스트용: 리마인더 자료(reminders.v1.json) 대신 넣을 것(FE-16) */
  reminderFixture?: ReminderFixture;
  /** 에이전트 명령 지연(ms). 규칙 경로 · 엑사원 경로. 기본 MOCK_DELAY_MS(0.5초 · 5초), 테스트는 0 */
  agentDelayMs?: { rule: number; model: number };
}

// ── 메모리 상태 ──

interface TaskExtra {
  doneAtMs: number | null;
  snoozedUntilMs: number | null;
  statusChangedAtMs: number | null;
}

type Snapshot = TaskExtra & { status: string };

/** 기억 한 항목의 스냅숏(memory.py와 같게 항목 전체를 통째로 남긴다) */
type MemorySnapshot =
  | { kind: 'me'; department: string | null; position: string | null; lists: MailingList[] }
  | { kind: 'contact'; isSuperior: boolean; isFavorite: boolean; facts: Partial<Record<MemoryFactKind, string>> };

interface MockAction {
  id: number;
  kind: 'change' | 'undo';
  action: string; // BE-4 action_log.action(set_status · bulk_status · T03 · memory_me · memory_people · undo …)
  undoneId: number | null; // kind가 undo일 때 되돌린 기록 id
  taskIds: number[];
  before: Map<number, Snapshot>;
  undone: boolean;
  /** 모의 시계 기준 기록 시각(기록 탭 '10분 전') */
  atMs: number;
  /** action_log.source(ui · agent_rule) */
  source: string;
  /** params_json.via(제안 카드 · 기록 탭) */
  via: string | null;
  /** 업무 변경의 바뀐 상태(기록 문장) */
  status: string | null;
  snoozedUntilMs: number | null;
  /** 기억 변경이면 대상과 앞뒤 스냅숏(되돌리기 · 출처 한 줄) */
  memory: { target: string; before: MemorySnapshot; after: MemorySnapshot } | null;
  /** 캘린더 일정 넣기 · 빼기(BE-15)면 일정과 지워짐 앞뒤 */
  calendar?: { eventId: number; title: string; startMs: number; beforeDeleted: boolean; afterDeleted: boolean } | null;
}

interface MockBulkPreview {
  action: string;
  taskIds: number[];
  status: TaskStatus;
  snoozedUntilMs: number | null;
  expiresAtMs: number; // 벽시계(Date.now) 기준. 화면이 expires_at을 지금 시각과 견줄 수 있게 모의 시계를 쓰지 않는다
  used: boolean;
  createdAtMs: number; // 모의 시계
  source: string;
  via: string | null;
}

/** 모의 사용자(이준호 팀장, 시안 cne_v31 ME). 배포 목록은 모의 메일에서 알 수 있는 것이 없어 비워 둔다 */
interface MockOwner {
  name: string;
  department: string | null;
  position: string | null;
  lists: MailingList[];
}

interface MockState {
  origin: DataOrigin;
  dashboard: ProvisionalDashboardResponse;
  extra: Map<number, TaskExtra>;
  mails: Record<string, MockMailFixture> | null;
  summaryCalls: Map<number, number>;
  notifications: ProvisionalNotification[];
  settings: ProvisionalSettings;
  actions: MockAction[];
  previews: Map<string, MockBulkPreview>;
  nextPreview: number;
  /** 보낸 답장(메모리에만, 실제로 보내지 않는다). 보낸 메일 id는 받은 메일 · 응답 대기(1001~)와 겹치지 않게 2001부터 */
  sentReplies: (ProvisionalReplyRequest & { id: number; mail_id: number; sent_at: string })[];
  /** 숨긴 제안 카드(suggestion_hides) */
  hides: Map<string, HideRow>;
  owner: MockOwner;
  learnFromMail: boolean;
  /** 문맥 기억(contact_facts). 모의 데이터에는 없다 */
  facts: Map<number, Partial<Record<MemoryFactKind, string>>>;
  asOfMs: number;
  startedAtMs: number;
  /** 캘린더에 넣은 일정(BE-15 calendar_events). 지우면 deleted만 켠다 */
  events?: MockEvent[];
}

const PREVIEW_TTL_MS = 5 * 60_000; // BE-4 PREVIEW_TTL과 같게
const HH_MM = /^([01]\d|2[0-3]):[0-5]\d$/;

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) return Promise.reject(signal.reason);
  if (ms <= 0) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      'abort',
      () => {
        clearTimeout(timer);
        reject(signal.reason);
      },
      { once: true },
    );
  });
}

const iso = (ms: number | null) => (ms === null ? null : toKstIso(ms));

export function createMockApi(options: MockOptions = {}): ApiClient {
  const { preview = null, dataset = 'v2' } = options;
  const latency = options.latencyMs ?? ([150, 300] as const);
  let statePromise: Promise<MockState> | null = null;

  function load(): Promise<MockState> {
    statePromise ??= (options.fixtures ? Promise.resolve(options.fixtures) : loadMockFixtures(dataset)).then((f) => {
      // 같은 JSON 모듈을 여러 클라이언트가 나눠 쓰므로 고치기 전에 복사한다
      const dashboard = structuredClone(f.dashboard.response);
      // FE-5d: 모의는 고정 칸을 보낸다(처음엔 아무것도 고정 안 함). 실제 서버는 아직 안 보내 화면이 고정을 숨긴다
      for (const m of dashboard.mails) m.pinned_at ??= null;
      return {
        origin: { kind: 'mock', dataset: f.dashboard.meta.dataset, version: f.dashboard.meta.version },
        dashboard,
        // 처음 자료에는 완료 · 나중에 시각이 없다(시안에 없음) → 모름(null)으로 둔다
        extra: new Map(dashboard.tasks.map((t) => [t.id, { doneAtMs: null, snoozedUntilMs: null, statusChangedAtMs: null }])),
        mails: f.mails,
        summaryCalls: new Map(),
        notifications: structuredClone(f.notifications.items),
        settings: structuredClone(f.settings),
        actions: [],
        previews: new Map(),
        nextPreview: 1,
        sentReplies: [],
        hides: new Map(),
        owner: { name: '이준호', department: '1팀', position: '팀장', lists: [] },
        learnFromMail: true, // backend 기본값(켜짐, BE-D17)
        facts: new Map(),
        asOfMs: Date.parse(dashboard.as_of),
        startedAtMs: Date.now(),
      };
    });
    return statePromise;
  }

  // 모의 시계: 데이터 기준 시각(as_of)에서 실제로 흐른 만큼 더한다. 완료 시각이 오늘이 아니라 시연 날짜(11/6)에 찍히게
  const now = (s: MockState) => s.asOfMs + (Date.now() - s.startedAtMs);

  async function begin(signal?: AbortSignal): Promise<MockState> {
    if (preview === 'error') throw new HttpError(503, '모의 오류 상태(?mock=error)');
    if (preview === 'loading') {
      return new Promise<MockState>((_, reject) => {
        signal?.addEventListener('abort', () => reject(signal.reason));
      });
    }
    const [min, max] = typeof latency === 'number' ? [latency, latency] : latency;
    await sleep(min + Math.random() * Math.max(0, max - min), signal);
    return load();
  }

  // ── BE-4 규칙 흉내 ──

  function findTasks(s: MockState, ids: readonly number[]): ProvisionalTask[] {
    const unique = [...new Set(ids)];
    const byId = new Map(s.dashboard.tasks.map((t) => [t.id, t]));
    const missing = unique.filter((id) => !byId.has(id));
    if (missing.length > 0) throw new HttpError(404, `없는 업무: ${missing.join(', ')}`);
    return unique.map((id) => byId.get(id)!);
  }

  function checkChange(status: TaskStatus, until: number | null) {
    if (!(TASK_STATUSES as readonly string[]).includes(status)) throw new HttpError(422, `모르는 상태: ${String(status)}`);
    if (status === 'snoozed' && until === null) throw new HttpError(422, '나중에(snoozed)는 snoozed_until이 필요합니다');
    if (status !== 'snoozed' && until !== null) throw new HttpError(422, 'snoozed_until은 status가 snoozed일 때만 씁니다');
  }

  function stateOf(s: MockState, t: ProvisionalTask): ProvisionalTaskState {
    const x = s.extra.get(t.id)!;
    return {
      id: t.id,
      status: t.status,
      done_at: iso(x.doneAtMs),
      snoozed_until: iso(x.snoozedUntilMs),
      status_changed_at: iso(x.statusChangedAtMs),
    };
  }

  interface RecordMeta {
    source?: string;
    via?: string | null;
    status?: string | null;
    snoozedUntilMs?: number | null;
    memory?: MockAction['memory'];
    calendar?: MockAction['calendar'];
  }

  function record(
    s: MockState,
    kind: MockAction['kind'],
    tasks: ProvisionalTask[],
    undoneId: number | null,
    name: string,
    meta: RecordMeta = {},
  ): MockAction {
    const action: MockAction = {
      id: s.actions.length + 1,
      kind,
      action: name,
      undoneId,
      taskIds: tasks.map((t) => t.id),
      before: new Map(tasks.map((t) => [t.id, { status: t.status, ...s.extra.get(t.id)! }])),
      undone: false,
      atMs: now(s),
      source: meta.source ?? 'ui',
      via: meta.via ?? null,
      status: meta.status ?? null,
      snoozedUntilMs: meta.snoozedUntilMs ?? null,
      memory: meta.memory ?? null,
      calendar: meta.calendar ?? null,
    };
    s.actions.push(action);
    return action;
  }

  /** 이미 그 상태(나중에면 같은 시각까지)인 업무는 건드리지 않고, 바뀐 업무가 없으면 기록도 남기지 않는다 */
  function changeRaw(
    s: MockState,
    ids: readonly number[],
    status: TaskStatus,
    until: number | null,
    name: string,
    meta: { source?: string; via?: string | null } = {},
  ) {
    checkChange(status, until);
    checkVia(meta.via ?? null);
    const tasks = findTasks(s, ids);
    const changed = tasks.filter((t) => t.status !== status || s.extra.get(t.id)!.snoozedUntilMs !== until);
    if (changed.length === 0) return { action_id: null, tasks: tasks.map((t) => stateOf(s, t)) };
    const action = record(s, 'change', changed, null, name, { ...meta, status, snoozedUntilMs: until });
    const at = now(s);
    for (const t of changed) {
      t.status = status;
      s.extra.set(t.id, {
        doneAtMs: status === 'done' ? at : null,
        snoozedUntilMs: status === 'snoozed' ? until : null,
        statusChangedAtMs: at,
      });
    }
    return { action_id: action.id, tasks: tasks.map((t) => stateOf(s, t)) };
  }

  const changeStatus = (
    s: MockState,
    ids: readonly number[],
    status: TaskStatus,
    until: number | null,
    name = 'set_status',
    meta: { source?: string; via?: string | null } = {},
  ) => toActionResult(changeRaw(s, ids, status, until, name, meta));

  /** BE-4 Via 형식: 영문 소문자 · 밑줄, 콜론 하나까지, 40자 이내 */
  function checkVia(via: string | null) {
    if (via !== null && (via.length > 40 || !/^[a-z_]+(:[a-z_]+)?$/.test(via))) throw new HttpError(422, `via 형식이 아닙니다: ${via}`);
  }

  function undoRaw(s: MockState, actionId: number) {
    const target = s.actions.find((a) => a.id === actionId);
    if (!target) throw new HttpError(404, `되돌릴 수 있는 기록이 없습니다: ${actionId}`);
    if (target.undone) throw new HttpError(409, '이미 되돌린 기록입니다');
    if (target.memory) return undoMemory(s, target);
    if (target.calendar) return undoCalendar(s, target);
    // BE-4를 줄인 규칙: 뒤에 같은 업무를 바꾼 '살아 있는 보통 변경'이 있으면 덮어쓰지 않는다(409).
    // 되돌리기 기록을 되돌리는 것(다시 하기)은 뒤에 같은 업무를 건드린 기록이 하나도 없을 때만
    const later = s.actions.filter((a) => a.id > target.id && a.taskIds.some((id) => target.before.has(id)));
    const blocked = target.kind === 'undo' ? later.length > 0 : later.some((a) => a.kind === 'change' && !a.undone);
    if (blocked) throw new HttpError(409, '이 기록 뒤에 같은 업무를 바꾼 기록이 있어 되돌릴 수 없습니다');
    const tasks = findTasks(s, target.taskIds);
    const back = record(s, 'undo', tasks, target.id, 'undo');
    if (target.kind === 'change') otherUndo.get(target.id)?.(); // FE-16: 리마인더 숨김 · 기한 바꾸기 · 약속 끝냄
    for (const t of tasks) {
      const { status, ...extra } = target.before.get(t.id)!;
      t.status = status;
      s.extra.set(t.id, extra);
    }
    target.undone = true;
    if (target.kind === 'undo') {
      const redone = s.actions.find((a) => a.id === target.undoneId);
      if (redone) redone.undone = false; // 다시 하기: 그 변경이 다시 살아 있으므로 다시 되돌릴 수 있다
    }
    return { back, target, tasks };
  }

  /** 기억 변경 되돌리기(memory.py): 뒤에 같은 항목을 바꾼 살아 있는 기록이 있거나, 지금 값이 그 기록이 남긴 값과 다르면 409 */
  function undoMemory(s: MockState, target: MockAction) {
    const mem = target.memory!;
    const later = s.actions.filter((a) => a.id > target.id && a.memory?.target === mem.target);
    const blocked = target.kind === 'undo' ? later.length > 0 : later.some((a) => a.kind === 'change' && !a.undone);
    if (blocked) throw new HttpError(409, '이 기록 뒤에 같은 항목을 바꾼 기록이 있어 되돌릴 수 없습니다');
    const current = memorySnapshot(s, mem.target);
    if (JSON.stringify(current) !== JSON.stringify(mem.after)) throw new HttpError(409, '기록 밖에서 바뀐 값이라 되돌리지 않았습니다');
    applyMemory(s, mem.target, mem.before);
    const back = record(s, 'undo', [], target.id, 'undo', { memory: { target: mem.target, before: current, after: mem.before } });
    target.undone = true;
    if (target.kind === 'undo') {
      const redone = s.actions.find((a) => a.id === target.undoneId);
      if (redone) redone.undone = false;
    }
    return { back, target, tasks: [] as ProvisionalTask[] };
  }

  /** 일정 넣기 · 빼기 되돌리기(services/calendar.py): 일정이 그 기록 직후 상태가 아니면 409 */
  function undoCalendar(s: MockState, target: MockAction) {
    const cal = target.calendar!;
    const ev = (s.events ?? []).find((e) => e.id === cal.eventId);
    if (!ev) throw new HttpError(404, '일정이 없습니다');
    if (ev.deleted !== cal.afterDeleted) throw new HttpError(409, '이 기록 뒤에 일정이 바뀌어 되돌릴 수 없습니다');
    ev.deleted = cal.beforeDeleted;
    const back = record(s, 'undo', [], target.id, 'undo', { calendar: { ...cal, beforeDeleted: cal.afterDeleted, afterDeleted: cal.beforeDeleted } });
    target.undone = true;
    if (target.kind === 'undo') {
      const redone = s.actions.find((a) => a.id === target.undoneId);
      if (redone) redone.undone = false;
    }
    return { back, target, tasks: [] as ProvisionalTask[] };
  }

  // ── 에이전트가 아는 것(memory.py 흉내) ──

  /** 연락처 id는 모의 원자료 순서 1..N(backend contacts.id 자리) */
  const contactAt = (s: MockState, id: number) => {
    const c = Number.isInteger(id) && id >= 1 ? s.dashboard.contacts[id - 1] : undefined;
    if (!c) throw new HttpError(404, `없는 연락처: ${id}`);
    return c;
  };

  function memorySnapshot(s: MockState, target: string): MemorySnapshot {
    const [kind, raw] = target.split(':');
    if (kind === 'me') return { kind: 'me', department: s.owner.department, position: s.owner.position, lists: s.owner.lists.map((l) => ({ ...l })) };
    const id = Number(raw);
    const c = contactAt(s, id);
    return { kind: 'contact', isSuperior: c.is_superior, isFavorite: c.is_favorite, facts: { ...(s.facts.get(id) ?? {}) } };
  }

  function applyMemory(s: MockState, target: string, snap: MemorySnapshot) {
    if (snap.kind === 'me') {
      s.owner = { ...s.owner, department: snap.department, position: snap.position, lists: snap.lists.map((l) => ({ ...l })) };
      return;
    }
    const id = Number(target.split(':')[1]);
    const c = contactAt(s, id);
    c.is_superior = snap.isSuperior;
    c.is_favorite = snap.isFavorite;
    s.facts.set(id, { ...snap.facts });
  }

  /** 바꾸기: 같은 값이면 기록 없음(null) */
  function changeMemory(s: MockState, target: string, action: 'memory_me' | 'memory_people', next: MemorySnapshot): number | null {
    const before = memorySnapshot(s, target);
    if (JSON.stringify(before) === JSON.stringify(next)) return null;
    applyMemory(s, target, next);
    return record(s, 'change', [], null, action, { memory: { target, before, after: next } }).id;
  }

  function memoryView(s: MockState): ProvisionalAgentMemory {
    const latest = new Map<string, MockAction>();
    for (const a of s.actions) if (a.memory) latest.set(a.memory.target, a);
    const origin = (target: string) => {
      const a = latest.get(target);
      if (!a) return { at: null, text: FIRST_ORIGIN };
      const undone = a.kind === 'undo' ? s.actions.find((x) => x.id === a.undoneId) : undefined;
      const how = a.kind === 'change' ? 'change' : undone?.kind === 'undo' ? 'redo' : 'undo';
      return { at: toKstIso(a.atMs), text: originText(a.atMs, a.source, how) };
    };
    const people = s.dashboard.contacts
      .map((c, i) => ({ c, id: i + 1, facts: s.facts.get(i + 1) ?? {} }))
      .filter(({ c, facts }) => c.is_superior || c.is_favorite || Object.keys(facts).length > 0)
      .sort((a, b) => (a.c.name ?? '').localeCompare(b.c.name ?? '', 'ko') || a.id - b.id)
      .map(({ c, id, facts }) => {
        const on = (['superior', 'favorite', 'facts'] as const).filter((k) =>
          k === 'superior' ? c.is_superior : k === 'favorite' ? c.is_favorite : Object.keys(facts).length > 0,
        );
        return {
          contact_id: id,
          name: c.name,
          email: c.email,
          position: c.position || null,
          is_superior: c.is_superior,
          is_favorite: c.is_favorite,
          facts: (Object.entries(facts) as [MemoryFactKind, string][]).map(([kind, value]) => ({
            kind,
            label: kind === 'works_on' ? '맡은 일' : '소속',
            value,
            evidence: null,
          })),
          uses: on.map((k) => MEMORY_USES[k]).join(' '),
          used_by: [...new Set(on.flatMap((k) => MEMORY_USED_BY[k]))],
          origin: origin(`contact:${id}`),
        };
      });
    return {
      learn_from_mail: s.learnFromMail,
      me: {
        name: s.owner.name,
        department: s.owner.department,
        position: s.owner.position,
        mailing_lists: s.owner.lists.map((l) => ({ ...l })),
        uses: MEMORY_USES.me,
        used_by: [...MEMORY_USED_BY.me],
        origin: origin('me:1'),
      },
      people,
    };
  }

  // ── 제안 카드 · 기록 탭 ──

  function suggestionInput(s: MockState): SuggestionInput {
    return {
      data: s.dashboard,
      nowMs: now(s),
      remindTime: s.settings.remind_time,
      awaitDays: s.settings.awaiting_reply_days,
      snoozedUntilMs: (id) => s.extra.get(id)?.snoozedUntilMs ?? null,
      hides: s.hides,
    };
  }

  function historyItems(s: MockState, days: number): ProvisionalHistoryItem[] {
    const at = now(s);
    const since = at - days * 24 * 3600_000;
    const texts = new Map(s.dashboard.tasks.map((t) => [t.id, t.text]));
    const waiting: ProvisionalHistoryItem[] = [...s.previews.entries()]
      .filter(([, p]) => !p.used && p.expiresAtMs >= Date.now())
      .sort(([, a], [, b]) => b.createdAtMs - a.createdAtMs)
      .map(([id, p]) => {
        const [via, label] = viaLabel(p.via, p.source);
        return {
          id: `preview:${id}`,
          state: 'waiting',
          action: p.action,
          action_id: null,
          preview_id: id,
          text: waitingHistoryText(p.taskIds.length, p.status),
          via,
          via_label: label,
          auto: false,
          at: toKstIso(p.createdAtMs),
          expires_at: toKstIso(p.expiresAtMs),
          can_undo: false,
          redo_action_id: null,
        };
      });
    // 되돌릴 수 있는 것: 그 업무 · 항목을 지금 되돌릴 수 있는 가장 최근 행동(task_status._top_actions)
    const keysOf = (a: MockAction) =>
      a.memory ? [a.memory.target] : a.calendar ? [`event:${a.calendar.eventId}`] : a.taskIds.map((id) => `task:${id}`);
    const top = topActions(s.actions.map((a) => ({ id: a.id, kind: a.kind, undoneId: a.undoneId, keys: keysOf(a) })));
    const isTop = (a: MockAction) => keysOf(a).length > 0 && keysOf(a).every((k) => top.get(k) === a.id);
    const redoOf = new Map(s.actions.filter((a) => a.kind === 'undo' && !a.undone).map((a) => [a.undoneId, a.id]));
    const logs: ProvisionalHistoryItem[] = s.actions
      .filter((a) => a.kind === 'change' && a.atMs >= since)
      .sort((a, b) => b.id - a.id)
      .map((a) => {
        const [via, label] = viaLabel(a.via, a.source, a.memory !== null);
        const text = otherText.has(a.id)
          ? otherText.get(a.id)!
          : a.memory
          ? memoryHistoryText(a.action as 'memory_me' | 'memory_people', a.source)
          : a.calendar
            ? calendarHistoryText(a.action, a.calendar.title, a.calendar.startMs)
            : taskHistoryText(a.taskIds.map((id) => texts.get(id) ?? ''), a.status ?? '', a.snoozedUntilMs, a.action);
        const state = a.undone ? 'undone' : 'done';
        return {
          id: `log:${a.id}`,
          state,
          action: a.action,
          action_id: a.id,
          preview_id: null,
          text,
          via,
          via_label: label,
          auto: AUTO_SOURCES.includes(a.source) || via === 'mail_learn',
          at: toKstIso(a.atMs),
          expires_at: null,
          can_undo: state === 'done' && isTop(a),
          redo_action_id: state === 'undone' ? (redoOf.get(a.id) ?? null) : null,
        };
      });
    return [...waiting, ...logs];
  }

  function undo(s: MockState, actionId: number) {
    const { back, target, tasks } = undoRaw(s, actionId);
    return toUndoResult({ action_id: back.id, undone_action_id: target.id, tasks: tasks.map((t) => stateOf(s, t)) });
  }

  function createPreview(
    s: MockState,
    tasks: ProvisionalTask[],
    status: TaskStatus,
    until: number | null,
    action: string,
    meta: { source?: string; via?: string | null } = {},
  ) {
    const previewId = `mock-preview-${s.nextPreview++}`;
    const expiresAtMs = Date.now() + PREVIEW_TTL_MS;
    s.previews.set(previewId, {
      action,
      taskIds: tasks.map((t) => t.id),
      status,
      snoozedUntilMs: until,
      expiresAtMs,
      used: false,
      createdAtMs: now(s),
      source: meta.source ?? 'ui',
      via: meta.via ?? null,
    });
    return { preview_id: previewId, expires_at: toKstIso(expiresAtMs) };
  }

  /** 에이전트 실행기(mock/agentExecutor.ts)에 넘기는 BE-4 흉내 */
  function agentStore(s: MockState): AgentStore {
    return {
      data: s.dashboard,
      nowMs: now(s),
      snoozedUntilMs: (id) => s.extra.get(id)?.snoozedUntilMs ?? null,
      preview: (ids, status, until, action) => {
        checkChange(status, until);
        return createPreview(s, findTasks(s, ids), status, until, action, { source: 'agent_rule' });
      },
      change: (ids, status, until, action) => changeRaw(s, ids, status, until, action, { source: 'agent_rule' }).action_id,
      latestAction: () => {
        const a = s.actions[s.actions.length - 1];
        return a ? { id: a.id, action: a.action, undoneId: a.undoneId } : null;
      },
      findAction: (id) => s.actions.find((a) => a.id === id) ?? null,
      undo: (id) => {
        const { back, target } = undoRaw(s, id);
        return { backId: back.id, undoneId: target.id, undoneAction: target.action, taskIds: target.taskIds };
      },
      toIso: iso,
    };
  }

  // ── 리마인더(FE-16, mock/reminderMock.ts) ──
  /** 업무 상태가 아닌 것을 바꾼 기록의 되돌리기 함수(기록 id별) */
  const otherUndo = new Map<number, () => void>();
  const otherText = new Map<number, string>(); // 기록 탭 문장
  const reminders = createReminderMock<MockState>({
    begin,
    now,
    dashboard: (s) => s.dashboard,
    snoozedUntil: (s, id) => s.extra.get(id)?.snoozedUntilMs ?? null,
    changeTasks: (s, ids, status, action, via) => changeRaw(s, ids, status, null, action, { via }).action_id,
    recordOther: (s, action, undo, text, via) => {
      const a = record(s, 'change', [], null, action, { via });
      otherUndo.set(a.id, undo);
      otherText.set(a.id, text);
      return a.id;
    },
    notifications: (s) => s.notifications,
    empty: preview === 'empty',
    ...(options.reminderFixture ? { fixture: options.reminderFixture } : {}),
  });
  const { visibleNotifications, ...reminderMethods } = reminders;

  function mailFixture(s: MockState, id: number, endpoint: string): MockMailFixture {
    if (s.mails === null) throw new NotAvailableError(endpoint, 404);
    const fixture = s.mails[String(id)];
    if (!fixture) throw new HttpError(404, `없는 메일: ${id}`);
    return fixture;
  }

  return {
    async getDashboard(signal) {
      const s = await begin(signal);
      const source = toDashboardSource(s.dashboard, s.origin);
      if (preview !== 'empty') return source;
      // 빈 상태 흉내: 응답 대기 칸이 원래 있던 묶음이면 [](없음), 없던 묶음이면 계속 숨김
      return { ...source, mails: [], tasks: [], contacts: [], ...(source.awaiting ? { awaiting: [] } : {}) };
    },

    async patchTaskStatus(id, change) {
      const s = await begin();
      return changeStatus(s, [id], change.status, change.snoozedUntilMs ?? null, 'set_status', { via: change.via ?? null });
    },

    async bulkPreview(request) {
      const s = await begin();
      const until = request.snoozedUntilMs ?? null;
      checkChange(request.status, until);
      if (request.taskIds.length === 0) throw new HttpError(422, '업무를 하나 이상 골라 주세요');
      const tasks = findTasks(s, request.taskIds);
      checkVia(request.via ?? null);
      const p = createPreview(s, tasks, request.status, until, 'bulk_status', { via: request.via ?? null });
      return toBulkPreview({
        ...p,
        status: request.status,
        snoozed_until: iso(until),
        targets: tasks.map((t) => ({ id: t.id, text: t.text, status: t.status })),
      });
    },

    async executeAction(previewId, taskIds) {
      const s = await begin();
      const p = s.previews.get(previewId);
      if (!p) throw new HttpError(404, '없는 미리보기입니다');
      if (p.used) throw new HttpError(409, '이미 실행한 미리보기입니다');
      let picked = p.taskIds;
      if (taskIds !== undefined) {
        // 확인 카드에서 체크를 남긴 업무만(BE-4 execute task_ids). 미리보기 대상 밖이거나 비면 422
        picked = [...new Set(taskIds)];
        if (picked.length === 0 || picked.some((id) => !p.taskIds.includes(id))) {
          throw new HttpError(422, '미리보기 대상 안에서 1건 이상 골라 주세요');
        }
      }
      if (p.expiresAtMs < Date.now()) throw new HttpError(409, '만료된 미리보기입니다. 다시 미리보기를 받아 주세요');
      p.used = true;
      return changeStatus(s, picked, p.status, p.snoozedUntilMs, p.action, { source: p.source, via: p.via });
    },

    async undoAction(actionId) {
      return undo(await begin(), actionId);
    },

    // BE-11 #50 흉내: 규칙 해석(mock/agentPlanner.ts) → 기다림(규칙 0.5초 · 엑사원 경로 5초) → executor.py와 같은 실행.
    // 기다리는 동안 중지하면 아무것도 바꾸지 않는다. ?mock=error면 실제 서버의 503처럼 AgentUnavailableError
    async runAgentCommand(request, signal) {
      let s: MockState;
      try {
        s = await begin(signal);
      } catch (e) {
        if (e instanceof HttpError && e.status === 503) throw new AgentUnavailableError();
        throw e;
      }
      const text = request.text.trim();
      if (!text || text.length > 500) throw new HttpError(422, '명령은 1~500자여야 합니다');
      const plan = planCommand(text, {
        now: kstNaive(now(s)),
        selected_mail_ids: (request.selectedMailIds ?? []).map(String),
        last_result_ids: (request.lastResultIds ?? []).map(String),
      });
      await sleep(mockDelayMs(plan, options.agentDelayMs ?? MOCK_DELAY_MS), signal);
      // FE-16: 고른 리마인더의 업무(task_ids)가 있으면 고른 메일 안에서 그 업무만 대상으로
      const store = agentStore(s);
      return toAgentResult(executePlan(plan, { ...store, data: narrowToTasks(store.data, request.selectedMailIds ?? [], request.taskIds) }));
    },

    async getNotifications(signal) {
      const s = await begin(signal);
      return toNotifications({ items: await visibleNotifications(s) });
    },

    async patchNotification(id, patch) {
      const s = await begin();
      const n = s.notifications.find((x) => x.id === id);
      if (!n) throw new HttpError(404, `없는 알림: ${id}`);
      const at = toKstIso(now(s));
      if (patch.answer !== undefined) {
        if (n.kind !== 'reply_confirm') throw new HttpError(422, '예/아니오로 답할 수 있는 알림이 아닙니다');
        if (n.answered_at !== null) throw new HttpError(409, '이미 답한 알림입니다');
        // '예'여도 업무 상태는 여기서 바꾸지 않는다. 완료는 화면이 useTaskActions로 따로 보낸다(BE-5 규칙 미정)
        n.answered_at = at;
        n.read_at ??= at;
      }
      if (patch.read) n.read_at ??= at;
      return toNotification(n);
    },

    async getSettings(signal) {
      return toSettings((await begin(signal)).settings);
    },

    async patchSettings(patch) {
      const s = await begin();
      const raw = settingsPatchToRaw(patch);
      for (const key of ['remind_time', 'quiet_start', 'quiet_end'] as const) {
        const v = raw[key];
        if (v !== undefined && v !== null && !HH_MM.test(v)) throw new HttpError(422, `${key}: HH:MM 형식이 아닙니다`);
      }
      const days = raw.awaiting_reply_days;
      if (days !== undefined && !(Number.isInteger(days) && days >= 1)) {
        throw new HttpError(422, 'awaiting_reply_days: 1 이상의 정수여야 합니다');
      }
      s.settings = { ...s.settings, ...raw };
      return toSettings(s.settings);
    },

    async patchContact(email, patch) {
      const s = await begin();
      const c = s.dashboard.contacts.find((x) => x.email === email);
      if (!c) throw new HttpError(404, '없는 연락처');
      if (patch.isSuperior !== undefined) c.is_superior = patch.isSuperior;
      if (patch.isFavorite !== undefined) c.is_favorite = patch.isFavorite;
      return toContact(c, '응답');
    },

    async getAwaiting(signal) {
      const s = await begin(signal);
      const awaiting: ProvisionalAwaiting[] | undefined = s.dashboard.awaiting;
      if (awaiting === undefined) throw new NotAvailableError('/awaiting', 404);
      return toAwaitingList(preview === 'empty' ? [] : awaiting);
    },

    async getMail(id, signal) {
      const s = await begin(signal);
      const fixture = mailFixture(s, id, '/mails/{id}');
      const mail = s.dashboard.mails.find((m) => m.id === id);
      if (!mail) throw new HttpError(404, `없는 메일: ${id}`);
      return toMailDetail({
        ...mail,
        to: fixture.to,
        lang: fixture.lang,
        body: fixture.body,
        tasks: s.dashboard.tasks.filter((t) => t.mail_id === id),
      });
    },

    async summarizeMail(id, signal) {
      const s = await begin(signal);
      const fixture = mailFixture(s, id, '/mails/{id}/summary');
      const calls = (s.summaryCalls.get(id) ?? 0) + 1;
      s.summaryCalls.set(id, calls);
      if (fixture.summary_fail_first && calls === 1) throw new HttpError(503, '모의 요약 실패(첫 요청만)');
      return toMailSummary(fixture.summary);
    },

    // 실제로 보내지 않는다: 메모리에 저장만 하고 저장된 보낸 메일 id · 시각을 돌려준다
    async sendReply(id, draft) {
      const s = await begin();
      if (!s.dashboard.mails.some((m) => m.id === id)) throw new HttpError(404, `없는 메일: ${id}`);
      if (draft.content.trim() === '') throw new HttpError(422, 'content: 보낼 내용이 없습니다');
      const sent = { ...replyBody(draft), id: 2001 + s.sentReplies.length, mail_id: id, sent_at: toKstIso(now(s)) };
      s.sentReplies.push(sent);
      return toSentReply({ id: sent.id, sent_at: sent.sent_at });
    },

    // ── 에이전트 패널(PL-16): backend services 규칙 그대로(mock/agentPanelRules.ts) ──

    async getSuggestions(limit, signal) {
      const s = await begin(signal);
      if (!(Number.isInteger(limit) && limit >= 1 && limit <= 50)) throw new HttpError(422, 'limit은 1~50');
      const cards = preview === 'empty' ? [] : computeSuggestions(suggestionInput(s));
      return toSuggestionList({
        suggestions: cards.slice(0, limit),
        more: Math.max(0, cards.length - limit),
        total: cards.length,
        generated_at: toKstIso(now(s)),
      });
    },

    async hideSuggestion(key) {
      const s = await begin();
      if (!SUGGESTION_KEY.test(key)) throw new HttpError(422, `카드 키 형식이 아닙니다: ${key}`);
      const row = hideRow(key, suggestionInput(s));
      s.hides.set(key, row);
      return toHideResult({ key, hidden_until: toKstIso(row.untilMs) });
    },

    // ── FE-12 캘린더(BE-15 흉내) ──
    async getCalendar(start, end, signal) {
      const s = await begin(signal);
      const range = checkRange(start, end);
      if (typeof range === 'string') throw new HttpError(422, range);
      const subjects = new Map(s.dashboard.mails.map((m) => [m.id, m.subject]));
      const items = calendarItems(
        { tasks: s.dashboard.tasks, snoozedUntil: (id) => s.extra.get(id)?.snoozedUntilMs ?? null, subjects, events: s.events ?? [] },
        range[0],
        range[1],
      );
      return toCalendarRange({ start, end, as_of: toKstIso(now(s)), items });
    },

    async addCalendarEvent(req) {
      const s = await begin();
      const body = calendarEventBody(req); // 실제 요청과 같은 값으로 검사한다
      const events = (s.events ??= []);
      let mailId = body.mail_id ?? null;
      if (body.task_id != null) {
        const t = s.dashboard.tasks.find((x) => x.id === body.task_id);
        if (!t) throw new HttpError(404, `없는 업무: ${body.task_id}`);
        mailId ??= t.mail_id;
      }
      const mail = mailId === null ? null : s.dashboard.mails.find((m) => m.id === mailId);
      if (mailId !== null && !mail) throw new HttpError(404, `없는 메일: ${mailId}`);
      if (mailId !== null && events.some((e) => !e.deleted && e.mailId === mailId)) throw new HttpError(409, '이 메일의 일정이 이미 캘린더에 있습니다');
      const startMs = req.startMs;
      const endMs = req.endMs ?? startMs + DEFAULT_EVENT_MS;
      if (endMs <= startMs) throw new HttpError(422, '끝 시각이 시작 시각보다 앞입니다');
      checkVia(req.via ?? null);
      const meeting = MOCK_MEETINGS.find((m) => m.mailId === mailId);
      const title = req.title?.trim() || meeting?.title || mail?.subject || '일정';
      const ev: MockEvent = { id: events.length + 1, title, startMs, endMs, mailId, taskId: body.task_id ?? null, deleted: false };
      events.push(ev);
      const action = record(s, 'change', [], null, 'T15', {
        via: req.via ?? null,
        calendar: { eventId: ev.id, title, startMs, beforeDeleted: true, afterDeleted: false },
      });
      return toCalendarEventResult({ action_id: action.id, item: mockEventItem(s, ev) });
    },

    async removeCalendarEvent(eventId) {
      const s = await begin();
      const ev = (s.events ?? []).find((e) => e.id === eventId && !e.deleted);
      if (!ev) throw new HttpError(404, `없는 일정: ${eventId}`);
      ev.deleted = true;
      const action = record(s, 'change', [], null, 'calendar_remove', {
        calendar: { eventId: ev.id, title: ev.title, startMs: ev.startMs, beforeDeleted: false, afterDeleted: true },
      });
      return toCalendarEventResult({ action_id: action.id, item: mockEventItem(s, ev) });
    },

    async getActionHistory(days, signal) {
      const s = await begin(signal);
      if (!(Number.isInteger(days) && days >= 1 && days <= 30)) throw new HttpError(422, 'days는 1~30');
      return toHistoryList({ days, items: preview === 'empty' ? [] : historyItems(s, days) });
    },

    async getAgentMemory(signal) {
      return toAgentMemory(memoryView(await begin(signal)));
    },

    async patchAgentMemoryMe(patch) {
      const s = await begin();
      const cur = memorySnapshot(s, 'me:1') as Extract<MemorySnapshot, { kind: 'me' }>;
      const blank = (v: string | null | undefined, max: number, field: string) => {
        if (v === undefined) return undefined;
        if (v !== null && v.length > max) throw new HttpError(422, `${field}: ${max}자까지`);
        return v === null ? null : v.trim() || null;
      };
      const department = blank(patch.department, 100, 'department');
      const position = blank(patch.position, 50, 'position');
      let lists = cur.lists;
      if (patch.mailingLists !== undefined) {
        const items = patch.mailingLists ?? [];
        if (items.length > 20) throw new HttpError(422, '배포 목록은 20개까지');
        const seen = new Map<string, MailingListKind>();
        for (const it of items) {
          const address = it.address.trim().toLowerCase();
          if (address.length < 3 || address.length > 255 || !LIST_ADDRESS.test(address)) {
            throw new HttpError(422, `배포 목록 주소 형식이 아닙니다: ${address}`);
          }
          if (!(MAILING_LIST_KINDS as readonly string[]).includes(it.kind)) throw new HttpError(422, `모르는 종류: ${it.kind}`);
          if (!seen.has(address)) seen.set(address, it.kind ?? guessListKind(address));
        }
        lists = [...seen].map(([address, kind]) => ({ address, kind }));
      }
      const actionId = changeMemory(s, 'me:1', 'memory_me', {
        kind: 'me',
        department: department === undefined ? cur.department : department,
        position: position === undefined ? cur.position : position,
        lists,
      });
      return toMemoryChange({ action_id: actionId, memory: memoryView(s) });
    },

    async patchAgentMemoryPerson(contactId, patch) {
      const s = await begin();
      const target = `contact:${contactId}`;
      const cur = memorySnapshot(s, target) as Extract<MemorySnapshot, { kind: 'contact' }>;
      for (const v of [patch.isSuperior, patch.isFavorite]) {
        if (v !== undefined && typeof v !== 'boolean') throw new HttpError(422, 'is_superior · is_favorite는 true 또는 false');
      }
      const facts = { ...cur.facts };
      for (const [k, v] of Object.entries(patch.facts ?? {}) as [MemoryFactKind, string | null][]) {
        if (v === null) delete facts[k];
        else if (v.trim().length < 1 || v.trim().length > 40) throw new HttpError(422, `${k} 값은 1~40자`);
        else facts[k] = v.trim();
      }
      const actionId = changeMemory(s, target, 'memory_people', {
        kind: 'contact',
        isSuperior: patch.isSuperior ?? cur.isSuperior,
        isFavorite: patch.isFavorite ?? cur.isFavorite,
        facts,
      });
      return toMemoryChange({ action_id: actionId, memory: memoryView(s) });
    },

    async getAgentSettings(signal) {
      return toAgentSettings({ learn_from_mail: (await begin(signal)).learnFromMail });
    },

    async patchAgentSettings(patch) {
      const s = await begin();
      if (typeof patch.learnFromMail !== 'boolean') throw new HttpError(422, 'learn_from_mail은 참거짓만');
      s.learnFromMail = patch.learnFromMail;
      return toAgentSettings({ learn_from_mail: s.learnFromMail });
    },

    // ── FE-5d 메일 읽음 · 고정(FE 제안) ──
    // 읽음: 이미 읽었으면 처음 읽은 시각을 그대로 둔다. 읽음 칸이 없는 묶음(v1)은 실제 서버에 없는 것과 같게 NotAvailableError
    async patchMail(id, patch) {
      const s = await begin();
      const mail = s.dashboard.mails.find((m) => m.id === id);
      if (!mail) throw new HttpError(404, `없는 메일: ${id}`);
      if (patch.read === undefined && patch.pinned === undefined) throw new HttpError(422, 'read 또는 pinned가 필요합니다');
      const at = toKstIso(now(s));
      if (patch.read !== undefined) {
        if (mail.read_at === undefined) throw new NotAvailableError('/mails/{id}', 404);
        mail.read_at = patch.read ? (mail.read_at ?? at) : null;
      }
      if (patch.pinned !== undefined) mail.pinned_at = patch.pinned ? (mail.pinned_at ?? at) : null;
      return toMailItem(mail);
    },

    ...reminderMethods, // FE-16
  };
}

// ── FE-12 캘린더(BE-15 흉내) 도움 함수 ──

function mockEventItem(s: { dashboard: { mails: { id: number; subject: string }[] } }, ev: MockEvent) {
  const subject = ev.mailId === null ? null : (s.dashboard.mails.find((m) => m.id === ev.mailId)?.subject ?? null);
  return { kind: 'event', title: ev.title, start: toKstIso(ev.startMs), end: toKstIso(ev.endMs), time_stated: true,
    mail_id: ev.mailId, task_id: ev.taskId, event_id: ev.id, subject, auto: false };
}

/** 기록 탭 문장(services/calendar.describe와 같게) */
function calendarHistoryText(action: string, title: string, startMs: number): string {
  const d = new Date(startMs + 9 * 3600_000);
  const when = `${d.getUTCMonth() + 1}/${d.getUTCDate()} ${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
  return action === 'calendar_remove' ? `캘린더에서 ${when} '${title}'을(를) 뺐어요` : `캘린더에 ${when} '${title}'을(를) 넣었어요`;
}
