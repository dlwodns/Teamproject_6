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
} from './adapter.ts';
import type { ApiClient } from './contract.ts';
import { ConfigError, HttpError, NotAvailableError } from './errors.ts';
import type {
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
}

// ── 메모리 상태 ──

interface TaskExtra {
  doneAtMs: number | null;
  snoozedUntilMs: number | null;
  statusChangedAtMs: number | null;
}

type Snapshot = TaskExtra & { status: string };

interface MockAction {
  id: number;
  kind: 'change' | 'undo';
  undoneId: number | null; // kind가 undo일 때 되돌린 기록 id
  taskIds: number[];
  before: Map<number, Snapshot>;
  undone: boolean;
}

interface MockBulkPreview {
  taskIds: number[];
  status: TaskStatus;
  snoozedUntilMs: number | null;
  expiresAtMs: number;
  used: boolean;
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
  asOfMs: number;
  startedAtMs: number;
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

  function record(s: MockState, kind: MockAction['kind'], tasks: ProvisionalTask[], undoneId: number | null): MockAction {
    const action: MockAction = {
      id: s.actions.length + 1,
      kind,
      undoneId,
      taskIds: tasks.map((t) => t.id),
      before: new Map(tasks.map((t) => [t.id, { status: t.status, ...s.extra.get(t.id)! }])),
      undone: false,
    };
    s.actions.push(action);
    return action;
  }

  /** 이미 그 상태(나중에면 같은 시각까지)인 업무는 건드리지 않고, 바뀐 업무가 없으면 기록도 남기지 않는다 */
  function changeStatus(s: MockState, ids: readonly number[], status: TaskStatus, until: number | null) {
    checkChange(status, until);
    const tasks = findTasks(s, ids);
    const changed = tasks.filter((t) => t.status !== status || s.extra.get(t.id)!.snoozedUntilMs !== until);
    if (changed.length === 0) return toActionResult({ action_id: null, tasks: tasks.map((t) => stateOf(s, t)) });
    const action = record(s, 'change', changed, null);
    const at = now(s);
    for (const t of changed) {
      t.status = status;
      s.extra.set(t.id, {
        doneAtMs: status === 'done' ? at : null,
        snoozedUntilMs: status === 'snoozed' ? until : null,
        statusChangedAtMs: at,
      });
    }
    return toActionResult({ action_id: action.id, tasks: tasks.map((t) => stateOf(s, t)) });
  }

  function undo(s: MockState, actionId: number) {
    const target = s.actions.find((a) => a.id === actionId);
    if (!target) throw new HttpError(404, `되돌릴 수 있는 기록이 없습니다: ${actionId}`);
    if (target.undone) throw new HttpError(409, '이미 되돌린 기록입니다');
    // BE-4를 줄인 규칙: 뒤에 같은 업무를 바꾼 '살아 있는 보통 변경'이 있으면 덮어쓰지 않는다(409).
    // 되돌리기 기록을 되돌리는 것(다시 하기)은 뒤에 같은 업무를 건드린 기록이 하나도 없을 때만
    const later = s.actions.filter((a) => a.id > target.id && a.taskIds.some((id) => target.before.has(id)));
    const blocked = target.kind === 'undo' ? later.length > 0 : later.some((a) => a.kind === 'change' && !a.undone);
    if (blocked) throw new HttpError(409, '이 기록 뒤에 같은 업무를 바꾼 기록이 있어 되돌릴 수 없습니다');
    const tasks = findTasks(s, target.taskIds);
    const back = record(s, 'undo', tasks, target.id);
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
    return toUndoResult({ action_id: back.id, undone_action_id: target.id, tasks: tasks.map((t) => stateOf(s, t)) });
  }

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
      return changeStatus(s, [id], change.status, change.snoozedUntilMs ?? null);
    },

    async bulkPreview(request) {
      const s = await begin();
      const until = request.snoozedUntilMs ?? null;
      checkChange(request.status, until);
      if (request.taskIds.length === 0) throw new HttpError(422, '업무를 하나 이상 골라 주세요');
      const tasks = findTasks(s, request.taskIds);
      const previewId = `mock-preview-${s.nextPreview++}`;
      const expiresAtMs = now(s) + PREVIEW_TTL_MS;
      s.previews.set(previewId, { taskIds: tasks.map((t) => t.id), status: request.status, snoozedUntilMs: until, expiresAtMs, used: false });
      return toBulkPreview({
        preview_id: previewId,
        expires_at: toKstIso(expiresAtMs),
        status: request.status,
        snoozed_until: iso(until),
        targets: tasks.map((t) => ({ id: t.id, text: t.text, status: t.status })),
      });
    },

    async executeAction(previewId) {
      const s = await begin();
      const p = s.previews.get(previewId);
      if (!p) throw new HttpError(404, '없는 미리보기입니다');
      if (p.used) throw new HttpError(409, '이미 실행한 미리보기입니다');
      if (p.expiresAtMs < now(s)) throw new HttpError(409, '만료된 미리보기입니다. 다시 미리보기를 받아 주세요');
      p.used = true;
      return changeStatus(s, p.taskIds, p.status, p.snoozedUntilMs);
    },

    async undoAction(actionId) {
      return undo(await begin(), actionId);
    },

    async getNotifications(signal) {
      const s = await begin(signal);
      return toNotifications({ items: preview === 'empty' ? [] : s.notifications });
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
  };
}
