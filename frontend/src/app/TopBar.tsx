import { NotificationCenter } from '../features/notifications/NotificationCenter.tsx';

// 주 메뉴는 왼쪽 사이드바(Sidebar.tsx), 에이전트는 오른쪽 아래 원형 버튼(AgentLauncher.tsx)으로 옮겼다.
// 상단 바에는 앱 이름과 알림 센터 진입점만 둔다.
export function TopBar() {
  return (
    <header className="topbar">
      <span className="brand">업무 리마인더</span>
      <span className="topbar-spacer" />
      <div className="topbar-actions">
        <NotificationCenter />
      </div>
    </header>
  );
}
