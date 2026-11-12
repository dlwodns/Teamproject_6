import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { TaskStatusChange } from '../../api/actions.ts';
import { dashboardApi, dashboardDataMode, syncMockActions } from '../../api/client.ts';
import type { DashboardSource, TaskId, TaskStatus } from '../../api/types.ts';
import { buildDashboard } from './aggregate.ts';
import { createSilentRefresher, startDashboardLoad, type DashboardState } from './dashboardLoader.ts';
import { applyTaskStatuses } from './taskStatusUpdate.ts';

export type { DashboardState } from './dashboardLoader.ts';

export interface DashboardControls {
  state: DashboardState;
  reload: () => void;
  /** 완료 · 되돌리기 결과를 반영하고 다시 집계한다. 불러오는 중 · 오류 상태에서는 아무것도 하지 않는다. */
  applyChanges: (changes: readonly TaskStatusChange[]) => void;
  /** 서버 응답을 기다리는 체크를 적어 둔다(null이면 지움). 조용한 다시 불러오기가 이 값을 덮지 않는다 */
  setPending: (id: TaskId, status: TaskStatus | null) => void;
  /** 실제 모드에서만 /api/dashboard를 조용히 다시 받아 맞춘다. 모의 모드는 건너뛴다(모의 대시보드는 늘 원본) */
  refresh: () => void;
}

// reload나 화면 이탈로 effect가 정리되면 이전 요청을 취소한다(startDashboardLoad가 돌려준 함수)
export function useDashboard(): DashboardControls {
  const [state, setState] = useState<DashboardState>({ kind: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const pending = useRef(new Map<TaskId, TaskStatus>());

  useEffect(
    () =>
      startDashboardLoad(dashboardApi, (s) => {
        if (s.kind === 'ready') syncMockActions(s.source.tasks);
        setState(s);
      }),
    [attempt],
  );

  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  const applyChanges = useCallback((changes: readonly TaskStatusChange[]) => {
    setState((prev) => {
      if (prev.kind !== 'ready') return prev;
      const source = applyTaskStatuses(prev.source, changes);
      return source === prev.source ? prev : { ...prev, source, view: buildDashboard(source) };
    });
  }, []);

  const setPending = useCallback((id: TaskId, status: TaskStatus | null) => {
    if (status === null) pending.current.delete(id);
    else pending.current.set(id, status);
  }, []);

  const refresher = useMemo(
    () =>
      createSilentRefresher(
        dashboardApi,
        () => [...pending.current].map(([id, status]) => ({ id, status })),
        (source: DashboardSource) => {
          let view;
          try {
            view = buildDashboard(source);
          } catch {
            return; // 형식이 어긋난 응답이면 지금 화면을 그대로 둔다(조용한 갱신은 오류 화면으로 바꾸지 않음)
          }
          setState((prev) => (prev.kind === 'ready' ? { ...prev, source, origin: source.origin, view } : prev));
        },
      ),
    [],
  );
  // 다시 불러오기(reload)를 시작하거나 화면을 떠나면 진행 중인 조용한 요청은 버린다
  useEffect(() => refresher.dispose, [attempt, refresher]);

  const refresh = useCallback(() => {
    if (dashboardDataMode === 'http') refresher.refresh();
  }, [refresher]);

  return { state, reload, applyChanges, setPending, refresh };
}
