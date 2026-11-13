// 에이전트 패널 G (components.md 4.4 · wireframe 13-4 · UX-D8 · D37). 앱 틀(AppLayout)이 <AgentPanel id onClose />로 연다.
// 소개 한 줄 + 예시 명령 칩 + 대화 목록 + 아래 고정 입력 영역(선택한 메일 줄 · 입력).
// - role="status" 영역 하나를 처음부터 두고 단계가 바뀔 때만 글자를 바꾼다(agentSession.announcement)
// - 포커스: 확인 카드가 뜨면 카드로, 결과가 나오면 결과 카드로, 취소 · 중지하면 입력칸으로, 예시 칩을 누르면 입력칸으로
// - 패널은 라우터 Outlet 밖에 있어 useParams가 비므로, 고른 메일은 useMatch로 주소에서 읽는다
// 명령 해석은 모의(agentMock.ts) — BE-18이 생기면 requestPlan 연결만 바꾼다.
import { useCallback, useEffect, useRef, useState } from 'react';
import { useMatch } from 'react-router';
import { PANEL_WIDTH } from '../../app/panel.tsx';
import { useDashboardQuery } from '../../api/queries.ts';
import { LiveRegion, SidePanel } from '../../ui/index.ts';
import { AwaitingCard, ConfirmCard, DraftCard, NoticeCard, ResultCard, SummaryCard, UnsupportedCard } from './AgentCards.tsx';
import { AGENT_NAME } from './agentBrand.tsx';
import styles from './AgentPanel.module.css';
import { INTRO_EXAMPLES } from './agentResolve.ts';
import { agentCardId, agentConfirmId, agentSession, type Run } from './agentSession.ts';
import { ExampleList } from './ExampleList.tsx';
import { PromptInput } from './PromptInput.tsx';
import { SelectedMailBar } from './SelectedMailBar.tsx';
import { StepLine } from './StepLine.tsx';
import { useAgentSession } from './useAgentSession.ts';

interface Props {
  id: string;
  onClose: () => void;
}

function RunView({ run, busy, onRun }: { run: Run; busy: boolean; onRun: (text: string) => void }) {
  const o = run.outcome;
  const cardId = agentCardId(run.id);
  return (
    <div className={styles.run}>
      <StepLine run={run} onStop={() => agentSession.stop()} />
      {o?.type === 'confirm' && (
        <ConfirmCard
          id={agentConfirmId(run.id)}
          question={o.question}
          verb={o.verb}
          targets={o.targets}
          onConfirm={(ids) => agentSession.confirm(run.id, ids)}
          onCancel={() => agentSession.cancelConfirm(run.id)}
        />
      )}
      {o?.type === 'result' && (
        <ResultCard
          id={cardId}
          title={o.title}
          targets={o.targets}
          canUndo={o.actionId !== null}
          undo={o.undo}
          interpretation={o.interpretation}
          onUndo={() => void agentSession.undoResult(run.id)}
        />
      )}
      {o?.type === 'summary' && <SummaryCard id={cardId} title={o.title} items={o.items} hint={o.hint} />}
      {o?.type === 'awaiting' && <AwaitingCard id={cardId} title={o.title} items={o.items} />}
      {o?.type === 'draft' && <DraftCard id={cardId} mailId={o.mailId} subject={o.subject} to={o.to} text={o.text} />}
      {o?.type === 'notice' && <NoticeCard id={cardId} title={o.title} hint={o.hint} />}
      {o?.type === 'error' && <NoticeCard title={o.title} hint={o.hint} />}
      {o?.type === 'unsupported' && <UnsupportedCard title={o.title} hint={o.hint} examples={o.examples} busy={busy} onRun={onRun} />}
    </div>
  );
}

export function AgentPanel({ id, onClose }: Props) {
  // 메일 화면에서 고른 메일(#/mail/:box/:mailId). [빼기]로 뺀 메일은 다른 메일을 고르면 다시 보인다
  const mailMatch = useMatch('/mail/:box/:mailId');
  const routeMailId = mailMatch?.params.mailId ?? null;
  const [removedMailId, setRemovedMailId] = useState<string | null>(null);
  const selectedMailId = routeMailId !== null && routeMailId !== removedMailId ? routeMailId : null;
  const dashboard = useDashboardQuery(); // 대상 찾기에 쓰는 원자료(대시보드 · 메일 목록과 같은 캐시)
  const selectedMail = selectedMailId === null ? undefined : dashboard.data?.mails.find((m) => String(m.id) === selectedMailId);

  const state = useAgentSession(selectedMailId === null ? [] : [selectedMailId]);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const logRef = useRef<HTMLDivElement>(null);

  const submit = useCallback((text: string) => agentSession.submit(text), []);
  const runExample = useCallback((text: string) => {
    if (agentSession.submit(text)) inputRef.current?.focus();
  }, []);

  // 새 대화 · 카드가 생기면 맨 아래로(부드러운 스크롤을 쓰지 않는다)
  const lastEntry = state.entries[state.entries.length - 1];
  const scrollKey = `${state.entries.length}:${lastEntry?.kind === 'run' ? `${lastEntry.phase}:${lastEntry.outcome?.type ?? ''}` : ''}`;
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [scrollKey]);

  // 세션의 포커스 요청. 패널을 다시 열 때 지난 요청으로 제목 포커스를 빼앗지 않게, 연 뒤에 생긴 요청만 따른다
  const handledFocus = useRef(state.focus?.seq ?? 0);
  useEffect(() => {
    const f = state.focus;
    if (!f || f.seq <= handledFocus.current) return;
    handledFocus.current = f.seq;
    if (f.target === 'input') inputRef.current?.focus();
    else document.getElementById(f.target)?.focus();
  }, [state.focus]);

  return (
    <SidePanel id={id} title={AGENT_NAME} width={PANEL_WIDTH.agent} onClose={onClose}>
      <div className={styles.root}>
        <div ref={logRef} className={styles.log}>
          <div className={styles.intro}>
            <p className={styles.introText}>말이나 글로 시키면 처리해요. 여러 건을 바꿀 때는 먼저 물어봐요.</p>
            <ExampleList examples={INTRO_EXAMPLES} busy={state.busy} onRun={runExample} label="예시 명령" />
          </div>
          {state.entries.length > 0 && (
            <ol className={styles.entries} aria-label="대화">
              {state.entries.map((e) =>
                e.kind === 'user' ? (
                  <li key={e.id} className={styles.bubble}>
                    {e.text}
                  </li>
                ) : (
                  <li key={e.id}>
                    <RunView run={e} busy={state.busy} onRun={runExample} />
                  </li>
                ),
              )}
            </ol>
          )}
        </div>
        <LiveRegion>{state.announcement}</LiveRegion>
        <div className={styles.foot}>
          {selectedMailId !== null && (
            <SelectedMailBar
              subject={selectedMail?.subject ?? null}
              onRemove={() => {
                setRemovedMailId(selectedMailId);
                inputRef.current?.focus();
              }}
            />
          )}
          <PromptInput busy={state.busy} onSubmit={submit} inputRef={inputRef} />
        </div>
      </div>
    </SidePanel>
  );
}
