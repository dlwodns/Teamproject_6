// 상단 바 T0 (components.md 4.1): CNE · Catch & End · 메뉴(대시보드 · 캐치봇 · 캘린더 · 메일 · 설정) · 동기화 시각 · 🔔 · 사용자
// 11-15: 오른쪽 위 ✦ 캐치봇 버튼과 패널을 없앴다. 캐치봇은 메뉴 화면 하나다(Ctrl+J · ⌘J도 그 화면으로, reminders.md 12.8)
import { Link, NavLink } from 'react-router';
import { dashboardDataMode } from '../api/client.ts';
import { NotificationBell } from '../features/notifications/NotificationBell.tsx';
import { TOGGLE_AGENT_KEYSHORTCUTS } from '../lib/shortcuts.ts';
import { Avatar } from '../ui/index.ts';
import styles from './TopBar.module.css';

const MENU = [
  // 11-15 순서: 대시보드 · 캐치봇 · 캘린더 · 메일 · 설정
  { to: '/dashboard', label: '대시보드' },
  { to: '/agent', label: '캐치봇' },
  { to: '/calendar', label: '캘린더' },
  { to: '/mail', label: '메일' },
  { to: '/settings', label: '설정' },
] as const;

interface Props {
  /** 마지막 동기화 시각(예: "10:42"). 값이 있을 때만 보인다 */
  syncTime?: string;
  /** 사용자 이름. 로그인이 없어 지금은 자리 값 */
  userName?: string;
}

export function TopBar({ syncTime, userName = '사용자' }: Props) {
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
              <NavLink
                to={m.to}
                className={styles.navLink}
                aria-keyshortcuts={m.to === '/agent' ? TOGGLE_AGENT_KEYSHORTCUTS : undefined}
              >
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
        <span className={styles.avatar}>
          <Avatar name={userName} labelled />
        </span>
      </div>
    </header>
  );
}
