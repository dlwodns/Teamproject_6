// 에이전트 화면 #/agent (FE-16 · UX-D19 · 명세 docs/10_planning/reminders.md 5절). FE-15의 두 칸 화면을 세 칸으로 다시 짰다.
//   왼쪽 메뉴(220px) · 가운데 목록 · 오른쪽 상세 + 모든 메뉴 아래 같은 입력 한 줄
//   메뉴: 리마인더(묶음 6개 + 전체) · 브리핑 · 회고 · 초안 · 대화(FE-15 대화 · 결과물 그대로) · 기록 · 에이전트가 아는 것(FE-11 부품)
// - 에이전트의 역할을 '먼저 알려 주는 리마인더'로 좁고 분명하게 보이려고 첫 메뉴를 리마인더로 둔다. 대화는 리마인더를 처리하는 한 방법이다
// - 제목 줄 아래 "메일을 보내거나 지우는 일은 직접 하지 않아요"(명세 5.1절): 대화창이 있으면 다 해 줄 것이라 기대하기 쉬워서 먼저 밝힌다
// - 리마인더를 고르면 입력 위에 '고른 리마인더' 칩이 붙고, 그 상태로 말하면 그 업무를 대상으로 명령이 간다(task_ids · reminder_key).
//   결과는 대화에 쌓이고, 대화 메뉴가 아니면 결과 한 줄 토스트(+ 실행 취소)만 띄운다(pageRunToast)
// - 메뉴를 옮기면 가운데 칸 제목으로 포커스. 뒤로 가기가 메뉴 이동을 되돌린다(주소에 쌓임)
// - 실제 서버에 리마인더 API(BE-12)가 없으면 리마인더 · 브리핑 메뉴를 숨기고 대화로 시작한다(없는 기능을 0건으로 보이지 않는다)
// - 1024px 미만: 왼쪽 메뉴는 위쪽 고르기 상자, 목록과 상세는 한 칸씩(상세에 ‹ 뒤로)
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Navigate, useNavigate, useParams } from 'react-router';
import { useDashboardQuery, useHistoryQuery } from '../../api/queries.ts';
import { useRemindersQuery } from '../../api/reminders.ts';
import { AgentMemoryView } from '../../features/agent/AgentMemoryView.tsx';
import { AGENT_NAME } from '../../features/agent/agentBrand.tsx';
import { menuPath, parseAgentPath, reminderPath, type AgentRoute } from '../../features/agent/agentRoutes.ts';
import { agentSession, type Entry, type Run } from '../../features/agent/agentSession.ts';
import { senderLookup } from '../../features/agent/agentText.ts';
import { agentViewer } from '../../features/agent/agentViewer.ts';
import { AGENT_PROMPT_ATTR, focusAgentPrompt } from '../../features/agent/AgentWorkspace.tsx';
import { HistoryTab } from '../../features/agent/HistoryTab.tsx';
import { pageRunToast } from '../../features/agent/pageRunToast.ts';
import { PromptInput } from '../../features/agent/PromptInput.tsx';
import { useAgentSession } from '../../features/agent/useAgentSession.ts';
import { kstDate } from '../../features/reminders/briefingModel.ts';
import { groupCounts, hasOverdue, visibleItems } from '../../features/reminders/reminderModel.ts';
import { useReminderRunner, type CommandRequest } from '../../features/reminders/useReminderRunner.ts';
import { IconButton, LiveRegion, useToast, X } from '../../ui/index.ts';
import { AgentMenuSelect, AgentNav } from './AgentNav.tsx';
import styles from './AgentPage.module.css';
import { BriefingView } from './BriefingView.tsx';
import { ChatView } from './ChatView.tsx';
import { DraftsView } from './DraftsView.tsx';
import { RemindersView } from './RemindersView.tsx';

const NO_MAILS: never[] = [];

/** 대화에서 초안 결과만, 최근 것부터 */
function draftRuns(entries: readonly Entry[]): Run[] {
  return entries.filter((e): e is Run => e.kind === 'run' && e.phase === 'done' && e.outcome?.type === 'draft').reverse();
}

export function AgentPage() {
  const params = useParams();
  const parsed = parseAgentPath(params['*'] ?? '');
  const reminders = useRemindersQuery();
  const remindersAvailable = !reminders.isNotAvailable;

  if (!parsed) return <Navigate to={remindersAvailable ? reminderPath() : menuPath('chat')} replace />;
  if (!remindersAvailable && (parsed.menu === 'reminders' || parsed.menu === 'briefing')) return <Navigate to={menuPath('chat')} replace />;
  return <AgentScreen route={parsed} reminders={reminders} remindersAvailable={remindersAvailable} />;
}

