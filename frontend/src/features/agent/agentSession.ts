// 에이전트 대화 · 실행 흐름 (components.md 4.4 · UX-D8 · D37). React 밖의 보통 객체라 node --test로 흐름 전체를 시험한다.
// 패널을 닫았다 열어도 대화가 남도록 모듈에 하나만 둔다(agentSession).
// 데이터 경계는 하나다: runCommand(POST /api/agent/command) → AgentResult. 대상 찾기 · 확인 판정 · 실행은 서버가 하고,
// 여기서는 kind에 따라 카드를 고른다. 확인 카드 실행은 executeAction(preview_id, 체크한 업무), 결과 카드 [실행 취소]는 undo.
//
// - 단계가 바뀔 때만 announcement를 바꾼다(패널의 role="status" 하나가 읽는다). 진행 글자를 흘려 읽히지 않는다
// - 작업 카드 [취소](stop, 예전 [중지])는 실행 단계 전까지만 받는다. 요청을 보낸 뒤 취소하면 서버가 이미 처리했을 수 있어
//   '바뀐 것은 없어요'를 말하지 않고 기록 탭에서 되돌릴 수 있다고 알린다(FE-15)
// - 상태가 바뀌었을 수 있는 일(결과 · 실행 · 되돌리기 · 중지) 뒤에는 refresh()로 ['dashboard']를 다시 불러온다
import type { ActionResult, AgentCommandRequest, AgentDraft, AgentMail, AgentPerson, AgentResult, AgentSource, AgentSummary, AgentTarget, UndoResult } from '../../api/contract.ts';
import { AgentUnavailableError, AGENT_UNAVAILABLE_TEXT, HttpError } from '../../api/errors.ts';
import type { Awaiting, MailId, TaskId } from '../../api/types.ts';
import { activeLabel, announceText, MODEL_TIMEOUT_SEC, SHOW_ELAPSED_FROM_SEC, STOPPED_UNSURE_TEXT, stepsFor, understandNote, type RunPhase, type StepKey, type StepStatus } from './agentSteps.ts';
import { executedTitle, EXPIRED_TEXT, FALLBACK_EXAMPLES, resultMailIds, UNDO_BLOCKED_TEXT, undoFailState, undoneActionId, withStates } from './agentText.ts';

/** blocked = 서버가 409로 거절(이미 되돌렸거나 뒤에 같은 업무를 바꾼 기록이 있음) — 다시 눌러도 계속 실패하므로 버튼을 거둔다(#60 리뷰) */
export type UndoState = 'idle' | 'pending' | 'done' | 'error' | 'blocked';

/** 명령과 함께 보낼 대상(없으면 주소의 고른 메일) */
export interface SubmitOptions {
  selectedMailIds?: MailId[];
  /** 고른 리마인더의 업무(FE-16) */
  taskIds?: TaskId[];
  reminderKey?: string;
}

export type Outcome =
  | { type: 'confirm'; title: string; action: string | null; targets: AgentTarget[]; expiresAtMs: number | null }
  | { type: 'result'; title: string; targets: AgentTarget[]; actionId: number | null; undo: UndoState; notes: string[] }
  | { type: 'query'; title: string; targets: AgentTarget[]; notes: string[]; mails?: AgentMail[]; lines?: string[] }
  | { type: 'summary'; title: string; summary: AgentSummary }
  | { type: 'awaiting'; title: string; items: Awaiting[] }
  | { type: 'draft'; title: string; draft: AgentDraft }
  | { type: 'person'; title: string; person: AgentPerson; targets: AgentTarget[]; notes: string[] }
  | { type: 'notice'; title: string; hint: string | null }
  | { type: 'unsupported'; title: string; hint: string; examples: readonly string[]; choices?: AgentTarget[] }
  | { type: 'error'; title: string; hint: string };

export interface Run {
  kind: 'run';
  id: number;
  text: string;
  action: string | null;
  source: AgentSource | null;
  steps: StepKey[];
  status: StepStatus[];
  notes: Partial<Record<StepKey, string>>;
  phase: RunPhase;
  /** 요청이 서버에 간 뒤 중지했다(처리됐을 수 있음) */
  unsure: boolean;
  startedAtMs: number;
  endedAtMs: number | null;
  outcome: Outcome | null;
}

export interface UserEntry {
  kind: 'user';
  id: number;
  text: string;
}

