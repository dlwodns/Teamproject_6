// 화면은 이 파일의 dashboardApi만 쓴다. fetch를 화면에서 직접 부르지 않는다(frontend/README.md).
import { readApiConfig } from './config.ts';
import { createHttpApi } from './httpClient.ts';
import { createMockApi, readMockPreview } from './mockClient.ts';
import type { DashboardSource } from './types.ts';

export interface DashboardApi {
  getDashboardSource(signal?: AbortSignal): Promise<DashboardSource>;
}

function createDashboardApi(): DashboardApi {
  let config;
  try {
    config = readApiConfig({
      VITE_API_MODE: import.meta.env.VITE_API_MODE,
      VITE_API_BASE: import.meta.env.VITE_API_BASE,
    });
  } catch (e) {
    return { getDashboardSource: () => Promise.reject(e) };
  }
  return config.mode === 'mock' ? createMockApi(readMockPreview(window.location.search)) : createHttpApi(config.baseUrl);
}

export const dashboardApi = createDashboardApi();