interface ScreenProps {
  route: AgentRoute;
  reminders: ReturnType<typeof useRemindersQuery>;
  remindersAvailable: boolean;
}

function AgentScreen({ route, reminders, remindersAvailable }: ScreenProps) {
  const navigate = useNavigate();
  const toast = useToast();
  const state = useAgentSession(NO_MAILS);
  const dashboard = useDashboardQuery();
  const source = dashboard.data;
  const senderOf = useMemo(() => senderLookup(source), [source]);
  const asOfMs = reminders.data?.asOfMs ?? source?.asOfMs ?? Date.now();
  const history = useHistoryQuery(7);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const items = useMemo(() => (reminders.data ? visibleItems(reminders.data.items) : []), [reminders.data]);
  const counts = remindersAvailable ? groupCounts(items) : null;
  const drafts = useMemo(() => draftRuns(state.entries), [state.entries]);

  // ── 토스트를 아래 입력 위로 올린다(오른쪽 아래 토스트가 보내기 버튼을 가리지 않게) ──
  const footRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const foot = footRef.current;
    if (!foot) return;
    const root = document.documentElement;
    const lift = () => root.style.setProperty('--toast-lift', `${Math.max(0, Math.round(window.innerHeight - foot.getBoundingClientRect().top))}px`);
    lift();
    const ro = new ResizeObserver(lift);
    ro.observe(foot);
    window.addEventListener('resize', lift);
    return () => {
      ro.disconnect();
      window.removeEventListener('resize', lift);
      root.style.removeProperty('--toast-lift');
    };
  }, []);

  // ── 고른 리마인더 → 입력 위 칩 ──
  // 리마인더 메뉴 안에서는 칩이 오른쪽 상세와 늘 같다(고른 항목이 없으면 칩도 없다).
  // 다른 메뉴(대화 등)로 옮기면 마지막에 고른 항목을 그대로 들고 간다. ✕로 빼면 다른 항목을 고를 때까지 빠져 있다.
  const onReminders = route.menu === 'reminders';
  const selectedKey = onReminders ? route.key : null;
  const [contextKey, setContextKey] = useState<string | null>(selectedKey);
  useEffect(() => {
    if (onReminders) setContextKey(selectedKey);
  }, [onReminders, selectedKey]);
  const contextItem = contextKey === null ? null : (items.find((i) => i.key === contextKey) ?? null);

  // ── 명령 보내기: 아래 입력 · 리마인더 버튼(초안 · 그날 업무)이 같은 길을 탄다 ──
  const watched = useRef(new Set<number>());
  const menuRef = useRef(route.menu);
  menuRef.current = route.menu;
  const send = useCallback((req: CommandRequest): boolean => {
    const { text, ...opts } = req;
    const ok = agentSession.submit(text, { selectedMailIds: [], ...opts });
    if (ok) {
      const last = agentSession.getState().entries.at(-1);
      if (last?.kind === 'run' && menuRef.current !== 'chat') watched.current.add(last.id);
    }
    return ok;
  }, []);
  const runner = useReminderRunner(send);

  const submit = useCallback(
    (text: string) => {
      const it = contextItem;
      return send(
        it
          ? { text, selectedMailIds: it.mailId === null ? [] : [it.mailId], ...(it.taskIds.length ? { taskIds: it.taskIds } : {}), reminderKey: it.key }
          : { text },
      );
    },
    [contextItem, send],
  );

  // 대화 메뉴가 아닌 곳에서 보낸 명령: 끝나면(또는 확인을 기다리면) 결과 한 줄 토스트
  useEffect(
    () =>
      agentSession.subscribe(() => {
        for (const e of agentSession.getState().entries) {
          if (e.kind !== 'run' || !watched.current.has(e.id)) continue;
          const t = pageRunToast(e);
          if (!t && e.phase === 'running') continue;
          watched.current.delete(e.id);
          if (!t || menuRef.current === 'chat') continue;
          const id = `agent-page-run-${e.id}`;
          const onAction = () => {
            toast.close(id);
            if (t.action === 'undo') {
              void agentSession.undoResult(e.id).then(() => toast.show({ kind: 'info', title: agentSession.getState().announcement || '되돌렸어요' }));
              return;
            }
            agentViewer.open(e.id);
            void navigate(menuPath(t.action === 'open_draft' ? 'drafts' : 'chat'));
            if (t.action === 'open_confirm') agentSession.focusConfirm(e.id);
          };
          toast.show({ id, kind: t.kind, title: t.title, ...(t.action && t.actionLabel ? { actionLabel: t.actionLabel, onAction } : {}) });
        }
      }),
    [toast, navigate],
  );

  // ── 메뉴를 옮기면 가운데 칸 제목으로 포커스(첫 로드 제외 — 그때는 앱 틀이 화면 제목으로) ──
  const menuKey = route.menu === 'reminders' ? `reminders:${route.group}` : route.menu;
  const prevMenu = useRef(menuKey);
  useEffect(() => {
    if (prevMenu.current === menuKey) return;
    prevMenu.current = menuKey;
    document.querySelector<HTMLElement>('[data-agent-heading]')?.focus();
  }, [menuKey]);

  const [note, setNote] = useState('');
  const serverNow = useCallback(() => asOfMs, [asOfMs]);

  let body: ReactNode;
  switch (route.menu) {
    case 'reminders':
      body = (
        <RemindersView
          group={route.group}
          selectedKey={route.key}
          data={reminders.data}
          loading={reminders.isPending}
          error={reminders.isError && !reminders.data}
          onRetry={() => void reminders.refetch()}
          runner={runner}
          source={source}
          busy={state.busy}
        />
      );
      break;
    case 'briefing':
      body = <BriefingView today={kstDate(asOfMs)} nowMs={asOfMs} source={source} reminders={items} />;
      break;
    case 'drafts':
      body = <DraftsView drafts={drafts} senderOf={senderOf} asOfMs={asOfMs} />;
      break;
    case 'chat':
      body = <ChatView state={state} senderOf={senderOf} asOfMs={asOfMs} />;
      break;
    case 'history':
      body = (
        <WideColumn title="기록" count={history.data ? history.data.items.length : null}>
          <HistoryTab
            now={serverNow}
            canResume={(id) => agentSession.confirmRunFor(id) !== null}
            onResume={(previewId) => {
              const runId = agentSession.confirmRunFor(previewId);
              if (runId === null) return;
              void navigate(menuPath('chat'));
              agentSession.focusConfirm(runId);
            }}
            announce={setNote}
          />
        </WideColumn>
      );
      break;
    case 'memory':
      body = (
        <WideColumn title="에이전트가 아는 것" count={null}>
          <AgentMemoryView hideTitle />
        </WideColumn>
      );
      break;
  }

  return (
    <div className={styles.page}>
      <header className={styles.head}>
        <h1 id="page-title" className={styles.title} tabIndex={-1}>
          {AGENT_NAME}
        </h1>
        <p className={styles.limit}>메일을 보내거나 지우는 일은 직접 하지 않아요. 보내기는 언제나 직접 눌러 주세요.</p>
      </header>
      <div className={styles.body}>
        <AgentNav route={route} counts={counts} dueAlert={hasOverdue(items)} drafts={drafts.length} />
        <AgentMenuSelect route={route} counts={counts} dueAlert={false} drafts={drafts.length} onGo={(p) => void navigate(p)} />
        <div className={styles.main}>{body}</div>
      </div>
      <div ref={footRef} className={styles.foot} {...{ [AGENT_PROMPT_ATTR]: '' }}>
        {contextItem && (
          <div className={styles.context}>
            <span className={styles.contextChip}>
              <span className={styles.contextLabel}>고른 리마인더</span>
              <span className={styles.contextTitle}>{contextItem.title}</span>
              <IconButton
                className={styles.contextX}
                label="고른 리마인더 빼기"
                icon={<X size={16} aria-hidden="true" />}
                onClick={() => {
                  setContextKey(null);
                  focusAgentPrompt();
                }}
              />
            </span>
          </div>
        )}
        <PromptInput
          busy={state.busy}
          onSubmit={submit}
          inputRef={inputRef}
          placeholder={contextItem ? '이 리마인더를 어떻게 할까요? 예: 금요일로 미뤄 · 이거 완료 · 회신 초안 써 줘' : '에이전트에게 말하기…'}
        />
      </div>
      <LiveRegion>{state.announcement}</LiveRegion>
      <LiveRegion>{note}</LiveRegion>
    </div>
  );
}

function WideColumn({ title, count, children }: { title: string; count: number | null; children: ReactNode }) {
  return (
    <section className={styles.wide} aria-labelledby="agent-wide-title">
      <div className={styles.colHead}>
        <h2 id="agent-wide-title" className={styles.colTitle} tabIndex={-1} data-agent-heading="">
          {title}
        </h2>
        {count !== null && count > 0 && <span className={styles.colCount}>{count}건</span>}
      </div>
      <div className={styles.scroll}>
        <div className={styles.reading}>{children}</div>
      </div>
    </section>
  );
}
