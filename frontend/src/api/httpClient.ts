// 실제 모드: backend를 부른다. 개발 서버에서는 Vite 프록시(vite.config.ts)가 /api/... 를 backend로 넘긴다.
// 실패하면 오류를 그대로 올린다. 모의 데이터로 대신하지 않는다.
// ai 서비스는 부르지 않는다(backend만 부른다, D34).
import { toDashboardSource } from './adapter.ts';
import type { DashboardApi } from './client.ts';
import { ContractError, HttpError } from './errors.ts';

// [제안] 구조도 8절 GET /dashboard. backend 미구현(BE-3). 응답 형식은 provisional.ts의 FE 임시 가정이다.
const DASHBOARD_PATH = '/dashboard';

export function createHttpApi(baseUrl: string): DashboardApi {
  return {
    async getDashboardSource(signal) {
      const res = await fetch(`${baseUrl}${DASHBOARD_PATH}`, { headers: { Accept: 'application/json' }, signal });
      if (!res.ok) throw new HttpError(res.status, `${baseUrl}${DASHBOARD_PATH} 응답 ${res.status}`);
      let body: unknown;
      try {
        body = await res.json();
      } catch {
        throw new ContractError('응답이 JSON이 아니다');
      }
      return toDashboardSource(body, { kind: 'http', baseUrl });
    },
  };
}
