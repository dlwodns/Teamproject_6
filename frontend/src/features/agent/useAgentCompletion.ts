// 작업이 끝나면 알린다 (FE-15 · FE-D22). 앱 틀(AppLayout)이 늘 붙여 두므로, 패널을 닫거나 다른 화면으로 옮겨도
// 대화(agentSession)는 계속 돌고 끝난 순간을 여기서 잡는다. 알릴지는 notifyDecision(순수 함수)이 정한다.
// 알림 센터(FE-10, FE-16에서 넘겨받아 만듦): 토스트를 띄울 때 같은 제목 · 설명으로 '알림' 탭에도 한 줄을 남긴다(localNotices).
// 토스트를 놓쳐도 🔔에서 다시 찾을 수 있다.
import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router';
import { useToast } from '../../ui/index.ts';
import { localNotices } from '../notifications/localNotices.ts';
import { completionText, finishedSince, notifyDecision, runningIds } from './agentNotify.ts';
import { viewerItemOf } from './agentResults.ts';
import { agentSession, type Run } from './agentSession.ts';
import { agentViewer } from './agentViewer.ts';
import { browserOptIn, browserPermission, showBrowserNotification } from './browserNotify.ts';

/** 결과를 여는 곳: 에이전트 화면의 대화 메뉴(FE-16, 예전 #/agent 한 화면) */
export const AGENT_PATH = '/agent/chat';

interface Where {
  panelOpen: boolean;
  onAgentPage: boolean;
}

export function useAgentCompletion(where: Where) {
  const toast = useToast();
  const navigate = useNavigate();
  const whereRef = useRef(where);
  whereRef.current = where;

  useEffect(() => {
    let prev = runningIds(agentSession.getState().entries);

    const openResult = (run: Run) => {
      if (viewerItemOf(run)) agentViewer.open(run.id);
      void navigate(AGENT_PATH);
    };

    const notify = (run: Run) => {
      const d = notifyDecision(run, {
        ...whereRef.current,
        hidden: document.hidden,
        browserOptIn: browserOptIn(),
        permission: browserPermission(),
      });
      if (d.openInViewer) agentViewer.open(run.id);
      const { title, body } = completionText(run);
      const toastId = `agent-run-${run.id}`;
      if (d.toast) {
        localNotices.add({ id: toastId, title, body, atMs: Date.now(), runId: run.id });
        toast.show({
          id: toastId,
          kind: run.phase === 'fail' ? 'error' : 'info',
          title,
          description: body,
          actionLabel: '열기',
          onAction: () => {
            toast.close(toastId);
            localNotices.markRead(toastId);
            openResult(run);
          },
          timeout: d.toastTimeout,
        });
      }
      if (d.browser)
        showBrowserNotification(title, body, toastId, () => {
          toast.close(toastId);
          openResult(run);
        });
    };

    return agentSession.subscribe(() => {
      const entries = agentSession.getState().entries;
      const done = finishedSince(prev, entries);
      prev = runningIds(entries);
      for (const run of done) notify(run);
    });
  }, [toast, navigate]);
}
