// 화면은 이 파일의 dashboardApi · taskActionsApi만 쓴다. fetch를 화면에서 직접 부르지 않는다(frontend/README.md).
import { selectTaskActionsApi, type TaskStatusChange } from './actions.ts';
import { dataModeOf, selectDashboardApi } from './selectApi.ts';
import type { DashboardSource } from './types.ts';

export interface DashboardApi {
  getDashboardSource(signal?: AbortSignal): Promise<DashboardSource>;
}

const env = {
  VITE_API_MODE: import.meta.env.VITE_API_MODE,
  VITE_API_BASE: import.meta.env.VITE_API_BASE,
};

export const dashboardApi = selectDashboardApi(env, window.location);

/** 모의 데이터를 쓰는지 화면에 알리기 위한 값(불러오는 중 · 오류 화면에도 표시) */
export const dashboardDataMode = dataModeOf(env);

/** 업무 완료 · 되돌리기(FE-4). 데이터 모드는 대시보드와 같다. */
export const taskActionsApi = selectTaskActionsApi(env);

/** 모의 모드에서 대시보드를 다시 불러오면 모의 행동 상태도 그 목록 기준으로 되돌린다(모의 대시보드는 늘 원본을 준다). */
export function syncMockActions(tasks: Iterable<TaskStatusChange>): void {
  if ('reset' in taskActionsApi) taskActionsApi.reset(tasks);
}
