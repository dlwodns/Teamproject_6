// 에이전트 세션(agentSession)을 화면에 잇는다. 서버는 api(contract.ts)로만 부른다: 명령 runAgentCommand,
// 확인 카드 실행 executeAction(preview_id, 체크한 업무), 되돌리기는 useTaskActions().undo(결과 카드에 자기 [실행 취소]가 있어 toast: false).
// 상태가 바뀐 뒤에는 useTaskActions와 같은 키(queryKeys.dashboard)로 원자료를 다시 불러온다.
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useSyncExternalStore } from 'react';
import { api } from '../../api/client.ts';
import { queryKeys } from '../../api/queries.ts';
import type { MailId } from '../../api/types.ts';
import { useTaskActions } from '../tasks/useTaskActions.ts';
import { agentSession, type SessionState } from './agentSession.ts';

export function useAgentSession(selectedMailIds: readonly MailId[]): SessionState {
  const actions = useTaskActions();
  const queryClient = useQueryClient();
  const selectedKey = selectedMailIds.join(',');

  useEffect(() => {
    const ids = selectedKey ? selectedKey.split(',').map((v) => Number(v) as MailId) : [];
    agentSession.setDeps({
      runCommand: (request, signal) => api.runAgentCommand(request, signal),
      execute: (previewId, taskIds) => api.executeAction(previewId, taskIds),
      undo: (actionId) => actions.undo(actionId, { source: 'agent', toast: false }),
      refresh: () => void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard }),
      selectedMailIds: () => ids,
      now: () => Date.now(),
    });
  }, [actions, queryClient, selectedKey]);

  return useSyncExternalStore(agentSession.subscribe, agentSession.getState);
}
