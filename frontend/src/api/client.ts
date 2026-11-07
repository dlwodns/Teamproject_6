// 화면은 이 파일의 dashboardApi만 쓴다. fetch를 화면에서 직접 부르지 않는다(frontend/README.md).
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
