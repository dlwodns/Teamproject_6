// 앱 틀 (components.md 4.1): 상단 바 · 본문(Outlet) · 패널 자리.
// - 메뉴로 화면(대시보드 · 메일 · 설정)을 옮기면 화면 제목(#page-title)으로 포커스. 첫 로드와 같은 화면 안 이동(메일 고르기)에는 옮기지 않는다
// - 설정 화면에서는 ✦ 에이전트 버튼 · 패널을 숨긴다. 에이전트 화면(#/agent)에서도 떠 있는 패널은 열지 않는다(FE-15)
// - 메일 화면에서 Ctrl+B(⌘B)로 메일함을 열고 닫는다(입력 중 · 한글 조합 중에는 무시)
// - 어느 화면에서나 Ctrl+J(⌘J)로 에이전트 패널을 열고 닫는다. 에이전트 화면에서는 입력칸으로 포커스(FE-15 · FE-D21)
// - 에이전트 작업이 끝나면 보고 있지 않을 때만 알린다(useAgentCompletion, FE-D22)
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { Outlet, useLocation } from 'react-router';
import { AgentPanel } from '../features/agent/AgentPanel.tsx';
import { focusAgentPrompt } from '../features/agent/AgentWorkspace.tsx';
import { useAgentCompletion } from '../features/agent/useAgentCompletion.ts';
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
  if (panel.kind === 'agent') return <AgentPanel id={PANEL_ID} onClose={panel.close} />;
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
  const { kind: panelKind, close: closePanel, open: openPanel } = usePanel();
  const [mailboxOpen, setMailboxOpen] = useState(true);
  const prevSection = useRef(section);
  const panelKindRef = useRef(panelKind); // 화면이 바뀐 순간의 패널 종류만 본다
  panelKindRef.current = panelKind;

  // 화면이 바뀔 때만(첫 로드 제외): 설정이면 패널을 닫고, 더보기(대시보드 칸 목록)는 그 화면 것이라 닫는다. 그리고 화면 제목으로 포커스.
  // 직전 화면과 비교하므로 StrictMode가 effect를 두 번 돌려도 첫 로드에 포커스가 가지 않는다
  useEffect(() => {
    if (prevSection.current === section) return;
    prevSection.current = section;
    if (section === 'settings' || section === 'agent' || panelKindRef.current === 'more') closePanel();
    focusPageTitle();
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

  // Ctrl+J(⌘J): 에이전트 패널 열고 닫기. 크롬 다운로드 창 단축키라 처리할 때만 막는다
  const agentWhere = section === 'settings' ? 'hidden' : section === 'agent' ? 'agent-page' : 'other';
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const action = agentShortcutAction(e, agentWhere);
      if (action === null) return;
      e.preventDefault();
      if (action === 'focus-input') focusAgentPrompt();
      else if (panelKindRef.current === 'agent') closePanel();
      else openPanel('agent');
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [agentWhere, closePanel, openPanel]);

  const outlet = useMemo<AppOutletContext>(
    () => ({ mailboxOpen, setMailboxOpen, toggleMailbox }),
    [mailboxOpen, toggleMailbox],
  );

  const agentAvailable = section !== 'settings' && section !== 'agent';
  const shownPanel = panelKind === 'agent' && !agentAvailable ? null : panelKind;
  useAgentCompletion({ panelOpen: shownPanel === 'agent', onAgentPage: section === 'agent' });

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
      <TopBar agentAvailable={agentAvailable} />
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
