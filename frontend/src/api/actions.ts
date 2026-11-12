// 업무 상태 바꾸기 · 되돌리기 (FE-4). backend BE-4 API(구조도 v3.1 8절 ③)를 부른다.
//   PATCH /api/tasks/{id}            { status } → { action_id, tasks[] }
//   POST  /api/actions/{id}/undo                → { action_id, undone_action_id, tasks[] }
// 화면은 client.ts의 taskActionsApi만 쓴다. 응답은 여기서 확인한 뒤에만 화면에 넘긴다.
import { readApiConfig } from './config.ts';
import { ContractError, HttpError, NetworkError } from './errors.ts';
import { TASK_STATUSES, type TaskId, type TaskStatus } from './types.ts';

/** 업무 한 건의 바뀐 상태. backend TaskState에서 화면이 쓰는 값만 남긴다. */
export interface TaskStatusChange {
  id: TaskId;
  status: TaskStatus;
}

export interface ActionOutcome {
  /** 되돌리기에 쓰는 기록 id. 바뀐 업무가 없으면 null(되돌릴 것이 없다) */
  actionId: number | null;
  tasks: TaskStatusChange[];
}

export interface TaskActionsApi {
  setTaskStatus(id: TaskId, status: Exclude<TaskStatus, 'snoozed'>): Promise<ActionOutcome>;
  undo(actionId: number): Promise<ActionOutcome>;
}

const isStatus = (v: unknown): v is TaskStatus => typeof v === 'string' && (TASK_STATUSES as readonly string[]).includes(v);

/** backend 응답 → ActionOutcome. 형식이 다르면 ContractError(응답 값은 오류 메시지에 넣지 않는다). */
export function toActionOutcome(body: unknown): ActionOutcome {
  if (typeof body !== 'object' || body === null) throw new ContractError('행동 응답이 객체가 아니다');
  const { action_id, tasks } = body as { action_id?: unknown; tasks?: unknown };
  if (action_id !== null && !Number.isInteger(action_id)) throw new ContractError('action_id가 정수 또는 null이 아니다');
  if (!Array.isArray(tasks)) throw new ContractError('tasks가 배열이 아니다');
  return {
    actionId: action_id as number | null,
    tasks: tasks.map((t: unknown) => {
      const { id, status } = (t ?? {}) as { id?: unknown; status?: unknown };
      if (!Number.isInteger(id)) throw new ContractError('업무 id가 정수가 아니다');
      if (!isStatus(status)) throw new ContractError('업무 상태 값이 정해진 값이 아니다');
      return { id: id as TaskId, status };
    }),
  };
}

export function createHttpActionsApi(baseUrl: string, fetchFn: typeof fetch = (...a) => fetch(...a)): TaskActionsApi {
  async function send(method: 'PATCH' | 'POST', path: string, body?: unknown): Promise<ActionOutcome> {
    let res: Response;
    try {
      res = await fetchFn(`${baseUrl}${path}`, {
        method,
        headers: { Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (e) {
      if (e instanceof TypeError) throw new NetworkError('서버에 연결하지 못했다', { cause: e });
      throw e;
    }
    if (!res.ok) throw new HttpError(res.status, `${method} ${baseUrl}${path} 응답 ${res.status}`);
    let json: unknown;
    try {
      json = await res.json();
    } catch {
      throw new ContractError('응답이 JSON이 아니다');
    }
    return toActionOutcome(json);
  }
  return {
    setTaskStatus: (id, status) => send('PATCH', `/tasks/${id}`, { status }),
    undo: (actionId) => send('POST', `/actions/${actionId}/undo`),
  };
}

export interface MockActionsApi extends TaskActionsApi {
  /** 대시보드를 다시 불러왔을 때 부른다. 모의 대시보드는 늘 원본을 주므로, 바꾼 상태 · 기록을 버리고 새 목록을 기준으로 삼는다. */
  reset(tasks: Iterable<TaskStatusChange>): void;
}

/**
 * 모의 모드: 서버 없이 backend와 같은 규칙으로 흉내 낸다. 바꾼 상태는 이 탭의 메모리에만 있고 다시 불러오면 원래대로 돌아간다.
 * - 이미 그 상태면 바뀐 업무 없음(actionId null).
 * - 되돌리기는 한 번만 된다(두 번째는 409). 되돌리기도 기록이 남는다(새 actionId).
 */
export function createMockActionsApi(): MockActionsApi {
  let statuses = new Map<TaskId, TaskStatus>();
  let log = new Map<number, { before: TaskStatusChange[]; undone: boolean }>();
  let nextId = 1;

  function record(before: TaskStatusChange[], after: TaskStatusChange[]): ActionOutcome {
    const id = nextId++;
    log.set(id, { before, undone: false });
    return { actionId: id, tasks: after };
  }

  return {
    reset(tasks) {
      statuses = new Map([...tasks].map((t) => [t.id, t.status]));
      log = new Map();
    },
    async setTaskStatus(id, status) {
      const prev = statuses.get(id);
      if (prev === undefined) throw new HttpError(404, '모의 데이터에 없는 업무');
      if (prev === status) return { actionId: null, tasks: [{ id, status }] };
      statuses.set(id, status);
      return record([{ id, status: prev }], [{ id, status }]);
    },
    async undo(actionId) {
      const entry = log.get(actionId);
      if (!entry) throw new HttpError(404, '모의 기록에 없는 행동');
      if (entry.undone) throw new HttpError(409, '이미 되돌린 행동');
      entry.undone = true;
      const before = entry.before.map((t) => ({ id: t.id, status: statuses.get(t.id)! }));
      for (const t of entry.before) statuses.set(t.id, t.status);
      return record(before, entry.before);
    },
  };
}

/** 설정 오류면 모든 호출이 그 오류로 실패한다(모의 데이터로 몰래 바꾸지 않는다). */
export function selectTaskActionsApi(env: { VITE_API_MODE?: string; VITE_API_BASE?: string }): TaskActionsApi | MockActionsApi {
  let config;
  try {
    config = readApiConfig(env);
  } catch (e) {
    return { setTaskStatus: () => Promise.reject(e), undo: () => Promise.reject(e) };
  }
  return config.mode === 'mock' ? createMockActionsApi() : createHttpActionsApi(config.baseUrl);
}
