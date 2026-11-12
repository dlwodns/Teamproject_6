import { useEffect, useRef, useState } from 'react';
import { AgentLauncher } from '../features/agent/AgentLauncher.tsx';
import { AgentPanel } from '../features/agent/AgentPanel.tsx';
import { ToastProvider } from '../features/toast/ToastProvider.tsx';
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
  const agentButtonRef = useRef<HTMLButtonElement>(null);
  const returnFocusToLauncher = useRef(false);
  const prevRoute = useRef(route);
  const [sidebarExpanded, setSidebarExpanded] = useState(() => !isNarrow());

  // 메뉴로 화면을 옮겼을 때만 화면 제목으로 포커스를 옮겨 화면 읽기 프로그램이 바뀐 화면을 알 수 있게 한다.
  // 첫 로드에는 옮기지 않는다. 직전 경로와 비교하므로 StrictMode가 effect를 두 번 돌려도 첫 로드에 포커스가 가지 않는다.
  useEffect(() => {
    if (prevRoute.current === route) return;
    prevRoute.current = route;
    if (isNarrow()) setSidebarExpanded(false); // 좁은 화면에서 겹친 메뉴가 바뀐 화면을 가리지 않게
    // 설정 화면에서는 에이전트 버튼 · 패널을 모두 숨긴다. 사라진 버튼으로 포커스를 보내지 않고 화면 제목으로 보낸다
    if (route === 'settings') {
      returnFocusToLauncher.current = false;
      setAgentOpen(false);
    }
    document.getElementById('page-title')?.focus();
  }, [route]);

  // 에이전트는 설정 화면을 뺀 모든 화면에서 부를 수 있다(FE-D13 [제안])
  const agentAvailable = route !== 'settings';
  const panelOpen = agentOpen && agentAvailable;

  // 닫으면 원형 버튼으로 포커스를 돌려준다. 버튼은 패널이 닫힌 뒤에 다시 그려지므로 그린 다음 옮긴다
  const closeAgent = () => {
    returnFocusToLauncher.current = true;
    setAgentOpen(false);
  };

  useEffect(() => {
    if (agentOpen || !returnFocusToLauncher.current) return;
    returnFocusToLauncher.current = false;
    agentButtonRef.current?.focus();
  }, [agentOpen]);

  useEffect(() => {
    if (!panelOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeAgent();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [panelOpen]);

  return (
    <ToastProvider>
      <div className="app" data-agent-open={panelOpen} data-sidebar-expanded={sidebarExpanded}>
        <a className="skip-link" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById('page-title')?.focus(); }}>
          본문으로 건너뛰기
        </a>
        <Sidebar route={route} expanded={sidebarExpanded} onToggle={() => setSidebarExpanded((v) => !v)} />
        <div className="app-main">
          <TopBar />
          <main id="main" className="page">
            {route === 'dashboard' && <DashboardPage />}
            {route === 'mail' && <MailPage />}
            {route === 'settings' && <SettingsPage />}
          </main>
        </div>
        {panelOpen && <AgentPanel onClose={closeAgent} />}
        {agentAvailable && !panelOpen && <AgentLauncher onOpen={() => setAgentOpen(true)} buttonRef={agentButtonRef} />}
      </div>
    </ToastProvider>
  );
}
