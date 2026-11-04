import { useCallback, useEffect, useState } from 'react';
import { dashboardApi } from '../../api/client.ts';
import type { DataOrigin } from '../../api/types.ts';
import { buildDashboard, type DashboardView } from './aggregate.ts';

export type DashboardState =
  | { kind: 'loading' }
  | { kind: 'error'; error: unknown }
  | { kind: 'ready'; view: DashboardView; origin: DataOrigin };

export function useDashboard(): { state: DashboardState; reload: () => void } {
  const [state, setState] = useState<DashboardState>({ kind: 'loading' });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState({ kind: 'loading' });
    dashboardApi
      .getDashboardSource(controller.signal)
      .then((src) => setState({ kind: 'ready', view: buildDashboard(src), origin: src.origin }))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setState({ kind: 'error', error });
      });
    return () => controller.abort();
  }, [attempt]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  return { state, reload };
}
