// 에이전트 패널 G (components.md 4.4 · wireframe 13-4 · UX-D8 · D37). 앱 틀(AppLayout)이 <AgentPanel id onClose />로 연다.
// 소개 한 줄 + 예시 명령 칩 + 대화 목록 + 아래 고정 입력 영역(선택한 메일 줄 · 입력).
// - role="status" 영역 하나를 처음부터 두고 단계가 바뀔 때만 글자를 바꾼다(agentSession.announcement)
// - 포커스: 확인 카드가 뜨면 카드로, 결과가 나오면 결과 카드로, 취소 · 중지하면 입력칸으로, 예시 칩을 누르면 입력칸으로
// - 패널은 라우터 Outlet 밖에 있어 useParams가 비므로, 고른 메일은 useMatch로 주소에서 읽는다
// 데이터는 api.runAgentCommand(POST /api/agent/command) 하나다. 모의 · 실제는 클라이언트(api/selectApi.ts)만 바뀐다.
//
// FE-11(PL-16 · D50): 패널 위쪽에 [대화 · 제안 · 기록] 탭. 열면 제안이 있을 때 제안, 없으면 대화로 시작한다.
// 입력은 모든 탭 아래에 그대로 있고, 글을 쓰기 시작하면 대화 탭으로 옮긴다. 제목 줄 ⋯ 메뉴 → '에이전트가 아는 것'(패널 안 화면, ‹ 뒤로).
import { Tabs } from "@base-ui/react/tabs";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMatch } from "react-router";
import { PANEL_WIDTH } from "../../app/panel.tsx";
import { useDashboardQuery, useSuggestionsQuery } from "../../api/queries.ts";
import { CountBadge, Ellipsis, IconButton, LiveRegion, Menu, SidePanel } from "../../ui/index.ts";
import type { MailId } from "../../api/types.ts";
import {
  AwaitingCard,
  ConfirmCard,
  DraftCard,
  NoticeCard,
  QueryCard,
  ResultCard,
  SummaryCard,
  UnsupportedCard,
  type SenderOf,
} from "./AgentCards.tsx";
import { AGENT_NAME } from "./agentBrand.tsx";
import styles from "./AgentPanel.module.css";
import { INTRO_EXAMPLES, senderLookup } from "./agentText.ts";
import {
  agentCardId,
  agentConfirmId,
  agentSession,
  type Run,
} from "./agentSession.ts";
import { ExampleList } from "./ExampleList.tsx";
import { PromptInput } from "./PromptInput.tsx";
import { SelectedMailBar } from "./SelectedMailBar.tsx";
import { StepLine } from "./StepLine.tsx";
import { useAgentSession } from "./useAgentSession.ts";
import { AgentMemoryView } from "./AgentMemoryView.tsx";
import { landingTab } from "./agentPanelPlan.ts";
import { HistoryTab } from "./HistoryTab.tsx";
import { SuggestionsTab } from "./SuggestionsTab.tsx";

type PanelTab = "chat" | "suggest" | "history";

interface Props {
  id: string;
  onClose: () => void;
}

interface RunViewProps {
  run: Run;
  busy: boolean;
  onRun: (text: string) => void;
  senderOf: SenderOf;
  asOfMs: number;
}

