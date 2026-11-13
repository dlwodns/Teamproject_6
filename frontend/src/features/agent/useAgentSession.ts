// 에이전트 세션(agentSession)을 화면에 잇는다. 업무 상태 바꾸기는 useTaskActions()만 부른다(components.md 5.1):
// 결과 카드에 자기 [실행 취소]가 있으므로 toast: false. 다시 불러오기(['dashboard'])는 그 훅 안에서 한다.
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useSyncExternalStore } from 'react';
import { queryKeys } from '../../api/queries.ts';
import type { DashboardSource } from '../../api/types.ts';
import { useTaskActions } from '../tasks/useTaskActions.ts';
import { requestPlan } from './agentMock.ts';
import { agentSession, type SessionState } from './agentSession.ts';

/** 단계가 눈에 보이게 머무는 시간(ms). 동작 줄이기 설정이면 줄인다 */
const PACE_MS = 400;
const PACE_REDUCED_MS = 150;

function reducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true;
}

export function useAgentSession(selectedMailIds: readonly string[]): SessionState {
  const actions = useTaskActions();
  const queryClient = useQueryClient();
  const selectedKey = selectedMailIds.join(',');

  useEffect(() => {
    const ids = selectedKey ? selectedKey.split(',') : [];
    agentSession.setDeps({
      requestPlan,
      // 가장 최근 캐시를 읽는다(실행 뒤 다시 불러온 값이 바로 다음 명령에 쓰이게)
      getData: () => queryClient.getQueryData<DashboardSource>(queryKeys.dashboard),
      selectedMailIds: () => ids,
      complete: (taskIds) => actions.complete(taskIds, { source: 'agent', toast: false }),
      snooze: (taskIds, untilMs) => actions.snooze(taskIds, untilMs, { source: 'agent', toast: false }),
      undo: (actionId) => actions.undo(actionId, { source: 'agent', toast: false }),
      now: () => Date.now(),
      paceMs: reducedMotion() ? PACE_REDUCED_MS : PACE_MS,
    });
  }, [actions, queryClient, selectedKey]);

  return useSyncExternalStore(agentSession.subscribe, agentSession.getState);
}
