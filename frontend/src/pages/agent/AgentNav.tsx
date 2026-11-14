// 에이전트 화면 왼쪽 메뉴 (FE-16 · 명세 5절). 리마인더 = 업무 유형 채널 6개(11-14 결정)마다 건수 + 브리핑 · 회고 · 초안 · 대화 · 기록 · 에이전트가 아는 것.
// - 숫자는 회색 글자. 기한 지남이 있는 채널만 숫자에 리마인드 색. 0건 채널도 남긴다(어디를 볼지 헷갈리지 않게)
// - 고른 메뉴는 aria-current="page" + 채움 바탕 + 굵게(앱의 선택 표시와 같음)
// - 1024px 미만은 위쪽 고르기 상자 하나로 바뀐다(AgentMenuSelect)
import { Link } from 'react-router';
import { menuPath, MENU_LABEL, reminderPath, type AgentMenu, type AgentRoute } from '../../features/agent/agentRoutes.ts';
import { CHANNEL_LABEL, CHANNELS, type Channel } from '../../features/reminders/reminderModel.ts';
import { Select, cx } from '../../ui/index.ts';
import styles from './AgentPage.module.css';

const OTHER_MENUS: readonly Exclude<AgentMenu, 'reminders'>[] = ['briefing', 'chat', 'history'];

interface Props {
  route: AgentRoute;
  /** 리마인더 API가 없으면(실제 서버에 아직 없음) null → 리마인더 · 브리핑 메뉴를 숨긴다 */
  counts: Record<Channel, number> | null;
  /** 기한 지남이 있는 채널 */
  alerts: ReadonlySet<Channel>;
}

const isCurrent = (route: AgentRoute, menu: AgentMenu, group?: Channel) =>
  route.menu === menu && (group === undefined || (route.menu === 'reminders' && route.group === group));

export function AgentNav({ route, counts, alerts }: Props) {
  const others = counts ? OTHER_MENUS : OTHER_MENUS.filter((m) => m !== 'briefing');
  return (
    <nav className={styles.nav} aria-label="캐치봇 메뉴">
      {counts && (
        <>
          <p className={styles.navSection} id="agent-nav-reminders">
            리마인더
          </p>
          <ul className={styles.navList} aria-labelledby="agent-nav-reminders">
            {CHANNELS.map((g) => {
              const current = isCurrent(route, 'reminders', g);
              return (
                <li key={g}>
                  <Link to={reminderPath(g)} className={styles.navLink} aria-current={current ? 'page' : undefined}>
                    <span className={styles.navLabel}>{CHANNEL_LABEL[g]}</span>
                    <span className={cx(styles.navCount, alerts.has(g) && styles.navCountAlert)}>{counts[g]}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
          <hr className={styles.navRule} />
        </>
      )}
      <ul className={styles.navList}>
        {others.map((m) => (
          <li key={m}>
            <Link to={menuPath(m)} className={styles.navLink} aria-current={isCurrent(route, m) ? 'page' : undefined}>
              <span className={styles.navLabel}>{MENU_LABEL[m]}</span>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** 좁은 화면의 메뉴: 고르기 상자 하나 */
export function AgentMenuSelect({ route, counts, onGo }: Props & { onGo: (path: string) => void }) {
  const value = route.menu === 'reminders' ? reminderPath(route.group) : menuPath(route.menu);
  const options = [
    ...(counts ? CHANNELS.map((g) => ({ value: reminderPath(g), label: `리마인더 · ${CHANNEL_LABEL[g]} ${counts[g]}` })) : []),
    ...OTHER_MENUS.filter((m) => counts || m !== 'briefing').map((m) => ({
      value: menuPath(m),
      label: MENU_LABEL[m],
    })),
  ];
  return (
    <div className={styles.menuSelect}>
      <Select label="캐치봇 메뉴" options={options} value={value} onValueChange={onGo} />
    </div>
  );
}