export type Entry = UserEntry | Run;

export interface FocusRequest {
  /** 'input' 또는 요소 id(agentCardId · agentConfirmId) */
  target: string;
  seq: number;
}

export interface SessionState {
  entries: Entry[];
  /** 화면 읽기 프로그램에 알릴 단계 문구 */
  announcement: string;
  /** 명령 하나가 진행 중(확인 대기 포함) */
  busy: boolean;
  /** 직전 결과 대상의 메일 id. 다음 명령의 last_result_ids('그 2건') */
  lastResultIds: MailId[];
  focus: FocusRequest | null;
}

export interface SessionDeps {
  runCommand(request: AgentCommandRequest, signal: AbortSignal): Promise<AgentResult>;
  execute(previewId: string, taskIds: readonly TaskId[]): Promise<ActionResult>;
  undo(actionId: number): Promise<UndoResult>;
  /** 원자료 다시 불러오기(['dashboard']) */
  refresh(): void;
  selectedMailIds(): MailId[];
  /** 벽시계(경과 초 · 확인 만료) */
  now(): number;
}

export const agentCardId = (runId: number) => `agent-card-${runId}`;
export const agentConfirmId = (runId: number) => `agent-confirm-${runId}`;

/** 서버 미리보기 유효 시간(backend `task_status.PREVIEW_TTL` 5분) */
export const PREVIEW_TTL_MS = 5 * 60_000;

/**
 * 서버가 준 만료 시각을 브라우저 시계의 마감으로 바꾼다. 서버는 시연 시각(CLOCK_START)으로 과거나 미래에 있을 수 있어
 * 두 시계의 차가 5분을 넘으면 서버 시각을 믿지 않고 받은 때부터 5분으로 잰다(#62 리뷰). 마지막 판정은 서버 409가 한다
 */
export function localDeadline(serverExpiresAtMs: number | null, nowMs: number): number | null {
  if (serverExpiresAtMs === null) return null;
  const left = serverExpiresAtMs - nowMs;
  return nowMs + (left > 0 && left <= PREVIEW_TTL_MS ? left : PREVIEW_TTL_MS);
}

const STOP = 'stop';
const TIMEOUT = 'timeout';

interface Waiting {
  previewId: string;
  action: string | null;
  targets: AgentTarget[];
  expiresAtMs: number | null;
  timer: ReturnType<typeof setTimeout> | null;
}

const UNSUPPORTED_HINT = '메일 업무 조회 · 처리만 지원합니다. 아래와 같이 요청해 주십시오.';
const NOT_READY_HINT = '서버에 아직 없는 기능입니다. 아래와 같이 요청해 주십시오.';
const ASK_HINT = '조금 더 구체적으로 말씀해 주십시오. 아래와 같이 요청하실 수 있습니다.';

export type AgentSession = ReturnType<typeof createAgentSession>;

