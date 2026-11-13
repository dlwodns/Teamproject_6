// 에이전트 화면 #/agent (FE-15 · FE-D20). 화면을 세로로 반씩 나눈다.
// - 왼쪽: 대화. 패널과 같은 부품(AgentWorkspace)이고 대화도 하나라, 패널에서 [크게 보기]를 누르면 그 대화가 그대로 이어진다.
//   [대화 · 제안 · 기록] 탭과 ⋯ → '에이전트가 아는 것'도 패널과 같은 자리에 둔다(FE-D20: 두 모양을 따로 익히지 않게)
// - 오른쪽: 결과물. 대화의 짧은 카드 [열기]로 고른 결과를 크게 연다(ResultViewer). 처음에는 빈 상태
// - 이 화면에서는 떠 있는 패널을 열지 않는다(앱 틀). Ctrl+J는 입력칸으로 포커스를 옮긴다
import { useId, useMemo, useState } from 'react';
import { useDashboardQuery } from '../../api/queries.ts';
import { AGENT_NAME } from '../../features/agent/agentBrand.tsx';
import { openedRun } from '../../features/agent/agentResults.ts';
import { agentViewer, useAgentViewer } from '../../features/agent/agentViewer.ts';
import { AgentMenu, AgentWorkspace, type WorkspaceView } from '../../features/agent/AgentWorkspace.tsx';
import { senderLookup } from '../../features/agent/agentText.ts';
import { useBrowserNotify } from '../../features/agent/browserNotify.ts';
import { ResultViewer } from '../../features/agent/ResultViewer.tsx';
import { useAgentSession } from '../../features/agent/useAgentSession.ts';
import { Checkbox } from '../../ui/index.ts';
import styles from './AgentPage.module.css';

const ROOT_ID = 'agent-page';
const VIEWER_ID = 'agent-viewer';
const NO_MAILS: never[] = [];

function BrowserNotifyToggle() {
  const { on, permission, toggle } = useBrowserNotify();
  if (permission === 'unsupported') return null;
  if (permission === 'denied') return <span className={styles.note}>브라우저 알림이 막혀 있어요</span>;
  return <Checkbox checked={on} onCheckedChange={(v) => void toggle(v)} label={<span className={styles.note}>작업이 끝나면 브라우저 알림 받기</span>} />;
}

export function AgentPage() {
  const [view, setView] = useState<WorkspaceView>('tabs');
  const state = useAgentSession(NO_MAILS);
  const { openRunId } = useAgentViewer();
  const dashboard = useDashboardQuery();
  const senderOf = useMemo(() => senderLookup(dashboard.data), [dashboard.data]);
  const asOfMs = dashboard.data?.asOfMs ?? Date.now();
  const viewerHeadingId = useId();
  // 좁은 화면(1024px 미만)은 결과물 칸이 대화 아래에 쌓이므로, 열면 그 칸으로 굴려 보인다
  const results = useMemo(
    () => ({
      openRunId,
      onOpen: (runId: number) => {
        agentViewer.open(runId);
        if (window.matchMedia('(width < 1024px)').matches) document.getElementById(VIEWER_ID)?.scrollIntoView({ block: 'start' });
      },
    }),
    [openRunId],
  );
  const run = openedRun(state.entries, openRunId);

  return (
    <div className={styles.page} id={ROOT_ID}>
      <section className={styles.chat} aria-labelledby="page-title">
        <div className={styles.chatHead}>
          <h1 id="page-title" className={styles.title} tabIndex={-1}>
            {AGENT_NAME}
          </h1>
          <AgentMenu onMemory={() => setView('memory')} />
        </div>
        <div className={styles.chatBody}>
          <AgentWorkspace rootId={ROOT_ID} view={view} onViewChange={setView} results={results} />
        </div>
      </section>
      <ResultViewer id={VIEWER_ID} run={run} senderOf={senderOf} asOfMs={asOfMs} headingId={viewerHeadingId} headExtra={<BrowserNotifyToggle />} />
    </div>
  );
}
