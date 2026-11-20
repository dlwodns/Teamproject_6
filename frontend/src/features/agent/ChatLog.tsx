// 캐치봇 대화 목록 (components.md 4.4 · FE-11 · FE-15). 캐치봇 화면(#/agent/chat)의 대화 메뉴가 쓴다.
// 11-15: 오른쪽 패널을 없애고 캐치봇은 상단 메뉴 화면 하나로 합쳤다(reminders.md 12.8). 입력은 화면 아래 하나를 모든 메뉴가 함께 쓴다.
// - 결과(초안 · 요약 · 업무 목록)는 대화에 짧은 카드('초안 1건 · 열기')만 두고, 누르면 오른쪽 결과물 칸에 연다
import {
  AwaitingCard,
  ConfirmCard,
  DraftCard,
  NoticeCard,
  PersonCard,
  QueryCard,
  ResultCard,
  ResultLinkCard,
  SummaryCard,
  UnsupportedCard,
  type SenderOf,
} from './AgentCards.tsx';
import { viewerItemOf } from './agentResults.ts';
import { agentCardId, agentConfirmId, agentSession, type Run, type SessionState } from './agentSession.ts';
import { INTRO_EXAMPLES } from './agentText.ts';
import { agentViewer } from './agentViewer.ts';
import styles from './ChatLog.module.css';
import { ExampleList } from './ExampleList.tsx';
import { StepLine } from './StepLine.tsx';

interface ChatLogProps {
  state: SessionState;
  onRun: (text: string) => void;
  senderOf: SenderOf;
  asOfMs: number;
  results?: RunViewProps['results'];
}

/** 대화 목록: 대화가 없으면 소개 · 예시, 있으면 말풍선과 작업 카드 */
export function ChatLog({ state, onRun, senderOf, asOfMs, results }: ChatLogProps) {
  if (state.entries.length === 0) {
    // 소개 · 예시는 대화가 없을 때만. 대화가 시작되면 화면을 대화에 내준다(예시는 '지원하지 않는 요청' 카드에 다시 나온다)
    return (
      <div className={styles.intro}>
        <p className={styles.introText}>말이나 글로 요청하시면 처리합니다. 여러 건을 변경할 때는 먼저 확인을 요청합니다.</p>
        <ExampleList examples={INTRO_EXAMPLES} onRun={onRun} label="예시 명령" />
      </div>
    );
  }
  return (
    <ol className={styles.entries} aria-label="대화">
      {state.entries.map((e) =>
        e.kind === 'user' ? (
          <li key={e.id} className={styles.bubble}>
            {e.text}
          </li>
        ) : (
          <li key={e.id}>
            <RunView run={e} onRun={onRun} senderOf={senderOf} asOfMs={asOfMs} results={results} />
          </li>
        ),
      )}
    </ol>
  );
}
/** 입력 영역 표시. 에이전트 화면에서 Ctrl+J가 이 안의 입력칸으로 포커스를 옮긴다 */
export const AGENT_PROMPT_ATTR = 'data-agent-prompt';

export function focusAgentPrompt(): boolean {
  const el = document.querySelector<HTMLTextAreaElement>(`[${AGENT_PROMPT_ATTR}] textarea`);
  el?.focus();
  return Boolean(el);
}

interface RunViewProps {
  run: Run;
  onRun: (text: string) => void;
  senderOf: SenderOf;
  asOfMs: number;
  /** 있으면(에이전트 화면) 결과물로 여는 결과를 짧은 카드로 보인다 */
  results?: { openRunId: number | null; onOpen: (runId: number) => void };
}

function RunView({ run, onRun, senderOf, asOfMs, results }: RunViewProps) {
  const o = run.outcome;
  const cardId = agentCardId(run.id);
  const link = results ? viewerItemOf(run) : null;
  return (
    <div className={styles.run}>
      <StepLine run={run} onStop={() => agentSession.stop(run.id)} />
      {link && results ? (
        <ResultLinkCard
          id={cardId}
          title={link.title}
          label={link.label}
          open={results.openRunId === run.id}
          onOpen={() => results.onOpen(run.id)}
        />
      ) : (
        <>
          {o?.type === 'confirm' && (
            <ConfirmCard
              id={agentConfirmId(run.id)}
              title={o.title}
              action={o.action}
              targets={o.targets}
              senderOf={senderOf}
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
              notes={o.notes}
              onUndo={() => void agentSession.undoResult(run.id)}
            />
          )}
          {o?.type === 'query' && (
            <QueryCard id={cardId} title={o.title} targets={o.targets} notes={o.notes} senderOf={senderOf} mails={o.mails} lines={o.lines}
              onOpenMail={(mailId) => agentViewer.openMail(run.id, mailId)} />
          )}
          {o?.type === 'person' && <PersonCard id={cardId} title={o.title} person={o.person} targets={o.targets} notes={o.notes} mentioned={o.mails} onOpenMail={(mailId) => agentViewer.openMail(run.id, mailId)} />}
          {o?.type === 'summary' && <SummaryCard id={cardId} title={o.title} summary={o.summary} asOfMs={asOfMs} senderOf={senderOf} />}
          {o?.type === 'awaiting' && <AwaitingCard id={cardId} title={o.title} items={o.items} />}
          {o?.type === 'draft' && <DraftCard id={cardId} title={o.title} draft={o.draft} />}
          {o?.type === 'notice' && <NoticeCard id={cardId} title={o.title} hint={o.hint} />}
          {o?.type === 'error' && <NoticeCard title={o.title} hint={o.hint} />}
          {o?.type === 'unsupported' && (
            <UnsupportedCard title={o.title} hint={o.hint} examples={o.examples} onRun={onRun} choices={o.choices} senderOf={senderOf}
              onPick={(taskId) => agentSession.submit(run.text, { taskIds: [taskId], selectedMailIds: [] })} />
          )}
        </>
      )}
    </div>
  );
}