export function createAgentSession() {
  let state: SessionState = { entries: [], announcement: '', busy: false, lastResultIds: [], focus: null };
  let deps: SessionDeps | null = null;
  const listeners = new Set<() => void>();
  let controller: AbortController | null = null;
  const waiting = new Map<number, Waiting>();
  let nextId = 1;
  let focusSeq = 0;

  function set(patch: Partial<SessionState>) {
    state = { ...state, ...patch };
    for (const l of listeners) l();
  }

  function findRun(id: number): Run | undefined {
    return state.entries.find((e): e is Run => e.kind === 'run' && e.id === id);
  }

  function updateRun(id: number, fn: (r: Run) => Run, extra: Partial<SessionState> = {}) {
    set({ ...extra, entries: state.entries.map((e) => (e.kind === 'run' && e.id === id ? fn(e) : e)) });
  }

  const focusOn = (target: string): FocusRequest => ({ target, seq: ++focusSeq });

  function setStatus(r: Run, step: StepKey, status: StepStatus): Run {
    const i = r.steps.indexOf(step);
    if (i < 0) return r;
    const next = [...r.status];
    next[i] = status;
    return { ...r, status: next };
  }

  const markDone = (r: Run, ...keys: StepKey[]) => keys.reduce((x, k) => setStatus(x, k, 'done'), r);

  function finish(id: number, phase: Exclude<RunPhase, 'running'>, patch: (r: Run) => Run, extra: Partial<SessionState> = {}) {
    const now = deps?.now() ?? Date.now();
    controller = null;
    updateRun(id, (r) => ({ ...patch(r), phase, endedAtMs: now }), { busy: false, ...extra });
  }

  /** 그 단계를 실패로, 남은 단계는 건너뜀으로 두고 펼친 채 멈춘다 */
  function failAt(id: number, step: StepKey, outcome: Outcome, announcement: string, note?: string) {
    finish(
      id,
      'fail',
      (r) => {
        const status = r.status.map((s, i) => (r.steps[i] === step ? 'fail' : s === 'pending' || s === 'active' || s === 'wait' ? 'skip' : s));
        return { ...r, status, outcome, notes: note === undefined ? r.notes : { ...r.notes, [step]: note } };
      },
      { announcement },
    );
  }

  /** 요청 실패 → 사용자에게 보일 글자. 503(AI를 쓸 수 없음) · 서버 거절(HttpError)은 상태가 바뀌지 않았다 */
  function requestError(e: unknown, timedOut: boolean): Extract<Outcome, { type: 'error' }> {
    if (timedOut) {
      return { type: 'error', title: `${MODEL_TIMEOUT_SEC}초 안에 처리하지 못했습니다`, hint: '처리 여부를 업무 목록에서 확인하신 뒤 다시 요청해 주십시오.' };
    }
    if (e instanceof AgentUnavailableError) return { type: 'error', title: AGENT_UNAVAILABLE_TEXT, hint: '변경된 내용은 없습니다.' };
    if (e instanceof HttpError && e.status === 422) return { type: 'error', title: '요청을 접수하지 못했습니다', hint: '500자 이내로 줄여 다시 요청해 주십시오.' };
    if (e instanceof HttpError) return { type: 'error', title: '요청을 처리하지 못했습니다', hint: '변경된 내용은 없습니다. 잠시 후 다시 요청해 주십시오.' };
    return { type: 'error', title: '요청을 처리하지 못했습니다', hint: '처리 여부를 업무 목록에서 확인하신 뒤 다시 요청해 주십시오.' };
  }

  async function run(id: number, text: string, signal: AbortSignal, opts: SubmitOptions) {
    const d = deps!;
    // 명령 이해가 3초를 넘으면(엑사원 경로) 문구가 바뀌므로 그때 한 번 알린다. 30초를 넘으면 멈춘다
    const slow = setTimeout(() => {
      const r = findRun(id);
      if (r?.phase === 'running' && r.status[0] === 'active') set({ announcement: `엑사원이 명령을 해석하는 중 (최대 ${MODEL_TIMEOUT_SEC}초)` });
    }, SHOW_ELAPSED_FROM_SEC * 1000);
    const timeout = setTimeout(() => controller?.abort(TIMEOUT), MODEL_TIMEOUT_SEC * 1000);
    let result: AgentResult;
    try {
      result = await d.runCommand(
        {
          text,
          selectedMailIds: opts.selectedMailIds ?? d.selectedMailIds(),
          lastResultIds: state.lastResultIds,
          ...(opts.taskIds && opts.taskIds.length > 0 ? { taskIds: opts.taskIds } : {}),
          ...(opts.reminderKey ? { reminderKey: opts.reminderKey } : {}),
        },
        signal,
      );
    } catch (e) {
      if (signal.reason === STOP) return; // stop()이 이미 끝냈다
      const timedOut = signal.reason === TIMEOUT;
      if (timedOut) d.refresh();
      const outcome = requestError(e, timedOut);
      failAt(id, 'understand', outcome, outcome.title);
      return;
    } finally {
      clearTimeout(slow);
      clearTimeout(timeout);
    }
    if (signal.aborted) return; // 응답이 온 뒤 중지 · 초기화됐다
    handle(id, result);
  }

  function handle(id: number, res: AgentResult) {
    const d = deps!;
    const steps = stepsFor(res.action);
    const note = understandNote(res.action, res.actionName, res.source);
    updateRun(id, (r) => ({
      ...r,
      action: res.action,
      source: res.source,
      steps,
      status: steps.map((): StepStatus => 'pending'),
      notes: note ? { understand: note } : {},
    }));
    const lastResultIds = res.targets.length ? resultMailIds(res.targets) : state.lastResultIds;
    const withTargetNote = (r: Run): Run => (res.targets.length ? { ...r, notes: { ...r.notes, target: `대상 ${res.targets.length}건` } } : r);

    switch (res.kind) {
      case 'confirm': {
        if (res.previewId === null) {
          updateRun(id, (r) => markDone(r, 'understand', 'target'));
          failAt(id, 'confirm', { type: 'error', title: '확인 카드를 만들지 못했습니다', hint: '변경된 내용은 없습니다. 다시 요청해 주십시오.' }, '확인 카드를 만들지 못했습니다');
          return;
        }
        const expiresAtMs = localDeadline(res.expiresAtMs, d.now());
        const w: Waiting = { previewId: res.previewId, action: res.action, targets: res.targets, expiresAtMs, timer: null };
        if (expiresAtMs !== null) w.timer = setTimeout(() => expire(id), expiresAtMs - d.now());
        waiting.set(id, w);
        updateRun(
          id,
          (r) => ({
            ...setStatus(withTargetNote(markDone(r, 'understand', 'target')), 'confirm', 'wait'),
            outcome: { type: 'confirm', title: res.title, action: res.action, targets: res.targets, expiresAtMs: res.expiresAtMs },
          }),
          { announcement: `확인이 필요합니다. ${res.title}`, focus: focusOn(agentConfirmId(id)), lastResultIds },
        );
        return;
      }
      case 'done': {
        d.refresh();
        // '방금 거 취소해'(T04)가 되돌린 기록이 이 패널의 결과 카드면 그 [실행 취소]를 '취소했습니다'로 바꾼다
        const undoneId = res.action === 'T04' ? undoneActionId(res.notes) : null;
        if (undoneId !== null) {
          for (const e of state.entries) {
            if (e.kind === 'run' && e.outcome?.type === 'result' && e.outcome.actionId === undoneId) {
              updateRun(e.id, (r) => (r.outcome?.type === 'result' ? { ...r, outcome: { ...r.outcome, undo: 'done' } } : r));
            }
          }
        }
        finish(
          id,
          'done',
          (r) => ({
            ...setStatus(withTargetNote(markDone(r, 'understand', 'target', 'exec')), 'confirm', 'skip'),
            outcome: { type: 'result', title: res.title, targets: res.targets, actionId: res.actionId, undo: 'idle', notes: res.notes },
          }),
          { announcement: res.title, focus: focusOn(agentCardId(id)), lastResultIds },
        );
        return;
      }
      case 'query':
      case 'person':
      case 'summary':
      case 'awaiting':
      case 'draft': {
        let outcome: Outcome;
        let ids = lastResultIds;
        if (res.kind === 'query') {
          outcome = { type: 'query', title: res.title, targets: res.targets, notes: res.notes, mails: res.mails, lines: res.lines };
          if (res.mails?.length) ids = res.mails.map((m) => m.mailId); // '그 메일 요약해줘' 다음 명령의 직전 결과(11-18 메일 찾기)
        }
        else if (res.kind === 'person' && res.person) {
          outcome = { type: 'person', title: res.title, person: res.person, targets: res.targets, notes: res.notes };
          ids = res.person.mails.map((m) => m.mailId); // '그 메일 중 …' 다음 명령의 직전 결과
        }
        else if (res.summary) outcome = { type: 'summary', title: res.title, summary: res.summary };
        else if (res.awaiting) {
          outcome = { type: 'awaiting', title: res.title, items: res.awaiting };
          ids = resultMailIds(res.awaiting);
        } else if (res.draft) outcome = { type: 'draft', title: res.title, draft: res.draft };
        else outcome = { type: 'notice', title: res.title, hint: null };
        finish(id, 'done', (r) => ({ ...withTargetNote(markDone(r, 'understand', 'target', 'exec')), outcome }), {
          announcement: res.title,
          focus: focusOn(agentCardId(id)),
          lastResultIds: ids,
        });
        return;
      }
      case 'empty': {
        const hint = res.notes.length ? `찾은 조건: ${res.notes.join(' · ')}` : null;
        updateRun(id, (r) => markDone(r, 'understand'));
        failAt(id, 'target', { type: 'notice', title: res.title, hint }, res.title, '0건');
        return;
      }
      case 'ask':
      case 'unsupported': {
        const notReady = res.kind === 'unsupported' && res.action !== null;
        const hint = res.kind === 'ask' ? [...res.notes, ASK_HINT].join(' ') : notReady ? NOT_READY_HINT : UNSUPPORTED_HINT;
        // 11-19 되묻기에 후보 업무가 실려 오면(T16 '하나를 골라 주십시오') 그 목록을 고르게 보인다
        const choices = res.kind === 'ask' && res.targets.length > 0 ? res.targets : undefined;
        failAt(id, 'understand', { type: 'unsupported', title: res.title, hint, examples: FALLBACK_EXAMPLES, ...(choices ? { choices } : {}) }, res.title, note ?? undefined);
        return;
      }
    }
  }

  function dropWaiting(runId: number): Waiting | undefined {
    const w = waiting.get(runId);
    if (!w) return undefined;
    if (w.timer !== null) clearTimeout(w.timer);
    waiting.delete(runId);
    return w;
  }

  /** 확인 시간이 지났다. 미리보기만 있었으므로 바뀐 것은 없다 */
  function expire(runId: number) {
    if (!dropWaiting(runId)) return;
    failAt(runId, 'confirm', { type: 'notice', title: EXPIRED_TEXT, hint: '변경된 내용은 없습니다.' }, EXPIRED_TEXT);
  }

  async function execute(runId: number, w: Waiting, ids: TaskId[]) {
    const d = deps!;
    const chosen = w.targets.filter((t) => ids.includes(t.id));
    updateRun(runId, (r) => setStatus(setStatus(r, 'confirm', 'done'), 'exec', 'active'), {
      announcement: announceText(activeLabel('exec', w.action)),
    });
    let result: ActionResult;
    try {
      result = await d.execute(w.previewId, ids);
    } catch (e) {
      d.refresh();
      // 409 = 만료(또는 이미 실행). 서버가 거절했으니 바뀐 것은 없다. 연결 실패는 처리됐는지 알 수 없다
      const outcome: Outcome =
        e instanceof HttpError && e.status === 409
          ? { type: 'notice', title: EXPIRED_TEXT, hint: '변경된 내용은 없습니다.' }
          : {
              type: 'error',
              title: '변경하지 못했습니다',
              hint: e instanceof HttpError ? '변경된 내용은 없습니다. 다시 요청해 주십시오.' : '처리 여부를 업무 목록에서 확인해 주십시오.',
            };
      failAt(runId, 'exec', outcome, outcome.title);
      return;
    }
    d.refresh();
    const title = executedTitle(w.action, chosen.length, result);
    finish(
      runId,
      'done',
      (r) => ({
        ...setStatus(r, 'exec', 'done'),
        outcome: { type: 'result', title, targets: withStates(chosen, result), actionId: result.actionId, undo: 'idle', notes: [] },
      }),
      { announcement: title, focus: focusOn(agentCardId(runId)), lastResultIds: resultMailIds(chosen) },
    );
  }

  return {
    getState: (): SessionState => state,

    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },

    /** 화면이 그릴 때마다 최신 값으로 바꿔 끼운다 */
    setDeps(next: SessionDeps) {
      deps = next;
    },

    /** 아직 아무 화면도 잇지 않았을 때만 기본 연결을 둔다(FE-16: 🔔 팝업처럼 패널 밖에서 명령을 보낼 때) */
    ensureDeps(next: SessionDeps) {
      deps ??= next;
    },

    /**
     * 명령 보내기. 진행 중이거나 빈 글자면 false.
     * selectedMailIds: 제안 카드 [초안 보기]처럼 대상 메일이 정해진 명령은 주소의 고른 메일 대신 이것을 보낸다
     * taskIds · reminderKey: 에이전트 화면에서 고른 리마인더(FE-16). '이거'를 그 업무로 읽게 함께 보낸다
     */
    submit(text: string, opts: SubmitOptions = {}): boolean {
      const t = text.trim();
      if (!t || state.busy || !deps) return false;
      const userId = nextId++;
      const id = nextId++;
      const run0: Run = {
        kind: 'run',
        id,
        text: t,
        action: null,
        source: null,
        steps: ['understand', 'target', 'exec'],
        status: ['active', 'pending', 'pending'],
        notes: {},
        phase: 'running',
        unsure: false,
        startedAtMs: deps.now(),
        endedAtMs: null,
        outcome: null,
      };
      set({ entries: [...state.entries, { kind: 'user', id: userId, text: t }, run0], busy: true, announcement: announceText(activeLabel('understand', null)) });
      controller = new AbortController();
      void run(id, t, controller.signal, opts);
      return true;
    },

    /** 기록 탭 [이어서 보기]: 그 미리보기의 확인 카드가 이 대화에 아직 열려 있으면 그 run id. 없으면 null(버튼을 그리지 않는다) */
    confirmRunFor(previewId: string): number | null {
      for (const [runId, w] of waiting) if (w.previewId === previewId) return runId;
      return null;
    },

    /** 그 run의 확인 카드로 포커스(대화 탭으로 옮긴 뒤 부른다) */
    focusConfirm(runId: number) {
      if (!waiting.has(runId)) return;
      set({ focus: focusOn(agentConfirmId(runId)) });
    },

    /** 확인 카드 [N건 …]. 체크를 다 풀었으면 아무것도 하지 않는다(false). 확인 시간이 지났으면 실행하지 않고 알린다 */
    confirm(runId: number, ids: readonly TaskId[]): boolean {
      const w = waiting.get(runId);
      if (!w || !deps || ids.length === 0) return false;
      if (w.expiresAtMs !== null && deps.now() >= w.expiresAtMs) {
        expire(runId);
        return false;
      }
      dropWaiting(runId);
      const keep = w.targets.filter((t) => ids.includes(t.id)).map((t) => t.id);
      void execute(runId, w, keep);
      return true;
    },

    /** 확인 카드 [취소]. 미리보기만 있었으므로 바뀐 것은 없다 */
    cancelConfirm(runId: number) {
      if (!dropWaiting(runId)) return;
      finish(
        runId,
        'cancelled',
        (r) => ({ ...r, status: r.status.map((s) => (s === 'wait' || s === 'pending' || s === 'active' ? 'skip' : s)), outcome: null }),
        { announcement: '취소했습니다. 변경된 내용은 없습니다', focus: focusOn('input') },
      );
    },

    /** [중지]. 실행 단계에 들어갔으면 받지 않는다(false) */
    stop(): boolean {
      const r = [...state.entries].reverse().find((e): e is Run => e.kind === 'run' && e.phase === 'running');
      if (!r) return false;
      const execIdx = r.steps.indexOf('exec');
      if (r.status[execIdx] === 'active' || r.status[execIdx] === 'done') return false;
      // 확인 대기 중이면 미리보기만 있다 → 바뀐 것 없음. 요청 중이면 서버가 이미 처리했을 수 있다
      const unsure = !waiting.has(r.id);
      controller?.abort(STOP);
      dropWaiting(r.id);
      if (unsure) deps?.refresh();
      finish(
        r.id,
        'stopped',
        (x) => ({ ...x, unsure, status: x.status.map((s) => (s === 'active' || s === 'wait' || s === 'pending' ? 'skip' : s)), outcome: null }),
        { announcement: unsure ? STOPPED_UNSURE_TEXT : '취소했습니다. 변경된 내용은 없습니다', focus: focusOn('input') },
      );
      return true;
    },

    /** 결과 카드 [실행 취소] */
    async undoResult(runId: number): Promise<void> {
      const r = findRun(runId);
      const o = r?.outcome;
      if (!deps || o?.type !== 'result' || o.actionId === null || o.undo === 'pending' || o.undo === 'done') return;
      const d = deps;
      const actionId = o.actionId;
      const setUndo = (undo: UndoState, extra: Partial<SessionState> = {}) =>
        updateRun(runId, (x) => (x.outcome?.type === 'result' ? { ...x, outcome: { ...x.outcome, undo } } : x), extra);
      setUndo('pending');
      try {
        await d.undo(actionId);
      } catch (e) {
        d.refresh();
        const failed = undoFailState(e);
        setUndo(failed, { announcement: failed === 'blocked' ? UNDO_BLOCKED_TEXT : '취소하지 못했습니다' });
        return;
      }
      d.refresh();
      setUndo('done', { announcement: '취소했습니다' });
    },

    /** 시험용: 처음 상태로 */
    reset() {
      controller?.abort(STOP);
      controller = null;
      for (const id of [...waiting.keys()]) dropWaiting(id);
      state = { entries: [], announcement: '', busy: false, lastResultIds: [], focus: null };
      for (const l of listeners) l();
    },
  };
}

/** 앱에 하나. 패널을 닫았다 열어도 대화가 남는다(새로고침하면 사라진다) */
export const agentSession = createAgentSession();
