// 환경 변수와 주소로 데이터 소스를 고른다. 화면 코드는 client.ts의 api만 쓴다.
// mock 쿼리(?mock=…)와 VITE_MOCK_DATASET은 모의 모드에서만 읽는다. http 모드에서는 주소에 mock이 있어도 데이터 소스가 바뀌지 않는다.
import { readApiConfig } from './config.ts';
import type { ApiClient, DashboardApi } from './contract.ts';
import { createHttpApi } from './httpClient.ts';
import { createMockApi, readMockDataset, readMockPreview } from './mockClient.ts';

export interface ApiEnv {
  VITE_API_MODE?: string;
  VITE_API_BASE?: string;
  VITE_USER_ID?: string;
  VITE_MOCK_DATASET?: string;
}

/** 화면 표시용 데이터 모드. 설정 오류면 null(오류 화면이 따로 안내한다). */
export function dataModeOf(env: ApiEnv): 'mock' | 'http' | null {
  try {
    return readApiConfig(env).mode;
  } catch {
    return null;
  }
}

// 설정이 잘못되면 모든 요청이 그 설정 오류로 실패한다(앱은 뜨고, 화면마다 오류 상태를 보인다)
function failingApi(error: unknown): ApiClient {
  const fail = () => Promise.reject(error);
  return {
    getDashboard: fail,
    patchTaskStatus: fail,
    bulkPreview: fail,
    executeAction: fail,
    undoAction: fail,
    runAgentCommand: fail,
    getNotifications: fail,
    patchNotification: fail,
    getSettings: fail,
    patchSettings: fail,
    patchContact: fail,
    getContacts: fail,
    getAwaiting: fail,
    getMail: fail,
    summarizeMail: fail,
    sendReply: fail,
    polishReply: fail,
    getSuggestions: fail,
    hideSuggestion: fail,
    getActionHistory: fail,
    getAgentMemory: fail,
    patchAgentMemoryMe: fail,
    patchAgentMemoryPerson: fail,
    getAgentSettings: fail,
    patchAgentSettings: fail,
    patchMail: fail, // FE-5d
    getCalendar: fail, // FE-12 캘린더
    addCalendarEvent: fail,
    removeCalendarEvent: fail,
    // FE-16 리마인더
    getReminders: fail,
    dismissReminder: fail,
    applyReminder: fail,
    setReminderTypeNotify: fail,
    getBriefing: fail,
    readAllNotifications: fail,
  };
}

export function selectApi(env: ApiEnv, location: { search: string; hash: string }): ApiClient {
  try {
    const config = readApiConfig(env);
    if (config.mode === 'http') return createHttpApi(config.baseUrl, config.userId);
    return createMockApi({ preview: readMockPreview(location.search, location.hash), dataset: readMockDataset(env.VITE_MOCK_DATASET) });
  } catch (e) {
    return failingApi(e);
  }
}

/** 옛 대시보드 화면용 좁은 창구(같은 클라이언트를 감싼다) */
export function asDashboardApi(api: ApiClient): DashboardApi {
  return { getDashboardSource: (signal) => api.getDashboard(signal) };
}

export function selectDashboardApi(env: ApiEnv, location: { search: string; hash: string }): DashboardApi {
  return asDashboardApi(selectApi(env, location));
}
