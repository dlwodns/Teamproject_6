// FE-4 업무 상태 토스트의 문구와 규칙(wireframe 13-6 · design_system 5절 '~해요' 체 · components.md 8절).
// 토스트 모양 · 자리 · 시간은 ui/Toast(FE-13), 언제 무엇을 띄울지는 여기, 띄우는 곳은 features/tasks/useTaskActions.ts 하나다.
//
// - 성공: 바뀐 업무가 있으면 '되돌리기' 토스트(8초). 이미 그 상태라 바뀐 것이 없으면(actionId null) 되돌릴 것이 없으니 정보 토스트.
// - 되돌리기 성공: '되돌렸어요'(정보).
// - 실패: 오류 토스트. 다시 해 볼 만한 실패(연결 · 시간 초과 · 서버 오류)에만 [다시 시도]를 붙인다.
//   이미 다른 곳에서 바뀐 경우(409)처럼 같은 요청을 다시 보내도 소용없는 실패에는 붙이지 않는다.
//   실패해도 대시보드는 다시 불러와 서버 값으로 맞춰진다(useTaskActions finally) — 시간 초과로 서버는 처리했을 수 있다.
import { ConfigError, ContractError, HttpError, NetworkError, NotAvailableError } from '../api/errors.ts';

export type TaskChange = 'done' | 'snoozed' | 'excluded';

export interface ToastCopy {
  title: string;
  description?: string;
}

const CHANGED: Record<TaskChange, (n: number) => string> = {
  done: (n) => `업무 ${n}건을 완료로 바꿨어요`,
  snoozed: (n) => `업무 ${n}건을 나중에로 미뤘어요`,
  excluded: (n) => `업무 ${n}건을 제외했어요`,
};

const ALREADY: Record<TaskChange, string> = {
  done: '이미 완료된 업무예요',
  snoozed: '이미 나중에로 미뤄 둔 업무예요',
  excluded: '이미 제외된 업무예요',
};

const FAILED: Record<TaskChange | 'undo', string> = {
  done: '완료로 바꾸지 못했어요',
  snoozed: '나중에로 미루지 못했어요',
  excluded: '제외하지 못했어요',
  undo: '되돌리지 못했어요',
};

export const UNDONE_TITLE = '되돌렸어요';

/** 같은 업무가 여러 번 들어와도 한 번으로 센다(planStatusCall과 같은 기준) */
export function countTasks(taskIds: readonly unknown[]): number {
  return new Set(taskIds).size;
}

/** 바뀐 것이 있으면 되돌리기 토스트, 없으면(actionId null) 정보 토스트 */
export function changedToast(change: TaskChange, count: number, actionId: number | null): ToastCopy & { undoable: boolean } {
  if (actionId === null) return { title: ALREADY[change], undoable: false };
  return { title: CHANGED[change](count), undoable: true };
}

/**
 * 실패 안내. 서버 오류 원문 · 주소는 보이지 않는다. retry는 [다시 시도]를 붙일지.
 * 401은 시연 서버에서 사용자 확인 헤더가 빠졌을 때 나온다(#44 · BE-D16) — 다시 눌러도 같아서 붙이지 않는다.
 */
export function failureToast(what: TaskChange | 'undo', error: unknown): ToastCopy & { retry: boolean } {
  const title = FAILED[what];
  if (error instanceof NetworkError) return { title, description: '서버에 연결하지 못했어요', retry: true };
  if (error instanceof NotAvailableError) return { title, description: '서버에 아직 없는 기능이에요', retry: false };
  if (error instanceof HttpError) {
    if (error.status === 409) return { title, description: '이미 다른 곳에서 바뀌었어요. 화면을 서버 값으로 다시 맞췄어요', retry: false };
    if (error.status === 404) return { title, description: '업무나 기록을 찾지 못했어요', retry: false };
    if (error.status === 401) return { title, description: '사용자 확인이 필요해요. 담당자에게 알려 주세요', retry: false };
    if (error.status === 422) return { title, description: '보낸 값이 맞지 않아요. 담당자에게 알려 주세요', retry: false };
    return { title, description: `잠시 뒤 다시 시도해 주세요(오류 코드 ${error.status})`, retry: true };
  }
  if (error instanceof ContractError) return { title, description: '받은 응답을 읽지 못했어요. 담당자에게 알려 주세요', retry: false };
  if (error instanceof ConfigError) return { title, description: '화면 설정에 문제가 있어요. 담당자에게 알려 주세요', retry: false };
  return { title, description: '잠시 뒤 다시 시도해 주세요', retry: true };
}
