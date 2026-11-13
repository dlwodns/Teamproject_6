// 에이전트 대화 영역 (components.md 4.4 · FE-11 · FE-15). 패널(AgentPanel)과 에이전트 화면(#/agent 왼쪽)이 같은 부품을 쓴다.
// 대화는 모듈 하나(agentSession)라 패널에서 시작한 대화가 화면에서도 그대로 이어진다.
// 소개 한 줄 + 예시 명령 칩 + 대화 목록 + 아래 고정 입력 영역(선택한 메일 줄 · 입력). 위에 [대화 · 리마인더 · 기록] 탭.
// FE-16: '제안' 탭은 '리마인더' 탭이 됐다(리마인더 목록의 앞쪽 3건, ReminderPeek). 실제 서버에 리마인더 API가 아직 없으면 제안 카드를 그대로 보인다.
// 에이전트 화면(#/agent/chat)은 탭 · 입력 없이 대화 목록(ChatLog)만 쓰고, 입력은 화면 아래 하나를 모든 메뉴가 함께 쓴다.
// - role="status" 영역 하나를 처음부터 두고 단계가 바뀔 때만 글자를 바꾼다(agentSession.announcement)
// - 포커스: 확인 카드가 뜨면 카드로, 결과가 나오면 결과 카드로, 취소하면 입력칸으로, 예시 칩을 누르면 입력칸으로
// - 패널은 라우터 Outlet 밖에 있어 useParams가 비므로, 고른 메일은 useMatch로 주소에서 읽는다
// - 열면 제안이 있을 때 제안, 없으면 대화로 시작한다. 입력은 모든 탭 아래에 그대로 있고, 글을 쓰기 시작하면 대화 탭으로 옮긴다
// - '에이전트가 아는 것'은 부르는 쪽의 ⋯ 메뉴(AgentMenu)가 연다(같은 자리 안 화면, ‹ 뒤로)
// variant='page'(FE-15): 초안 · 요약 · 업무 목록 같은 결과는 대화에 짧은 카드('초안 1건 · 열기')만 두고, 누르면 오른쪽 결과물 칸에 연다.
import { Tabs } from '@base-ui/react/tabs';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useMatch } from 'react-router';
import { useDashboardQuery, useSuggestionsQuery } from '../../api/queries.ts';
import { useRemindersQuery } from '../../api/reminders.ts';
import { ReminderPeek } from '../reminders/ReminderPeek.tsx';
import { splitQuiet, visibleItems } from '../reminders/reminderModel.ts';
import type { CommandRequest } from '../reminders/useReminderRunner.ts';
import type { MailId } from '../../api/types.ts';
import { CountBadge, Ellipsis, IconButton, LiveRegion, Menu } from '../../ui/index.ts';
import {
  AwaitingCard,
  ConfirmCard,
  DraftCard,
  NoticeCard,
  QueryCard,
  ResultCard,
  ResultLinkCard,
  SummaryCard,
  UnsupportedCard,
  type SenderOf,
} from './AgentCards.tsx';
import { AgentMemoryView } from './AgentMemoryView.tsx';
import styles from './AgentPanel.module.css';
import { landingTab } from './agentPanelPlan.ts';
import { viewerItemOf } from './agentResults.ts';
import { agentCardId, agentConfirmId, agentSession, type Run, type SessionState } from './agentSession.ts';
import { INTRO_EXAMPLES, senderLookup } from './agentText.ts';
import { ExampleList } from './ExampleList.tsx';
import { HistoryTab } from './HistoryTab.tsx';
import { PromptInput } from './PromptInput.tsx';
import { SelectedMailBar } from './SelectedMailBar.tsx';
import { StepLine } from './StepLine.tsx';
import { SuggestionsTab } from './SuggestionsTab.tsx';
import { useAgentSession } from './useAgentSession.ts';

type PanelTab = 'chat' | 'suggest' | 'history';

interface ChatLogProps {
  state: SessionState;
  onRun: (text: string) => void;
  senderOf: SenderOf;
  asOfMs: number;
  results?: RunViewProps['results'];
}

