// 실제 모드: backend를 부른다. 개발 서버에서는 Vite 프록시(vite.config.ts)가 /api/... 를 backend로 넘긴다.
// 실패하면 오류를 그대로 올린다. 모의 데이터로 대신하지 않는다.
// ai 서비스는 부르지 않는다(backend만 부른다, D34).
import { toDashboardSource } from './adapter.ts';
import type { DashboardApi } from './client.ts';
import { ContractError, HttpError, NetworkError } from './errors.ts';

// [제안] 구조도 8절 GET /dashboard. backend 미구현(BE-3). 응답 형식은 provisional.ts의 FE 임시 가정이다.
const DASHBOARD_PATH = '/dashboard';

/** 대시보드 조회 제한 시간(FE-D14). 응답 헤더 · 본문을 다 받을 때까지 센다. */
export const REQUEST_TIMEOUT_MS = 15_000;

export function createHttpApi(baseUrl: string): DashboardApi {
  return {
    async getDashboardSource(signal) {
      // 화면 쪽 취소 신호와 제한 시간 신호를 함께 건다. 어느 쪽이 걸렸는지는 따로 기억한다:
      // 화면 취소는 그대로 올리고(화면이 무시), 제한 시간 초과는 연결 실패(NetworkError)로 올린다.
      const controller = new AbortController();
      let timedOut = false;
      const timer = setTimeout(() => {
        timedOut = true;
        controller.abort(new DOMException('요청 제한 시간 초과', 'TimeoutError'));
      }, REQUEST_TIMEOUT_MS);
      const onCancel = () => controller.abort(signal?.reason);
      if (signal?.aborted) onCancel();
      else signal?.addEventListener('abort', onCancel, { once: true });

      const timeoutError = (cause: unknown) =>
        new NetworkError(`서버가 ${REQUEST_TIMEOUT_MS / 1000}초 안에 응답하지 않았다`, { cause });

      try {
        let res: Response;
        try {
          res = await fetch(`${baseUrl}${DASHBOARD_PATH}`, { headers: { Accept: 'application/json' }, signal: controller.signal });
        } catch (e) {
          // 요청 경계에서만 구분한다: 취소는 그대로(화면이 무시), 제한 시간 초과 · fetch의 TypeError는 네트워크 실패.
          // 이 밖(응답 읽기 · 변환)에서 나는 TypeError는 프로그래밍 오류라 NetworkError로 바꾸지 않는다
          if (signal?.aborted) throw e;
          if (timedOut) throw timeoutError(e);
          if (e instanceof TypeError) throw new NetworkError('서버에 연결하지 못했다', { cause: e });
          throw e;
        }
        if (!res.ok) throw new HttpError(res.status, `${baseUrl}${DASHBOARD_PATH} 응답 ${res.status}`);
        let body: unknown;
        try {
          body = await res.json();
        } catch (e) {
          // 본문을 읽다가 끊긴 것은 형식 오류가 아니다: 화면 취소는 그대로, 제한 시간 초과는 NetworkError
          if (signal?.aborted) throw e;
          if (timedOut) throw timeoutError(e);
          throw new ContractError('응답이 JSON이 아니다');
        }
        return toDashboardSource(body, { kind: 'http', baseUrl });
      } finally {
        clearTimeout(timer);
        signal?.removeEventListener('abort', onCancel);
      }
    },
  };
}
