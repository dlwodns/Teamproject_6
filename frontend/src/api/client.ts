// 화면은 이 파일의 api(또는 queries.ts의 훅)만 쓴다. fetch를 화면에서 직접 부르지 않는다(frontend/README.md).
import type { ApiClient, DashboardApi } from './contract.ts';
import { asDashboardApi, dataModeOf, selectApi } from './selectApi.ts';
import { readApiConfig } from './config.ts';
import { startSession } from './session.ts';

export type { DashboardApi } from './contract.ts';

// node --test에서도 이 파일을 불러올 수 있게(useTaskActions 판단 시험) Vite 밖이면 빈 값으로 읽는다.
// 빈 값이면 기본인 모의 모드가 되고, 시험은 api를 부르지 않으므로 데이터를 받지 않는다
const viteEnv = import.meta.env as Partial<ImportMetaEnv> | undefined;
const env = {
  VITE_API_MODE: viteEnv?.VITE_API_MODE,
  VITE_API_BASE: viteEnv?.VITE_API_BASE,
  VITE_USER_ID: viteEnv?.VITE_USER_ID,
  VITE_MOCK_DATASET: viteEnv?.['VITE_MOCK_DATASET'] as string | undefined,
};
const location = typeof window === 'undefined' ? { search: '', hash: '' } : window.location;

/** 모의 · 실제 중 하나. 앱 전체가 이 하나를 나눠 쓴다(모의 모드의 메모리 상태도 하나) */
export const api: ApiClient = selectApi(env, location);

export const dashboardApi: DashboardApi = asDashboardApi(api);

/** 모의 데이터를 쓰는지 화면에 알리기 위한 값(불러오는 중 · 오류 화면에도 표시) */
export const dashboardDataMode = dataModeOf(env);

/** 실제 모드에서 화면을 띄우기 전에 브라우저 세션을 받는다(backend AUTH_MODE=session, INF-11 11-25).
 *  AUTH_MODE=header backend는 아무것도 하지 않는다. 모의 모드 · 설정 오류면 바로 끝난다 */
export const sessionReady: Promise<void> =
  dashboardDataMode === 'http' ? startSession(readApiConfig(env).baseUrl) : Promise.resolve();
