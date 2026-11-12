// 업무 완료 · 되돌리기(FE-4, wireframe 13절 업무 체크 · 13-6 토스트).
// 체크하면 먼저 화면에서 빼고(줄이 바로 사라짐) 서버에 보낸다. 실패하면 원래 상태로 돌리고 오류 토스트를 띄운다.
import { useCallback, useRef, useState } from 'react';
import type { TaskActionsApi, TaskStatusChange } from '../../api/actions.ts';
import type { Task, TaskId } from '../../api/types.ts';
import type { useToast } from '../toast/ToastProvider.tsx';
import { actionErrorText } from './taskStatusUpdate.ts';

type ShowToast = ReturnType<typeof useToast>;

export interface TaskActions {
  complete: (task: Task) => void;
  /** 서버 응답을 기다리는 업무. 같은 업무를 두 번 보내지 않게 체크 상자를 잠근다 */
  busy: ReadonlySet<TaskId>;
}

export function useTaskActions(api: TaskActionsApi, applyChanges: (c: readonly TaskStatusChange[]) => void, toast: ShowToast): TaskActions {
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
          toast({ kind: 'info', text: '되돌렸어요' });
        },
        (e: unknown) => toast({ kind: 'error', text: actionErrorText('되돌리지', e) }),
      );
    },
    [api, applyChanges, toast],
  );

  const complete = useCallback(
    (task: Task) => {
      if (task.status === 'done' || inFlight.current.has(task.id)) return;
      const before: TaskStatusChange = { id: task.id, status: task.status };
      mark(task.id, true);
      applyChanges([{ id: task.id, status: 'done' }]);
      api
        .setTaskStatus(task.id, 'done')
        .then(
          (out) => {
            applyChanges(out.tasks); // 서버가 돌려준 상태가 기준
            const actionId = out.actionId;
            toast(
              actionId === null
                ? { kind: 'info', text: `이미 완료된 업무예요: ${task.text}` }
                : { kind: 'info', text: `완료로 바꿨어요: ${task.text}`, action: { label: '되돌리기', run: () => undo(actionId) } },
            );
          },
          (e: unknown) => {
            applyChanges([before]);
            toast({ kind: 'error', text: actionErrorText('완료로 바꾸지', e) });
          },
        )
        .finally(() => mark(task.id, false));
    },
    [api, applyChanges, toast, undo, mark],
  );

  return { complete, busy };
}