function RunView({ run, busy, onRun, senderOf, asOfMs }: RunViewProps) {
  const o = run.outcome;
  const cardId = agentCardId(run.id);
  return (
    <div className={styles.run}>
      <StepLine run={run} onStop={() => agentSession.stop()} />
      {o?.type === "confirm" && (
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
      {o?.type === "result" && (
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
      {o?.type === "query" && (
        <QueryCard
          id={cardId}
          title={o.title}
          targets={o.targets}
          notes={o.notes}
          senderOf={senderOf}
        />
      )}
      {o?.type === "summary" && (
        <SummaryCard
          id={cardId}
          title={o.title}
          summary={o.summary}
          asOfMs={asOfMs}
          senderOf={senderOf}
        />
      )}
      {o?.type === "awaiting" && (
        <AwaitingCard id={cardId} title={o.title} items={o.items} />
      )}
      {o?.type === "draft" && (
        <DraftCard id={cardId} title={o.title} draft={o.draft} />
      )}
      {o?.type === "notice" && (
        <NoticeCard id={cardId} title={o.title} hint={o.hint} />
      )}
      {o?.type === "error" && <NoticeCard title={o.title} hint={o.hint} />}
      {o?.type === "unsupported" && (
        <UnsupportedCard
          title={o.title}
          hint={o.hint}
          examples={o.examples}
          busy={busy}
          onRun={onRun}
        />
      )}
    </div>
  );
}

export function AgentPanel({ id, onClose }: Props) {
  // 메일 화면에서 고른 메일(#/mail/:box/:mailId). [빼기]로 뺀 메일은 다른 메일을 고르면 다시 보인다
  const mailMatch = useMatch("/mail/:box/:mailId");
  const routeMailId = mailMatch?.params.mailId ?? null;
  const [removedMailId, setRemovedMailId] = useState<string | null>(null);
  const selectedMailId =
    routeMailId !== null && routeMailId !== removedMailId ? routeMailId : null;
  const dashboard = useDashboardQuery(); // 고른 메일 제목 · 보낸 사람 표시에 쓰는 원자료(대시보드 · 메일 목록과 같은 캐시)
  const selectedMail =
    selectedMailId === null
      ? undefined
      : dashboard.data?.mails.find((m) => String(m.id) === selectedMailId);
  const senderOf = useMemo(
    () => senderLookup(dashboard.data),
    [dashboard.data],
  );
  const asOfMs = dashboard.data?.asOfMs ?? Date.now();
  const selectedNum = selectedMailId === null ? NaN : Number(selectedMailId);
  const selectedIds = useMemo<MailId[]>(
    () => (Number.isInteger(selectedNum) ? [selectedNum as MailId] : []),
    [selectedNum],
  );

  const state = useAgentSession(selectedIds);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const logRef = useRef<HTMLDivElement>(null);

  // 탭: 고르기 전에는 제안 수로 정한다(제안이 있으면 제안, 없거나 못 받으면 대화)
  const suggestions = useSuggestionsQuery(3);
  const [chosenTab, setChosenTab] = useState<PanelTab | null>(null);
  const landing = landingTab(suggestions.data?.total, suggestions.isError && !suggestions.data);
  const tab: PanelTab = chosenTab ?? landing ?? "suggest";
  const [view, setView] = useState<"tabs" | "memory">("tabs");
  const [note, setNote] = useState("");
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
    if (ok) setChosenTab("chat");
    return ok;
  }, []);
  const runExample = useCallback((text: string) => {
    if (agentSession.submit(text)) {
      setChosenTab("chat");
      inputRef.current?.focus();
    }
  }, []);
  const runCommand = useCallback((text: string, selectedMailIds?: MailId[]) => {
    if (agentSession.submit(text, { selectedMailIds })) setChosenTab("chat");
  }, []);
  const resume = useCallback((previewId: string) => {
    const runId = agentSession.confirmRunFor(previewId);
    if (runId === null) return;
    setChosenTab("chat");
    agentSession.focusConfirm(runId);
  }, []);
  const canResume = useCallback((previewId: string) => agentSession.confirmRunFor(previewId) !== null, []);

  // '에이전트가 아는 것'을 열면 그 제목으로, 닫으면 고른 탭으로 포커스
  const prevView = useRef(view);
  useEffect(() => {
    if (prevView.current === view) return; // 처음 열 때는 SidePanel이 제목으로 포커스한다
    prevView.current = view;
    if (view === "memory") memoryRef.current?.querySelector<HTMLElement>("h3")?.focus();
    else document.querySelector<HTMLElement>(`#${CSS.escape(id)} [role="tab"][aria-selected="true"]`)?.focus();
  }, [view, id]);

  // 새 대화 · 카드가 생기면 맨 아래로(부드러운 스크롤을 쓰지 않는다)
  const lastEntry = state.entries[state.entries.length - 1];
  const scrollKey = `${state.entries.length}:${lastEntry?.kind === "run" ? `${lastEntry.phase}:${lastEntry.outcome?.type ?? ""}` : ""}`;
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [scrollKey, tab, view]);

  // 세션의 포커스 요청. 패널을 다시 열 때 지난 요청으로 제목 포커스를 빼앗지 않게, 연 뒤에 생긴 요청만 따른다
  const handledFocus = useRef(state.focus?.seq ?? 0);
  useEffect(() => {
    const f = state.focus;
    if (!f || f.seq <= handledFocus.current) return;
    handledFocus.current = f.seq;
    if (f.target === "input") inputRef.current?.focus();
    else document.getElementById(f.target)?.focus();
  }, [state.focus]);

  const chatLog = (
    <>
      {/* 소개 · 예시는 대화가 없을 때만. 대화가 시작되면 화면을 대화에 내준다(예시는 '지원하지 않는 요청' 카드에 다시 나온다) */}
      {state.entries.length === 0 && (
        <div className={styles.intro}>
          <p className={styles.introText}>
            말이나 글로 시키면 처리해요. 여러 건을 바꿀 때는 먼저 물어봐요.
          </p>
          <ExampleList
            examples={INTRO_EXAMPLES}
            busy={state.busy}
            onRun={runExample}
            label="예시 명령"
          />
        </div>
      )}
      {state.entries.length > 0 && (
        <ol className={styles.entries} aria-label="대화">
          {state.entries.map((e) =>
            e.kind === "user" ? (
              <li key={e.id} className={styles.bubble}>
                {e.text}
              </li>
            ) : (
              <li key={e.id}>
                <RunView
                  run={e}
                  busy={state.busy}
                  onRun={runExample}
                  senderOf={senderOf}
                  asOfMs={asOfMs}
                />
              </li>
            ),
          )}
        </ol>
      )}
    </>
  );

  const total = suggestions.data?.total ?? 0;
  const menu = (
    <Menu
      align="end"
      trigger={
        <IconButton
          label="에이전트 메뉴"
          icon={<Ellipsis size={20} aria-hidden="true" />}
        />
      }
      items={[
        {
          key: "memory",
          label: "에이전트가 아는 것",
          onSelect: () => setView("memory"),
        },
      ]}
    />
  );

  return (
    <SidePanel
      id={id}
      title={AGENT_NAME}
      width={PANEL_WIDTH.agent}
      onClose={onClose}
      headerExtra={menu}
    >
      {view === "memory" ? (
        <div className={styles.root}>
          <div ref={memoryRef} className={styles.log}>
            <AgentMemoryView onBack={() => setView("tabs")} />
          </div>
        </div>
      ) : (
        <Tabs.Root
          className={styles.root}
          value={tab}
          onValueChange={(v) => setChosenTab(v as PanelTab)}
        >
          <div className={styles.tabsBar}>
            <Tabs.List className={styles.tabList} aria-label="에이전트 보기">
              <Tabs.Tab value="chat" className={styles.tab}>
                대화
              </Tabs.Tab>
              <Tabs.Tab
                value="suggest"
                className={styles.tab}
                aria-label={total > 0 ? `제안 ${total}건` : undefined}
              >
                제안
                <CountBadge count={total} />
              </Tabs.Tab>
              <Tabs.Tab value="history" className={styles.tab}>
                기록
              </Tabs.Tab>
            </Tabs.List>
          </div>
          <Tabs.Panel value="chat" ref={logRef} className={styles.log}>
            {chatLog}
          </Tabs.Panel>
          <Tabs.Panel value="suggest" className={styles.log}>
            <SuggestionsTab
              busy={state.busy}
              onCommand={runCommand}
              now={serverNow}
              announce={setNote}
            />
          </Tabs.Panel>
          <Tabs.Panel value="history" className={styles.log}>
            <HistoryTab
              now={serverNow}
              canResume={canResume}
              onResume={resume}
              announce={setNote}
            />
          </Tabs.Panel>
          <LiveRegion>{state.announcement}</LiveRegion>
          <LiveRegion>{note}</LiveRegion>
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
            <PromptInput
              busy={state.busy}
              onSubmit={submit}
              onTyping={() => setChosenTab("chat")}
              inputRef={inputRef}
            />
          </div>
        </Tabs.Root>
      )}
    </SidePanel>
  );
}
