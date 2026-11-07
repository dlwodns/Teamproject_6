// 대시보드 데이터 한 번 불러오기. 돌려준 함수를 부르면 이 요청을 취소하고, 취소된 요청은 성공하든 실패하든 상태를 바꾸지 않는다.
// API가 AbortSignal을 무시하고 늦게 끝나도(이전 요청이 나중에 도착해도) 최신 요청의 상태를 덮지 않는다.
import type { DashboardApi } from '../../api/client.ts';
import type { DataOrigin } from '../../api/types.ts';
import { buildDashboard, type DashboardView } from './aggregate.ts';

export type DashboardState =
  | { kind: 'loading' }
  | { kind: 'error'; error: unknown }
  | { kind: 'ready'; view: DashboardView; origin: DataOrigin };

export function startDashboardLoad(api: DashboardApi, setState: (s: DashboardState) => void): () => void {
  const controller = new AbortController();
  setState({ kind: 'loading' });
  api
    .getDashboardSource(controller.signal)
    .then((src) => {
      if (controller.signal.aborted) return; // 취소된 요청이면 집계도 하지 않는다
      setState({ kind: 'ready', view: buildDashboard(src), origin: src.origin }); // 집계 오류는 아래 catch로
    })
    .catch((error: unknown) => {
      if (controller.signal.aborted) return;
      // 개발 중에만 종류 · 메시지를 남긴다(응답 본문 · 토큰은 넣지 않음, 오류 메시지에도 응답 값을 넣지 않는다)
      if (import.meta.env?.DEV) console.warn('[대시보드] 불러오기 실패', error instanceof Error ? `${error.name}: ${error.message}` : typeof error);
      setState({ kind: 'error', error });
    });
  return () => controller.abort();
}
