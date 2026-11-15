// 상단 바 T0 (components.md 4.1): CNE · Catch & End · 메뉴(대시보드 · 메일 · 캘린더 · 에이전트 · 설정) · 동기화 시각 · 🔔 · ✦ 에이전트 · 사용자
// ✦ 에이전트 버튼은 패널을 열고 닫는다(Ctrl+J · ⌘J와 같음). 설정 · 에이전트 화면에서는 숨긴다
import { Link, NavLink } from 'react-router';
import { dashboardDataMode } from '../api/client.ts';
import { AGENT_NAME, AgentIcon } from '../features/agent/agentBrand.tsx';
import { NotificationBell } from '../features/notifications/NotificationBell.tsx';
import { TOGGLE_AGENT_KEYSHORTCUTS } from '../lib/shortcuts.ts';
import { Avatar, Button } from '../ui/index.ts';
import { PANEL_ID, usePanel } from './panel.tsx';
import styles from './TopBar.module.css';

const MENU = [
  { to: '/dashboard', label: '대시보드' },
  { to: '/mail', label: '메일' },
  { to: '/calendar', label: '캘린더' }, // D56: 메뉴 네 개(+ 에이전트)
  { to: '/agent', label: '에이전트' },
  { to: '/settings', label: '설정' },
] as const;

interface Props {
  /** 설정 · 에이전트 화면에서는 에이전트 버튼을 숨긴다 */
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
      {/* 로고: LG CNS 로고 파일 · 사용 허락을 받으면 브랜드 글자 앞에 넣는다(점선 '로고 자리' 상자는 미완성으로 보여 뺐다) */}
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
      {dashboardDataMode === 'mock' && (
        <span className={styles.dataNote} title="VITE_API_MODE=mock — 서버 대신 시안 데이터를 보여 줍니다">
          모의 데이터
        </span>
      )}
      {syncTime && (
        <span className={styles.sync}>
          동기화 <span className={styles.syncTime}>{syncTime}</span>
        </span>
      )}
      <div className={styles.actions}>
        <NotificationBell />
        {agentAvailable && (
          // 빨강 채움은 화면마다 '확정' 동작 하나에만 쓴다(Primer: 주 버튼은 화면당 하나). 늘 보이는 진입 단추는 테두리 단추 + 빨간 ✦
          <Button
            variant="secondary"
            className={styles.agent}
            data-open={agentOpen ? '' : undefined}
            aria-expanded={agentOpen}
            aria-controls={agentOpen ? PANEL_ID : undefined}
            aria-keyshortcuts={TOGGLE_AGENT_KEYSHORTCUTS}
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
