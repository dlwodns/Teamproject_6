// 대화 메뉴 (FE-16): FE-15의 '대화 · 결과물' 두 칸을 그대로 이 메뉴 안에 둔다. 입력은 화면 아래 하나를 함께 쓴다.
// - 대화의 초안 · 요약 · 업무 목록은 짧은 카드로 두고, [열기]로 오른쪽 결과물 칸에 연다(FE-D20)
// - 세션이 포커스를 바라면 따른다: 확인 카드 · 결과 카드로, 취소하면 아래 입력칸으로
import { useEffect, useId, useMemo, useRef } from 'react';
import { ChatLog } from '../../features/agent/AgentWorkspace.tsx';
import { focusAgentPrompt } from '../../features/agent/AgentWorkspace.tsx';
import type { SenderOf } from '../../features/agent/AgentCards.tsx';
import { openedRun } from '../../features/agent/agentResults.ts';
import { agentSession, type SessionState } from '../../features/agent/agentSession.ts';
import { agentViewer, useAgentViewer } from '../../features/agent/agentViewer.ts';
import { useBrowserNotify } from '../../features/agent/browserNotify.ts';
import { ResultViewer } from '../../features/agent/ResultViewer.tsx';
import { Checkbox } from '../../ui/index.ts';
import styles from './AgentPage.module.css';

const VIEWER_ID = 'agent-viewer';

function BrowserNotifyToggle() {
  const { on, permission, toggle } = useBrowserNotify();
  if (permission === 'unsupported') return null;
  if (permission === 'denied') return <span className={styles.note}>브라우저 알림이 막혀 있어요</span>;
  return <Checkbox checked={on} onCheckedChange={(v) => void toggle(v)} label={<span className={styles.note}>작업이 끝나면 브라우저 알림 받기</span>} />;
}

interface Props {
  state: SessionState;
  senderOf: SenderOf;
  asOfMs: number;
}

export function ChatView({ state, senderOf, asOfMs }: Props) {
  const { openRunId } = useAgentViewer();
  const headingId = useId();
  const viewerHeadingId = useId();
  const logRef = useRef<HTMLDivElement>(null);
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

  // 새 대화 · 카드가 생기면 맨 아래로(부드러운 스크롤을 쓰지 않는다)
  const last = state.entries[state.entries.length - 1];
  const scrollKey = `${state.entries.length}:${last?.kind === 'run' ? `${last.phase}:${last.outcome?.type ?? ''}` : ''}`;
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [scrollKey]);

  // 세션의 포커스 요청. 이 메뉴를 연 뒤에 생긴 요청만 따른다
  const handled = useRef(state.focus?.seq ?? 0);
  useEffect(() => {
    const f = state.focus;
    if (!f || f.seq <= handled.current) return;
    handled.current = f.seq;
    if (f.target === 'input') focusAgentPrompt();
    else document.getElementById(f.target)?.focus();
  }, [state.focus]);

  return (
    <div className={styles.split} data-view="both">
      <section className={styles.listCol} aria-labelledby={headingId}>
        <div className={styles.colHead}>
          <h2 id={headingId} className={styles.colTitle} tabIndex={-1} data-agent-heading="">
            대화
          </h2>
        </div>
        <div ref={logRef} className={`${styles.scroll} ${styles.chatLog}`}>
          <ChatLog state={state} onRun={(t) => agentSession.submit(t, { selectedMailIds: [] }) && focusAgentPrompt()} senderOf={senderOf} asOfMs={asOfMs} results={results} />
        </div>
      </section>
      <div className={styles.detailCol}>
        <ResultViewer id={VIEWER_ID} run={run} senderOf={senderOf} asOfMs={asOfMs} headingId={viewerHeadingId} headExtra={<BrowserNotifyToggle />} />
      </div>
    </div>
  );
}
