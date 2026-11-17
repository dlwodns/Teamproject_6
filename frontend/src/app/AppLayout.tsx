// 앱 틀 (components.md 4.1): 상단 바 · 본문(Outlet) · 패널 자리.
// - 메뉴로 화면(대시보드 · 메일 · 설정)을 옮기면 화면 제목(#page-title)으로 포커스. 첫 로드와 같은 화면 안 이동(메일 고르기)에는 옮기지 않는다
// - 메일 화면에서 Ctrl+B(⌘B)로 메일함을 열고 닫는다(입력 중 · 한글 조합 중에는 무시)
// - 어느 화면에서나 Ctrl+J(⌘J)로 캐치봇 화면에 가서 입력칸으로 포커스(FE-15 · FE-D21). 11-15 캐치봇 패널은 없앴다(reminders.md 12.8)
// - 에이전트 작업이 끝나면 보고 있지 않을 때만 알린다(useAgentCompletion, FE-D22)
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router';
import { focusAgentPrompt } from '../features/agent/ChatLog.tsx';
import { AGENT_PATH, useAgentCompletion } from '../features/agent/useAgentCompletion.ts';
import { useAgentSessionBase } from '../features/agent/useAgentSession.ts';
import { useSettingsQuery } from '../api/queries.ts';
import { REDUCE_MOTION_ATTR } from '../lib/motion.ts';
import { agentShortcutAction, isToggleMailboxShortcut, shouldIgnoreShortcut } from '../lib/shortcuts.ts';
import { SidePanel } from '../ui/index.ts';
import styles from './AppLayout.module.css';
import type { AppOutletContext } from './outlet.ts';
import { PANEL_ID, PANEL_WIDTH, PanelProvider, usePanel } from './panel.tsx';
import { TopBar } from './TopBar.tsx';

type Section = 'dashboard' | 'mail' | 'agent' | 'settings';

function sectionOf(pathname: string): Section {
  const first = pathname.split('/')[1];
  return first === 'mail' || first === 'agent' || first === 'settings' ? first : 'dashboard';
}

function focusPageTitle() {
  document.getElementById('page-title')?.focus();
}

function PanelHost() {
  const panel = usePanel();
  if (panel.kind === 'more' && panel.payload) {
    return (
      <SidePanel id={PANEL_ID} title={panel.payload.title} width={PANEL_WIDTH.more} onClose={panel.close}>
        {panel.payload.content}
      </SidePanel>
    );
  }
  return null;
}

function Shell() {
  const { pathname } = useLocation();
  const section = sectionOf(pathname);
  const { kind: panelKind, close: closePanel } = usePanel();
  const navigate = useNavigate();
  const [mailboxOpen, setMailboxOpen] = useState(true);
  const prevSection = useRef(section);
  const panelKindRef = useRef(panelKind); // 화면이 바뀐 순간의 패널 종류만 본다
  panelKindRef.current = panelKind;
  const focusPromptNext = useRef(false); // Ctrl+J로 캐치봇 화면에 왔으면 제목 대신 입력칸으로

  // 설정의 '움직임 줄이기'를 앱 전체에 건다(global.css · lib/motion.ts가 이 표시를 본다)
  const reduceMotion = useSettingsQuery().data?.reduceMotion === true;
  useEffect(() => {
    document.documentElement.toggleAttribute(REDUCE_MOTION_ATTR, reduceMotion);
  }, [reduceMotion]);

  // 화면이 바뀔 때만(첫 로드 제외): 더보기(대시보드 칸 목록)는 그 화면 것이라 닫는다. 그리고 화면 제목(Ctrl+J로 왔으면 캐치봇 입력칸)으로 포커스.
  // 직전 화면과 비교하므로 StrictMode가 effect를 두 번 돌려도 첫 로드에 포커스가 가지 않는다
  useEffect(() => {
    if (prevSection.current === section) return;
    prevSection.current = section;
    if (panelKindRef.current === 'more') closePanel();
    const wantPrompt = focusPromptNext.current;
    focusPromptNext.current = false;
    if (!(wantPrompt && focusAgentPrompt())) focusPageTitle();
  }, [section, closePanel]);

  const toggleMailbox = useCallback(() => setMailboxOpen((v) => !v), []);

  useEffect(() => {
    if (section !== 'mail') return;
    const onKey = (e: KeyboardEvent) => {
      if (!isToggleMailboxShortcut(e) || shouldIgnoreShortcut(e)) return;
      e.preventDefault(); // 브라우저 책갈피 단축키 대신
      toggleMailbox();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [section, toggleMailbox]);

  // Ctrl+J(⌘J): 캐치봇 화면으로 가서 입력칸에 포커스. 크롬 다운로드 창 단축키라 처리할 때만 막는다
  const agentWhere = section === 'agent' ? 'agent-page' : 'other';
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const action = agentShortcutAction(e, agentWhere);
      if (action === null) return;
      e.preventDefault();
      if (action === 'focus-input') focusAgentPrompt();
      else {
        focusPromptNext.current = true;
        void navigate(AGENT_PATH);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [agentWhere, navigate]);

  const outlet = useMemo<AppOutletContext>(
    () => ({ mailboxOpen, setMailboxOpen, toggleMailbox }),
    [mailboxOpen, toggleMailbox],
  );

  const shownPanel = panelKind;
  // 캐치봇 화면에서는 화면이 직접 알린다(대화 메뉴는 카드, 다른 메뉴는 결과 한 줄 토스트 — pages/agent/AgentPage.tsx)
  useAgentCompletion({ onAgentPage: section === 'agent' });
  useAgentSessionBase(); // 🔔 팝업처럼 캐치봇 화면 밖에서도 명령을 보낼 수 있게(FE-16)

  return (
    <div
      className={styles.layout}
      data-panel={shownPanel ?? undefined}
      style={shownPanel ? ({ '--panel-push': PANEL_WIDTH[shownPanel] } as CSSProperties) : undefined}
    >
      <a
        className={styles.skipLink}
        href="#page-title"
        onClick={(e) => {
          e.preventDefault(); // 해시 라우터라 주소의 # 뒤를 바꾸면 화면이 바뀐다
          focusPageTitle();
        }}
      >
        본문으로 건너뛰기
      </a>
      <TopBar />
      <main id="main" className={styles.main}>
        <div className={styles.content}>
          <Outlet context={outlet} />
        </div>
      </main>
      {shownPanel && <PanelHost />}
    </div>
  );
}

export function AppLayout() {
  return (
    <PanelProvider>
      <Shell />
    </PanelProvider>
  );
}