/** 대화 목록: 대화가 없으면 소개 · 예시, 있으면 말풍선과 작업 카드. 패널 대화 탭과 에이전트 화면 대화 메뉴가 같이 쓴다 */
export function ChatLog({ state, onRun, senderOf, asOfMs, results }: ChatLogProps) {
  if (state.entries.length === 0) {
    // 소개 · 예시는 대화가 없을 때만. 대화가 시작되면 화면을 대화에 내준다(예시는 '지원하지 않는 요청' 카드에 다시 나온다)
    return (
      <div className={styles.intro}>
        <p className={styles.introText}>말이나 글로 시키면 처리해요. 여러 건을 바꿀 때는 먼저 물어봐요.</p>
        <ExampleList examples={INTRO_EXAMPLES} busy={state.busy} onRun={onRun} label="예시 명령" />
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
            <RunView run={e} busy={state.busy} onRun={onRun} senderOf={senderOf} asOfMs={asOfMs} results={results} />
          </li>
        ),
      )}
    </ol>
  );
}
export type WorkspaceView = 'tabs' | 'memory';

/** 입력 영역 표시. 에이전트 화면에서 Ctrl+J가 이 안의 입력칸으로 포커스를 옮긴다 */
export const AGENT_PROMPT_ATTR = 'data-agent-prompt';

export function focusAgentPrompt(): boolean {
  const el = document.querySelector<HTMLTextAreaElement>(`[${AGENT_PROMPT_ATTR}] textarea`);
  el?.focus();
  return Boolean(el);
}

/** ⋯ 메뉴: '에이전트가 아는 것' */
export function AgentMenu({ onMemory }: { onMemory: () => void }) {
  return (
    <Menu
      align="end"
      trigger={<IconButton label="에이전트 메뉴" icon={<Ellipsis size={20} aria-hidden="true" />} />}
      items={[{ key: 'memory', label: '에이전트가 아는 것', onSelect: onMemory }]}
    />
  );
}

interface RunViewProps {
  run: Run;
  busy: boolean;
  onRun: (text: string) => void;
  senderOf: SenderOf;
  asOfMs: number;
  /** 있으면(에이전트 화면) 결과물로 여는 결과를 짧은 카드로 보인다 */
  results?: { openRunId: number | null; onOpen: (runId: number) => void };
}

function RunView({ run, busy, onRun, senderOf, asOfMs, results }: RunViewProps) {
  const o = run.outcome;
  const cardId = agentCardId(run.id);
  const link = results ? viewerItemOf(run) : null;
  return (
    <div className={styles.run}>
      <StepLine run={run} onStop={() => agentSession.stop()} />
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
          {o?.type === 'query' && <QueryCard id={cardId} title={o.title} targets={o.targets} notes={o.notes} senderOf={senderOf} />}
          {o?.type === 'summary' && <SummaryCard id={cardId} title={o.title} summary={o.summary} asOfMs={asOfMs} senderOf={senderOf} />}
          {o?.type === 'awaiting' && <AwaitingCard id={cardId} title={o.title} items={o.items} />}
          {o?.type === 'draft' && <DraftCard id={cardId} title={o.title} draft={o.draft} />}
          {o?.type === 'notice' && <NoticeCard id={cardId} title={o.title} hint={o.hint} />}
          {o?.type === 'error' && <NoticeCard title={o.title} hint={o.hint} />}
          {o?.type === 'unsupported' && <UnsupportedCard title={o.title} hint={o.hint} examples={o.examples} busy={busy} onRun={onRun} />}
        </>
      )}
    </div>
  );
}

interface Props {
  /** 감싼 요소 id(패널 · 화면). 탭 포커스를 이 안에서 찾는다 */
  rootId: string;
  view: WorkspaceView;
  onViewChange: (view: WorkspaceView) => void;
  /** 에이전트 화면: 결과물 칸과 잇는다 */
  results?: RunViewProps['results'];
}

