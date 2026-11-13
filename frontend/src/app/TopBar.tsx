// 상단 바 T0 (components.md 4.1): 로고 자리 · CNE · Catch & End · 메뉴 · 동기화 시각 · 🔔 · ✦ 에이전트 · 사용자
import { Link, NavLink } from 'react-router';
import { AGENT_NAME, AgentIcon } from '../features/agent/agentBrand.tsx';
import { NotificationBell } from '../features/notifications/NotificationBell.tsx';
import { Avatar, Button } from '../ui/index.ts';
import { PANEL_ID, usePanel } from './panel.tsx';
import styles from './TopBar.module.css';

const MENU = [
  { to: '/dashboard', label: '대시보드' },
  { to: '/mail', label: '메일' },
  { to: '/settings', label: '설정' },
] as const;

interface Props {
  /** 설정 화면에서는 에이전트 버튼을 숨긴다 */
  agentAvailable: boolean;
  /** 마지막 동기화 시각(예: "10:42"). 값이 있을 때만 보인다 */
  syncTime?: string;
  /** 사용자 이름. 로그인이 없어 지금은 자리 값 */
  userName?: string;
}

export function TopBar({ agentAvailable, syncTime, userName = '사용자' }: Props) {
  const panel = usePanel();
  const agentOpen = panel.kind === 'agent';

  return (
    <header className={styles.topbar}>
      {/* LG CNS 로고 파일 · 사용 허락을 받은 뒤 교체 */}
      <span className={styles.logoSlot} aria-hidden="true">
        로고 자리
      </span>
      {/* 메뉴와 겹치지 않게 NavLink가 아닌 Link(선택 표시 없음) */}
      <Link to="/dashboard" className={styles.brand}>
        <span className={styles.brandName}>CNE</span>
        <span className={styles.brandSub}>Catch &amp; End</span>
      </Link>
      <span className={styles.grow} />
      <nav className={styles.nav} aria-label="주 메뉴">
        <ul className={styles.navList}>
          {MENU.map((m) => (
            <li key={m.to}>
              <NavLink to={m.to} className={styles.navLink}>
                {m.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      {syncTime && (
        <span className={styles.sync}>
          동기화 <span className={styles.syncTime}>{syncTime}</span>
        </span>
      )}
      <div className={styles.actions}>
        <NotificationBell />
        {agentAvailable && (
          <Button
            variant="primary"
            aria-expanded={agentOpen}
            aria-controls={agentOpen ? PANEL_ID : undefined}
            onClick={() => (agentOpen ? panel.close() : panel.open('agent'))}
          >
            <AgentIcon size={16} />
            <span className={styles.agentText}>{AGENT_NAME}</span>
          </Button>
        )}
        <span className={styles.avatar}>
          <Avatar name={userName} labelled />
        </span>
      </div>
    </header>
  );
}
