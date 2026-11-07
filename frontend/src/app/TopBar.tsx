import type { Ref } from 'react';
import { NotificationCenter } from '../features/notifications/NotificationCenter.tsx';

interface Props {
  agentOpen: boolean;
  onToggleAgent: () => void;
  agentButtonRef: Ref<HTMLButtonElement>;
}

// 주 메뉴는 왼쪽 사이드바(Sidebar.tsx)로 옮겼다. 상단 바에는 앱 이름과 알림 센터 진입점만 둔다.
export function TopBar({ agentOpen, onToggleAgent, agentButtonRef }: Props) {
  return (
    <header className="topbar">
      <span className="brand">업무 리마인더</span>
      <span className="topbar-spacer" />
      <div className="topbar-actions">
        <NotificationCenter />
        <button
          ref={agentButtonRef}
          type="button"
          className="btn"
          aria-expanded={agentOpen}
          aria-controls="agent-panel"
          onClick={onToggleAgent}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M12 2l1.8 5.2L19 9l-5.2 1.8L12 16l-1.8-5.2L5 9l5.2-1.8zM19 14l.9 2.1L22 17l-2.1.9L19 20l-.9-2.1L16 17l2.1-.9z" />
          </svg>
          <span className="btn-label-wide">AI 에이전트</span>
          <span className="sr-only">{agentOpen ? ' 패널 닫기' : ' 패널 열기'}</span>
        </button>
      </div>
    </header>
  );
}
