// 환경 변수와 주소로 데이터 소스를 고른다. 화면 코드는 client.ts의 dashboardApi만 쓴다.
// mock 쿼리(?mock=…)는 모의 모드에서만 읽는다. http 모드에서는 주소에 mock이 있어도 데이터 소스가 바뀌지 않는다.
import type { DashboardApi } from './client.ts';
import { readApiConfig } from './config.ts';
import { createHttpApi } from './httpClient.ts';
import { createMockApi, readMockPreview } from './mockClient.ts';

/** 화면 표시용 데이터 모드. 설정 오류면 null(오류 화면이 따로 안내한다). */
export function dataModeOf(env: { VITE_API_MODE?: string; VITE_API_BASE?: string }): 'mock' | 'http' | null {
  try {
    return readApiConfig(env).mode;
  } catch {
    return null;
  }
}

export function selectDashboardApi(
  env: { VITE_API_MODE?: string; VITE_API_BASE?: string },
  location: { search: string; hash: string },
): DashboardApi {
  let config;
  try {
    config = readApiConfig(env);
  } catch (e) {
    return { getDashboardSource: () => Promise.reject(e) };
  }
  return config.mode === 'mock' ? createMockApi(readMockPreview(location.search, location.hash)) : createHttpApi(config.baseUrl);
}
