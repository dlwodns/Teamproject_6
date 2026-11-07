import { useEffect, useRef, useState } from 'react';
import { AgentPanel } from '../features/agent/AgentPanel.tsx';
import { DashboardPage } from '../pages/dashboard/DashboardPage.tsx';
import { MailPage } from '../pages/mail/MailPage.tsx';
import { SettingsPage } from '../pages/settings/SettingsPage.tsx';
import { useRoute } from './router.ts';
import { Sidebar } from './Sidebar.tsx';
import { TopBar } from './TopBar.tsx';

// 이 폭 이하에서는 사이드바를 접은 채 시작하고, 펼치면 본문 위에 겹쳐 보인다(global.css 같은 값)
const NARROW_QUERY = '(max-width: 720px)';
const isNarrow = () => window.matchMedia(NARROW_QUERY).matches;

export function App() {
  const route = useRoute();
  const [agentOpen, setAgentOpen] = useState(false);
  const [agentDraft, setAgentDraft] = useState('');
  const agentButtonRef = useRef<HTMLButtonElement>(null);
  const prevRoute = useRef(route);
  const [sidebarExpanded, setSidebarExpanded] = useState(() => !isNarrow());

  // 메뉴로 화면을 옮겼을 때만 화면 제목으로 포커스를 옮겨 화면 읽기 프로그램이 바뀐 화면을 알 수 있게 한다.
  // 첫 로드에는 옮기지 않는다. 직전 경로와 비교하므로 StrictMode가 effect를 두 번 돌려도 첫 로드에 포커스가 가지 않는다.
  useEffect(() => {
    if (prevRoute.current === route) return;
    prevRoute.current = route;
    if (isNarrow()) setSidebarExpanded(false); // 좁은 화면에서 겹친 메뉴가 바뀐 화면을 가리지 않게
    document.getElementById('page-title')?.focus();
  }, [route]);

  const closeAgent = () => {
    setAgentOpen(false);
    agentButtonRef.current?.focus();
  };

  useEffect(() => {
    if (!agentOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeAgent();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [agentOpen]);

  return (
    <div className="app" data-agent-open={agentOpen} data-sidebar-expanded={sidebarExpanded}>
      <a className="skip-link" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById('page-title')?.focus(); }}>
        본문으로 건너뛰기
      </a>
      <Sidebar route={route} expanded={sidebarExpanded} onToggle={() => setSidebarExpanded((v) => !v)} />
      <div className="app-main">
        <TopBar agentOpen={agentOpen} onToggleAgent={() => (agentOpen ? closeAgent() : setAgentOpen(true))} agentButtonRef={agentButtonRef} />
        <main id="main" className="page">
          {route === 'dashboard' && <DashboardPage />}
          {route === 'mail' && <MailPage />}
          {route === 'settings' && <SettingsPage />}
        </main>
      </div>
      {agentOpen && <AgentPanel draft={agentDraft} onDraftChange={setAgentDraft} onClose={closeAgent} />}
    </div>
  );
}
