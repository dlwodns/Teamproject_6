// 에이전트 대화 · 실행 흐름 (components.md 4.4 · UX-D8 · D37). React 밖의 보통 객체라 node --test로 흐름 전체를 시험한다.
// 패널을 닫았다 열어도 대화와 '방금 거'(마지막 행동)가 남도록 모듈에 하나만 둔다(agentSession).
// 서버 · 화면에 닿는 일은 모두 deps로 받는다: 명령 해석(requestPlan), 원자료, 업무 상태 바꾸기(useTaskActions).
//
// 흐름: 명령 이해(requestPlan) → 대상 찾기(resolvePlan) → (확인 카드: 대상 2건 이상 · 후보 여럿) → 실행 → 결과 카드
// - 단계가 바뀔 때만 announcement를 바꾼다(패널의 role="status" 하나가 읽는다). 진행 글자를 흘려 읽히지 않는다
// - [중지]는 실행 단계 전까지만 받는다. 서버에 바꾸기 요청을 보낸 뒤에는 '바뀐 것은 없어요'를 약속할 수 없어서다
import type { ActionResult, UndoResult } from '../../api/contract.ts';
import type { Awaiting, DashboardSource, MailId, TaskId } from '../../api/types.ts';
import { formatKstShort } from '../../lib/snooze.ts';
import { kstNaive, type ActionId, type PlanContext, type PlanResponse } from './agentMock.ts';
import {
  ambiguousHint,
  CONFIRMABLE,
  FALLBACK_EXAMPLES,
  resolvePlan,
  type LastAgentAction,
  type Resolution,
  type SummaryItem,
  type TargetItem,
} from './agentResolve.ts';
import { activeLabel, announceText, MODEL_TIMEOUT_SEC, SHOW_ELAPSED_FROM_SEC, stepsFor, type RunPhase, type StepKey, type StepStatus } from './agentSteps.ts';

export type UndoState = 'idle' | 'pending' | 'done' | 'error';

export type Outcome =
  | { type: 'confirm'; question: string; verb: 'complete' | 'snooze'; untilText: string | null; targets: TargetItem[] }
  | { type: 'result'; title: string; targets: TargetItem[]; actionId: number | null; undo: UndoState; interpretation: string[] }
  | { type: 'notice'; title: string; hint: string | null }
  | { type: 'summary'; title: string; items: SummaryItem[]; hint: string | null }
  | { type: 'awaiting'; title: string; items: Awaiting[] }
  | { type: 'draft'; mailId: MailId; subject: string; to: string; text: string }
  | { type: 'unsupported'; title: string; hint: string; examples: readonly string[] }
  | { type: 'error'; title: string; hint: string };

export interface Run {
  kind: 'run';
  id: number;
  text: string;
  action: ActionId | null;
  source: 'rule' | 'model' | null;
  steps: StepKey[];
  status: StepStatus[];
  notes: Partial<Record<StepKey, string>>;
  phase: RunPhase;
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
  lastAction: LastAgentAction | null;
  /** 직전 조회 결과 메일 id(T06 무응답 목록). '그 2건' 해석용 */
  lastResultIds: string[];
  focus: FocusRequest | null;
}

export interface SessionDeps {
  requestPlan(text: string, context: PlanContext, signal: AbortSignal): Promise<PlanResponse>;
  getData(): DashboardSource | undefined;
  selectedMailIds(): string[];
  complete(ids: readonly TaskId[]): Promise<ActionResult>;
  snooze(ids: readonly TaskId[], untilMs: number): Promise<ActionResult>;
  undo(actionId: number): Promise<UndoResult>;
  /** 벽시계(경과 초 계산) */
  now(): number;
  /** 단계가 눈에 보이게 잠깐 머무는 시간. 시험에서는 0 */
  paceMs: number;
}

export const agentCardId = (runId: number) => `agent-card-${runId}`;
export const agentConfirmId = (runId: number) => `agent-confirm-${runId}`;

const STOP = 'stop';
const TIMEOUT = 'timeout';

function wait(ms: number, signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.reject(signal.reason);
  if (ms <= 0) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener(
      'abort',
      () => {
        clearTimeout(timer);
        reject(signal.reason);
      },
      { once: true },
    );
  });
}