export function AgentWorkspace({ rootId, view, onViewChange, results }: Props) {
  // 메일 화면에서 고른 메일(#/mail/:box/:mailId). [빼기]로 뺀 메일은 다른 메일을 고르면 다시 보인다
  const mailMatch = useMatch('/mail/:box/:mailId');
  const routeMailId = mailMatch?.params.mailId ?? null;
  const [removedMailId, setRemovedMailId] = useState<string | null>(null);
  const selectedMailId = routeMailId !== null && routeMailId !== removedMailId ? routeMailId : null;
  const dashboard = useDashboardQuery(); // 고른 메일 제목 · 보낸 사람 표시에 쓰는 원자료(대시보드 · 메일 목록과 같은 캐시)
  const selectedMail = selectedMailId === null ? undefined : dashboard.data?.mails.find((m) => String(m.id) === selectedMailId);
  const senderOf = useMemo(() => senderLookup(dashboard.data), [dashboard.data]);
  const asOfMs = dashboard.data?.asOfMs ?? Date.now();
  const selectedNum = selectedMailId === null ? NaN : Number(selectedMailId);
  const selectedIds = useMemo<MailId[]>(() => (Number.isInteger(selectedNum) ? [selectedNum as MailId] : []), [selectedNum]);

  const state = useAgentSession(selectedIds);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const logRef = useRef<HTMLDivElement>(null);

  // 탭: 고르기 전에는 제안 수로 정한다(제안이 있으면 제안, 없거나 못 받으면 대화).
  // 이미 대화가 있으면(패널에서 이어 온 경우) 대화로 시작한다
  const suggestions = useSuggestionsQuery(3);
  const reminders = useRemindersQuery();
  // 리마인더 API가 있으면 리마인더(앞쪽 건수), 없으면(실제 서버에 아직 없음) 예전 제안 카드로 탭을 채운다
  const useReminders = !reminders.isNotAvailable;
  const reminderTotal = reminders.data ? splitQuiet(visibleItems(reminders.data.items)).active.length : undefined;
  const [chosenTab, setChosenTab] = useState<PanelTab | null>(() => (results && agentSession.getState().entries.length > 0 ? 'chat' : null));
  const landing = useReminders
    ? landingTab(reminderTotal, reminders.isError && !reminders.data)
    : landingTab(suggestions.data?.total, suggestions.isError && !suggestions.data);
  const tab: PanelTab = chosenTab ?? landing ?? 'suggest';
  const [note, setNote] = useState('');
  const memoryRef = useRef<HTMLDivElement>(null);

  // 서버 시계: 제안 응답의 generated_at + 받은 뒤 흐른 시간(모의는 시연 날짜 11/6 기준). 기록 '10분 전' · 나중에 메뉴 시각
  const generatedAt = suggestions.data?.generatedAtMs;
  const receivedAt = suggestions.dataUpdatedAt;
  const serverNow = useCallback(
    () => (generatedAt === undefined ? Date.now() : generatedAt + (Date.now() - receivedAt)),
    [generatedAt, receivedAt],
  );

  const submit = useCallback((text: string) => {
    const ok = agentSession.submit(text);
    if (ok) setChosenTab('chat');
    return ok;
  }, []);
  const runExample = useCallback((text: string) => {
    if (agentSession.submit(text)) {
      setChosenTab('chat');
      inputRef.current?.focus();
    }
  }, []);
  const runCommand = useCallback((text: string, selectedMailIds?: MailId[]) => {
    if (agentSession.submit(text, { selectedMailIds })) setChosenTab('chat');
  }, []);
  const runReminderCommand = useCallback(({ text, ...opts }: CommandRequest) => {
    if (agentSession.submit(text, opts)) setChosenTab('chat');
  }, []);
  const resume = useCallback((previewId: string) => {
    const runId = agentSession.confirmRunFor(previewId);
    if (runId === null) return;
    setChosenTab('chat');
    agentSession.focusConfirm(runId);
  }, []);
  const canResume = useCallback((previewId: string) => agentSession.confirmRunFor(previewId) !== null, []);

  // '에이전트가 아는 것'을 열면 그 제목으로, 닫으면 고른 탭으로 포커스
  const prevView = useRef(view);
  useEffect(() => {
    if (prevView.current === view) return; // 처음 열 때는 SidePanel · 화면이 제목으로 포커스한다
    prevView.current = view;
    if (view === 'memory') memoryRef.current?.querySelector<HTMLElement>('h3')?.focus();
    else document.querySelector<HTMLElement>(`#${CSS.escape(rootId)} [role="tab"][aria-selected="true"]`)?.focus();
  }, [view, rootId]);

  // 새 대화 · 카드가 생기면 맨 아래로(부드러운 스크롤을 쓰지 않는다)
  const lastEntry = state.entries[state.entries.length - 1];
  const scrollKey = `${state.entries.length}:${lastEntry?.kind === 'run' ? `${lastEntry.phase}:${lastEntry.outcome?.type ?? ''}` : ''}`;
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [scrollKey, tab, view]);

  // 세션의 포커스 요청. 다시 열 때 지난 요청으로 제목 포커스를 빼앗지 않게, 연 뒤에 생긴 요청만 따른다
  const handledFocus = useRef(state.focus?.seq ?? 0);
  useEffect(() => {
    const f = state.focus;
    if (!f || f.seq <= handledFocus.current) return;
    handledFocus.current = f.seq;
    if (f.target === 'input') inputRef.current?.focus();
    else document.getElementById(f.target)?.focus();
  }, [state.focus]);

  if (view === 'memory') {
    return (
      <div className={styles.root}>
        <div ref={memoryRef} className={styles.log}>
          <AgentMemoryView onBack={() => onViewChange('tabs')} />
        </div>
      </div>
    );
  }

  const total = (useReminders ? reminderTotal : suggestions.data?.total) ?? 0;
  return (
    <Tabs.Root className={styles.root} value={tab} onValueChange={(v) => setChosenTab(v as PanelTab)}>
      <div className={styles.tabsBar}>
        <Tabs.List className={styles.tabList} aria-label="에이전트 보기">
          <Tabs.Tab value="chat" className={styles.tab}>
            대화
          </Tabs.Tab>
          <Tabs.Tab value="suggest" className={styles.tab} aria-label={total > 0 ? `리마인더 ${total}건` : undefined}>
            리마인더
            <CountBadge count={total} />
          </Tabs.Tab>
          <Tabs.Tab value="history" className={styles.tab}>
            기록
          </Tabs.Tab>
        </Tabs.List>
      </div>
      <Tabs.Panel value="chat" ref={logRef} className={styles.log}>
        <ChatLog state={state} onRun={runExample} senderOf={senderOf} asOfMs={asOfMs} results={results} />
      </Tabs.Panel>
      <Tabs.Panel value="suggest" className={styles.log}>
        {useReminders ? (
          <ReminderPeek busy={state.busy} onCommand={runReminderCommand} now={serverNow} />
        ) : (
          <SuggestionsTab busy={state.busy} onCommand={runCommand} now={serverNow} announce={setNote} />
        )}
      </Tabs.Panel>
      <Tabs.Panel value="history" className={styles.log}>
        <HistoryTab now={serverNow} canResume={canResume} onResume={resume} announce={setNote} />
      </Tabs.Panel>
      <LiveRegion>{state.announcement}</LiveRegion>
      <LiveRegion>{note}</LiveRegion>
      <div className={styles.foot} {...{ [AGENT_PROMPT_ATTR]: '' }}>
        {selectedMailId !== null && (
          <SelectedMailBar
            subject={selectedMail?.subject ?? null}
            onRemove={() => {
              setRemovedMailId(selectedMailId);
              inputRef.current?.focus();
            }}
          />
        )}
        <PromptInput busy={state.busy} onSubmit={submit} onTyping={() => setChosenTab('chat')} inputRef={inputRef} />
      </div>
    </Tabs.Root>
  );
}
