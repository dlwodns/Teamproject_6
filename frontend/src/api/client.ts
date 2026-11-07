// 화면은 이 파일의 dashboardApi만 쓴다. fetch를 화면에서 직접 부르지 않는다(frontend/README.md).
import { selectDashboardApi } from './selectApi.ts';
import type { DashboardSource } from './types.ts';

export interface DashboardApi {
  getDashboardSource(signal?: AbortSignal): Promise<DashboardSource>;
}

export const dashboardApi = selectDashboardApi(
  {
    VITE_API_MODE: import.meta.env.VITE_API_MODE,
    VITE_API_BASE: import.meta.env.VITE_API_BASE,
  },
  window.location,
);
