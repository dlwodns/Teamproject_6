import { useCallback, useEffect, useState } from 'react';
import type { TaskStatusChange } from '../../api/actions.ts';
import { dashboardApi, syncMockActions } from '../../api/client.ts';
import { buildDashboard } from './aggregate.ts';
import { startDashboardLoad, type DashboardState } from './dashboardLoader.ts';
import { applyTaskStatuses } from './taskStatusUpdate.ts';

export type { DashboardState } from './dashboardLoader.ts';

// reload나 화면 이탈로 effect가 정리되면 이전 요청을 취소한다(startDashboardLoad가 돌려준 함수)
export function useDashboard(): { state: DashboardState; reload: () => void; applyChanges: (changes: readonly TaskStatusChange[]) => void } {
  const [state, setState] = useState<DashboardState>({ kind: 'loading' });
  const [attempt, setAttempt] = useState(0);

  useEffect(
    () =>
      startDashboardLoad(dashboardApi, (s) => {
        if (s.kind === 'ready') syncMockActions(s.source.tasks);
        setState(s);
      }),
    [attempt],
  );

  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  /** 완료 · 되돌리기 결과를 반영하고 다시 집계한다. 불러오는 중 · 오류 상태에서는 아무것도 하지 않는다. */
  const applyChanges = useCallback((changes: readonly TaskStatusChange[]) => {
    setState((prev) => {
      if (prev.kind !== 'ready') return prev;
      const source = applyTaskStatuses(prev.source, changes);
      return source === prev.source ? prev : { ...prev, source, view: buildDashboard(source) };
    });
  }, []);

  return { state, reload, applyChanges };
}
