// 업무 완료 · 되돌리기(FE-4, wireframe 13절 업무 체크 · 13-6 토스트).
// 체크하면 먼저 화면에서 빼고(줄이 바로 사라짐) 서버에 보낸다. 응답이 오면 그 상태로 다시 집계하고,
// 실제 모드에서는 /api/dashboard를 조용히 다시 받아 응답에 없는 값(리마인더 수 등)까지 맞춘다.
// 실패하면 원래 상태로 돌리고 오류 토스트를 띄운다.
import { useCallback, useRef, useState } from 'react';
import type { TaskActionsApi } from '../../api/actions.ts';
import type { Task, TaskId } from '../../api/types.ts';
import type { useToast } from '../toast/ToastProvider.tsx';
import { actionErrorText } from './taskStatusUpdate.ts';
import type { DashboardControls } from './useDashboard.ts';

type ShowToast = ReturnType<typeof useToast>;
type Dashboard = Pick<DashboardControls, 'applyChanges' | 'setPending' | 'refresh'>;

export interface TaskActions {
  complete: (task: Task) => void;
  /** 서버 응답을 기다리는 업무. 같은 업무를 두 번 보내지 않게 체크 상자를 잠근다 */
  busy: ReadonlySet<TaskId>;
}

export function useTaskActions(api: TaskActionsApi, dashboard: Dashboard, toast: ShowToast): TaskActions {
  const { applyChanges, setPending, refresh } = dashboard;
  const [busy, setBusy] = useState<ReadonlySet<TaskId>>(new Set());
  const inFlight = useRef(new Set<TaskId>()); // 상태 갱신 전에 연달아 눌러도 막는다

  const mark = useCallback((id: TaskId, on: boolean) => {
    if (on) inFlight.current.add(id);
    else inFlight.current.delete(id);
    setBusy(new Set(inFlight.current));
  }, []);

  const undo = useCallback(
    (actionId: number) => {
      api.undo(actionId).then(
        (out) => {
          applyChanges(out.tasks);
          refresh();
          toast({ kind: 'info', text: '되돌렸어요' });
        },
        (e: unknown) => toast({ kind: 'error', text: actionErrorText('되돌리지', e) }),
      );
    },
    [api, applyChanges, refresh, toast],
  );

  const complete = useCallback(
    (task: Task) => {
      if (task.status === 'done' || inFlight.current.has(task.id)) return;
      const before = { id: task.id, status: task.status };
      mark(task.id, true);
      setPending(task.id, 'done'); // 이 체크가 끝나기 전에 온 조용한 다시 불러오기가 줄을 되살리지 않게
      applyChanges([{ id: task.id, status: 'done' }]);
      api
        .setTaskStatus(task.id, 'done')
        .then(
          (out) => {
            setPending(task.id, null);
            applyChanges(out.tasks); // 서버가 돌려준 상태가 기준
            refresh();
            const actionId = out.actionId;
            toast(
              actionId === null
                ? { kind: 'info', text: `이미 완료된 업무예요: ${task.text}` }
                : { kind: 'info', text: `완료로 바꿨어요: ${task.text}`, action: { label: '되돌리기', run: () => undo(actionId) } },
            );
          },
          (e: unknown) => {
            setPending(task.id, null);
            applyChanges([before]);
            toast({ kind: 'error', text: actionErrorText('완료로 바꾸지', e) });
          },
        )
        .finally(() => mark(task.id, false));
    },
    [api, applyChanges, setPending, refresh, toast, undo, mark],
  );

  return { complete, busy };
}
