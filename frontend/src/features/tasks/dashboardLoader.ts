// 대시보드 데이터 한 번 불러오기. 돌려준 함수를 부르면 이 요청을 취소하고, 취소된 요청은 성공하든 실패하든 상태를 바꾸지 않는다.
// API가 AbortSignal을 무시하고 늦게 끝나도(이전 요청이 나중에 도착해도) 최신 요청의 상태를 덮지 않는다.
import type { TaskStatusChange } from '../../api/actions.ts';
import type { DashboardApi } from '../../api/client.ts';
import type { DashboardSource, DataOrigin } from '../../api/types.ts';
import { buildDashboard, type DashboardView } from './aggregate.ts';
import { applyTaskStatuses } from './taskStatusUpdate.ts';

export type DashboardState =
  | { kind: 'loading' }
  | { kind: 'error'; error: unknown }
  | { kind: 'ready'; view: DashboardView; origin: DataOrigin; source: DashboardSource }; // source: 완료 · 되돌리기 뒤 다시 집계할 원본(FE-4)

export function startDashboardLoad(api: DashboardApi, setState: (s: DashboardState) => void): () => void {
  const controller = new AbortController();
  setState({ kind: 'loading' });
  api
    .getDashboardSource(controller.signal)
    .then((src) => {
      if (controller.signal.aborted) return; // 취소된 요청이면 집계도 하지 않는다
      setState({ kind: 'ready', view: buildDashboard(src), origin: src.origin, source: src }); // 집계 오류는 아래 catch로
    })
    .catch((error: unknown) => {
      if (controller.signal.aborted) return;
      // 개발 중에만 종류 · 메시지를 남긴다(응답 본문 · 토큰은 넣지 않음, 오류 메시지에도 응답 값을 넣지 않는다)
      if (import.meta.env?.DEV) console.warn('[대시보드] 불러오기 실패', error instanceof Error ? `${error.name}: ${error.message}` : typeof error);
      setState({ kind: 'error', error });
    });
  return () => controller.abort();
}

/**
 * 조용한 다시 불러오기(FE-4): 완료 · 되돌리기 응답 뒤 /api/dashboard를 다시 받아 서버 값(리마인더 수 등)과 맞춘다.
 * - '불러오는 중'으로 바꾸지 않는다(화면이 깜빡이지 않음). 실패하면 지금 화면을 그대로 둔다.
 * - 나중에 시작한 요청만 반영한다(먼저 시작한 요청이 늦게 와도 버림).
 * - 받은 원본 위에 아직 서버 응답을 기다리는 체크(pending)를 덮어써서, 진행 중인 체크가 되살아나지 않게 한다.
 */
export function createSilentRefresher(
  api: DashboardApi,
  pending: () => readonly TaskStatusChange[],
  apply: (src: DashboardSource) => void,
): { refresh: () => void; dispose: () => void } {
  let latest = 0;
  let controller: AbortController | null = null;
  return {
    refresh() {
      const seq = ++latest;
      controller?.abort();
      const c = (controller = new AbortController());
      api.getDashboardSource(c.signal).then(
        (src) => {
          if (seq !== latest || c.signal.aborted) return;
          apply(applyTaskStatuses(src, pending()));
        },
        (error: unknown) => {
          if (seq !== latest || c.signal.aborted) return;
          if (import.meta.env?.DEV) console.warn('[대시보드] 조용한 다시 불러오기 실패', error instanceof Error ? error.name : typeof error);
        },
      );
    },
    dispose() {
      latest++;
      controller?.abort();
    },
  };
}
