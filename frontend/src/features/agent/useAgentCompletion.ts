// 작업이 끝나면 알린다 (FE-15 · FE-D22). 앱 틀(AppLayout)이 늘 붙여 두므로, 패널을 닫거나 다른 화면으로 옮겨도
// 대화(agentSession)는 계속 돌고 끝난 순간을 여기서 잡는다. 알릴지는 notifyDecision(순수 함수)이 정한다.
// TODO(FE-10 알림 센터): 알림 센터에 항목을 넣는 자리(훅 · 저장소)가 아직 없다(NotificationBell은 빈 틀).
// 자리가 생기면 아래 notify()에서 같은 제목 · 설명으로 한 줄을 넣는다. 알림 센터 구조는 FE-10 담당이 정한다.
import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router';
import { useToast } from '../../ui/index.ts';
import { completionText, finishedSince, notifyDecision, runningIds } from './agentNotify.ts';
import { viewerItemOf } from './agentResults.ts';
import { agentSession, type Run } from './agentSession.ts';
import { agentViewer } from './agentViewer.ts';
import { browserOptIn, browserPermission, showBrowserNotification } from './browserNotify.ts';

export const AGENT_PATH = '/agent';

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
        toast.show({
          id: toastId,
          kind: run.phase === 'fail' ? 'error' : 'info',
          title,
          description: body,
          actionLabel: '열기',
          onAction: () => {
            toast.close(toastId);
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