export type AgentSession = ReturnType<typeof createAgentSession>;

export function createAgentSession() {
  let state: SessionState = { entries: [], announcement: '', busy: false, lastAction: null, lastResultIds: [], focus: null };
  let deps: SessionDeps | null = null;
  const listeners = new Set<() => void>();
  let controller: AbortController | null = null;
  const waitingConfirm = new Map<number, Extract<Resolution, { kind: 'status' }>>();
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

  /** 단계 하나를 진행으로 두고 알린다 */
  function activate(id: number, step: StepKey) {
    const r = findRun(id);
    if (!r) return;
    updateRun(id, (x) => setStatus(x, step, 'active'), { announcement: announceText(activeLabel(step, r.action)) });
  }

  function finish(id: number, phase: Exclude<RunPhase, 'running'>, patch: (r: Run) => Run, extra: Partial<SessionState> = {}) {
    const now = deps?.now() ?? Date.now();
    controller = null;
    updateRun(id, (r) => ({ ...patch(r), phase, endedAtMs: now }), { busy: false, ...extra });
  }

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

  function context(): PlanContext {
    const d = deps!;
    const data = d.getData();
    return {
      // 모의 자료는 기준 시각(as_of)이 시연 시각이다. 실제 모드에서도 원자료 기준 시각을 '지금'으로 본다
      now: kstNaive(data?.asOfMs ?? d.now()),
      selected_mail_ids: d.selectedMailIds(),
      last_result_ids: state.lastResultIds,
    };
  }

  async function run(id: number, text: string, signal: AbortSignal) {
    const d = deps!;
    // 명령 이해가 3초를 넘으면(엑사원 경로) 문구가 바뀌므로 그때 한 번 알린다. 30초를 넘으면 멈춘다
    const slow = setTimeout(() => {
      const r = findRun(id);
      if (r?.phase === 'running' && r.status[0] === 'active') set({ announcement: `엑사원이 명령을 해석하는 중 (최대 ${MODEL_TIMEOUT_SEC}초)` });
    }, SHOW_ELAPSED_FROM_SEC * 1000);
    const timeout = setTimeout(() => controller?.abort(TIMEOUT), MODEL_TIMEOUT_SEC * 1000);
    let plan: PlanResponse;
    try {
      plan = await d.requestPlan(text, context(), signal);
    } catch {
      if (signal.reason === STOP) return;
      const timedOut = signal.reason === TIMEOUT;
      failAt(
        id,
        'understand',
        {
          type: 'error',
          title: timedOut ? `${MODEL_TIMEOUT_SEC}초 안에 해석하지 못했어요` : '명령을 해석하지 못했어요',
          hint: '바뀐 것은 없어요. 잠시 뒤 다시 말해 주세요.',
        },
        '처리하지 못했어요',
      );
      return;
    } finally {
      clearTimeout(slow);
      clearTimeout(timeout);
    }

    const src = plan.source === 'rule' ? '규칙' : '엑사원';
    if (plan.action === null) {
      const ambiguous = plan.reason === 'ambiguous';
      updateRun(id, (r) => ({ ...r, source: plan.source }));
      const title = ambiguous ? '무엇을 할지 조금 더 알려 주세요' : '지원하지 않는 요청이에요';
      failAt(
        id,
        'understand',
        {
          type: 'unsupported',
          title,
          hint: ambiguous
            ? ambiguousHint(plan.candidates, d.selectedMailIds().length > 0)
            : '메일 업무를 찾고 처리하는 일만 할 수 있어요. 이렇게 말해 보세요.',
          examples: FALLBACK_EXAMPLES,
        },
        title,
        ambiguous ? `${src} · 대상이나 때가 빠짐` : `${src} · 행동 목록(T01~T14)에 없는 요청`,
      );
      return;
    }

    const action = plan.action;
    const steps = stepsFor(action, CONFIRMABLE);
    updateRun(id, (r) => ({
      ...r,
      action,
      source: plan.source,
      steps,
      status: steps.map((_, i) => (i === 0 ? 'done' : 'pending')),
      notes: { understand: `${action} ${plan.action_name ?? ''} · ${src}` },
    }));
    activate(id, 'target');
    try {
      await wait(d.paceMs, signal);
    } catch {
      return; // 중지
    }

    const res = resolvePlan(plan, d.getData(), { lastAction: state.lastAction });
    if (res.kind === 'fail') {
      failAt(id, 'target', { type: 'error', title: res.title, hint: res.hint }, res.title, res.note);
      return;
    }
    updateRun(id, (r) => ({ ...setStatus(r, 'target', 'done'), notes: { ...r.notes, target: res.note } }));

    if (res.kind === 'status') {
      if (res.confirm) {
        waitingConfirm.set(id, res);
        const until = res.untilMs === null ? null : formatKstShort(res.untilMs);
        updateRun(
          id,
          (r) => ({
            ...setStatus(r, 'confirm', 'wait'),
            outcome: { type: 'confirm', question: res.question, verb: res.op, untilText: until, targets: res.targets },
          }),
          { announcement: `확인이 필요해요. ${res.question}`, focus: focusOn(agentConfirmId(id)) },
        );
        return;
      }
      updateRun(id, (r) => setStatus(r, 'confirm', 'skip'));
      await runStatus(id, res, res.targets.map((t) => t.id));
      return;
    }
    await runOther(id, res, signal);
  }

  async function runStatus(id: number, res: Extract<Resolution, { kind: 'status' }>, ids: TaskId[]) {
    const d = deps!;
    activate(id, 'exec');
    let result: ActionResult;
    try {
      result = res.op === 'complete' ? await d.complete(ids) : await d.snooze(ids, res.untilMs!);
    } catch {
      failAt(id, 'exec', { type: 'error', title: '바꾸지 못했어요', hint: '바뀐 것은 없어요. 잠시 뒤 다시 시도해 주세요.' }, '바꾸지 못했어요');
      return;
    }
    const chosen = res.targets.filter((t) => ids.includes(t.id));
    const n = chosen.length;
    const title =
      result.actionId === null
        ? '이미 그 상태라 바뀐 것이 없어요'
        : res.op === 'complete'
          ? `${n}건을 완료로 바꿨어요`
          : `${n}건을 ${formatKstShort(res.untilMs!)}까지 미뤘어요`;
    const lastAction = result.actionId === null ? state.lastAction : { runId: id, actionId: result.actionId, count: n };
    finish(
      id,
      'done',
      (r) => ({
        ...setStatus(r, 'exec', 'done'),
        outcome: { type: 'result', title, targets: chosen, actionId: result.actionId, undo: 'idle', interpretation: res.interpretation },
      }),
      { announcement: title, lastAction, focus: focusOn(agentCardId(id)) },
    );
  }

  async function runOther(id: number, res: Exclude<Resolution, { kind: 'status' | 'fail' }>, signal: AbortSignal) {
    const d = deps!;
    activate(id, 'exec');
    if (res.kind === 'undo') {
      try {
        await d.undo(res.last.actionId);
      } catch {
        failAt(id, 'exec', { type: 'error', title: '되돌리지 못했어요', hint: '잠시 뒤 다시 시도해 주세요.' }, '되돌리지 못했어요');
        return;
      }
      const title = `방금 바꾼 ${res.last.count}건을 되돌렸어요`;
      // 되돌린 결과 카드의 [실행 취소]도 '되돌렸어요'로 바꾼다(같은 행동을 두 번 되돌리지 않게)
      updateRun(res.last.runId, (r) => (r.outcome?.type === 'result' ? { ...r, outcome: { ...r.outcome, undo: 'done' } } : r));
      finish(id, 'done', (r) => ({ ...setStatus(r, 'exec', 'done'), outcome: { type: 'notice', title, hint: '바꾸기 전 상태로 돌아갔어요.' } }), {
        announcement: title,
        lastAction: null,
        focus: focusOn(agentCardId(id)),
      });
      return;
    }
    try {
      await wait(d.paceMs, signal);
    } catch {
      return;
    }
    let outcome: Outcome;
    let lastResultIds = state.lastResultIds;
    if (res.kind === 'summary') outcome = { type: 'summary', title: res.title, items: res.items, hint: res.hint };
    else if (res.kind === 'awaiting') {
      outcome = { type: 'awaiting', title: res.title, items: res.items };
      lastResultIds = res.items.map((a) => String(a.mailId));
    } else outcome = { type: 'draft', mailId: res.mailId, subject: res.subject, to: res.to, text: res.text };
    const title = outcome.type === 'draft' ? '회신 초안을 만들었어요' : outcome.title;
    finish(id, 'done', (r) => ({ ...setStatus(r, 'exec', 'done'), outcome }), { announcement: title, lastResultIds, focus: focusOn(agentCardId(id)) });
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

    /** 명령 보내기. 진행 중이거나 빈 글자면 false */
    submit(text: string): boolean {
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
        startedAtMs: deps.now(),
        endedAtMs: null,
        outcome: null,
      };
      set({ entries: [...state.entries, { kind: 'user', id: userId, text: t }, run0], busy: true, announcement: announceText(activeLabel('understand', null)) });
      controller = new AbortController();
      void run(id, t, controller.signal);
      return true;
    },

    /** 확인 카드 [N건 완료 처리]. 체크를 다 풀었으면 아무것도 하지 않는다 */
    confirm(runId: number, ids: readonly TaskId[]): boolean {
      const res = waitingConfirm.get(runId);
      if (!res || ids.length === 0) return false;
      waitingConfirm.delete(runId);
      const keep = res.targets.filter((t) => ids.includes(t.id)).map((t) => t.id);
      updateRun(runId, (r) => ({ ...setStatus(r, 'confirm', 'done'), outcome: null }));
      void runStatus(runId, res, keep);
      return true;
    },

    /** 확인 카드 [취소] */
    cancelConfirm(runId: number) {
      if (!waitingConfirm.delete(runId)) return;
      finish(
        runId,
        'cancelled',
        (r) => ({ ...r, status: r.status.map((s) => (s === 'wait' || s === 'pending' || s === 'active' ? 'skip' : s)), outcome: null }),
        { announcement: '취소했어요. 바뀐 것은 없어요', focus: focusOn('input') },
      );
    },

    /** [중지]. 실행 단계에 들어갔으면 받지 않는다(false) */
    stop(): boolean {
      const r = [...state.entries].reverse().find((e): e is Run => e.kind === 'run' && e.phase === 'running');
      if (!r) return false;
      const execIdx = r.steps.indexOf('exec');
      if (r.status[execIdx] === 'active' || r.status[execIdx] === 'done') return false;
      controller?.abort(STOP);
      waitingConfirm.delete(r.id);
      finish(
        r.id,
        'stopped',
        (x) => ({ ...x, status: x.status.map((s) => (s === 'active' || s === 'wait' || s === 'pending' ? 'skip' : s)), outcome: null }),
        { announcement: '중지했어요. 바뀐 것은 없어요', focus: focusOn('input') },
      );
      return true;
    },

    /** 결과 카드 [실행 취소] */
    async undoResult(runId: number): Promise<void> {
      const r = findRun(runId);
      const o = r?.outcome;
      if (!deps || o?.type !== 'result' || o.actionId === null || o.undo === 'pending' || o.undo === 'done') return;
      const actionId = o.actionId;
      const setUndo = (undo: UndoState, extra: Partial<SessionState> = {}) =>
        updateRun(runId, (x) => (x.outcome?.type === 'result' ? { ...x, outcome: { ...x.outcome, undo } } : x), extra);
      setUndo('pending');
      try {
        await deps.undo(actionId);
      } catch {
        setUndo('error', { announcement: '되돌리지 못했어요' });
        return;
      }
      setUndo('done', {
        announcement: '되돌렸어요',
        lastAction: state.lastAction?.runId === runId ? null : state.lastAction,
      });
    },

    /** 시험용: 처음 상태로 */
    reset() {
      controller?.abort(STOP);
      controller = null;
      waitingConfirm.clear();
      state = { entries: [], announcement: '', busy: false, lastAction: null, lastResultIds: [], focus: null };
      for (const l of listeners) l();
    },
  };
}

/** 앱에 하나. 패널을 닫았다 열어도 대화 · 마지막 행동이 남는다(새로고침하면 사라진다) */
export const agentSession = createAgentSession();
