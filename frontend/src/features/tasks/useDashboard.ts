import { useCallback, useEffect, useState } from 'react';
import { dashboardApi } from '../../api/client.ts';
import { startDashboardLoad, type DashboardState } from './dashboardLoader.ts';

export type { DashboardState } from './dashboardLoader.ts';

// reload나 화면 이탈로 effect가 정리되면 이전 요청을 취소한다(startDashboardLoad가 돌려준 함수)
export function useDashboard(): { state: DashboardState; reload: () => void } {
  const [state, setState] = useState<DashboardState>({ kind: 'loading' });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => startDashboardLoad(dashboardApi, setState), [attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  return { state, reload };
}
