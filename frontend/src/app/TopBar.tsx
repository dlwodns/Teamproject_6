import type { Ref } from 'react';
import { NotificationCenter } from '../features/notifications/NotificationCenter.tsx';
import { ROUTES, type RouteKey } from './router.ts';

interface Props {
  route: RouteKey;
  agentOpen: boolean;
  onToggleAgent: () => void;
  agentButtonRef: Ref<HTMLButtonElement>;
}

export function TopBar({ route, agentOpen, onToggleAgent, agentButtonRef }: Props) {
  return (
    <header className="topbar">
      <span className="brand">업무 리마인더</span>
      <span className="topbar-spacer" />
      <nav aria-label="주 메뉴">
        <ul className="nav">
          {ROUTES.map((r) => (
            <li key={r.key}>
              <a className="nav-link" href={r.path} aria-current={r.key === route ? 'page' : undefined}>
                <span className="nav-check" aria-hidden="true">
                  ✓
                </span>
                {r.label}
              </a>
            </li>
          ))}
        </ul>
      </nav>
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
