// 실제 모드: backend를 부른다. 개발 서버에서는 Vite 프록시(vite.config.ts)가 /api/... 를 backend로 넘긴다.
// 실패하면 오류를 그대로 올린다. 모의 데이터로 대신하지 않는다.
// ai 서비스는 부르지 않는다(backend만 부른다, D34).
import { toDashboardSource } from './adapter.ts';
import type { DashboardApi } from './client.ts';
import { ContractError, HttpError, NetworkError } from './errors.ts';

// [제안] 구조도 8절 GET /dashboard. backend 미구현(BE-3). 응답 형식은 provisional.ts의 FE 임시 가정이다.
const DASHBOARD_PATH = '/dashboard';

export function createHttpApi(baseUrl: string): DashboardApi {
  return {
    async getDashboardSource(signal) {
      let res: Response;
      try {
        res = await fetch(`${baseUrl}${DASHBOARD_PATH}`, { headers: { Accept: 'application/json' }, signal });
      } catch (e) {
        // 요청 경계에서만 구분한다: 취소는 그대로(화면이 무시), fetch의 TypeError는 네트워크 실패.
        // 이 밖(응답 읽기 · 변환)에서 나는 TypeError는 프로그래밍 오류라 NetworkError로 바꾸지 않는다
        if (signal?.aborted) throw e;
        if (e instanceof TypeError) throw new NetworkError('서버에 연결하지 못했다', { cause: e });
        throw e;
      }
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
