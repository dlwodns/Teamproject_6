import { useEffect, useRef, useState } from 'react';
import { AgentPanel } from '../features/agent/AgentPanel.tsx';
import { DashboardPage } from '../pages/dashboard/DashboardPage.tsx';
import { MailPage } from '../pages/mail/MailPage.tsx';
import { SettingsPage } from '../pages/settings/SettingsPage.tsx';
import { useRoute } from './router.ts';
import { TopBar } from './TopBar.tsx';

export function App() {
  const route = useRoute();
  const [agentOpen, setAgentOpen] = useState(false);
  const [agentDraft, setAgentDraft] = useState('');
  const agentButtonRef = useRef<HTMLButtonElement>(null);
  const prevRoute = useRef(route);

  // 메뉴로 화면을 옮겼을 때만 화면 제목으로 포커스를 옮겨 화면 읽기 프로그램이 바뀐 화면을 알 수 있게 한다.
  // 첫 로드에는 옮기지 않는다. 직전 경로와 비교하므로 StrictMode가 effect를 두 번 돌려도 첫 로드에 포커스가 가지 않는다.
  useEffect(() => {
    if (prevRoute.current === route) return;
    prevRoute.current = route;
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
    <div className="app" data-agent-open={agentOpen}>
      <a className="skip-link" href="#main" onClick={(e) => { e.preventDefault(); document.getElementById('page-title')?.focus(); }}>
        본문으로 건너뛰기
      </a>
      <div className="app-main">
        <TopBar route={route} agentOpen={agentOpen} onToggleAgent={() => (agentOpen ? closeAgent() : setAgentOpen(true))} agentButtonRef={agentButtonRef} />
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
