// 에이전트 화면 왼쪽 메뉴 (FE-16 · 명세 5절). 리마인더 묶음마다 건수 + 브리핑 · 회고 · 초안 · 대화 · 기록 · 에이전트가 아는 것.
// - 숫자는 회색 글자. 기한 지남이 있는 '기한'만 숫자에 리마인드 색(한 화면에 색 신호 하나). 0건 묶음도 남긴다(어디를 볼지 헷갈리지 않게)
// - 고른 메뉴는 aria-current="page" + 채움 바탕 + 굵게(앱의 선택 표시와 같음)
// - 1024px 미만은 위쪽 고르기 상자 하나로 바뀐다(AgentMenuSelect)
import { Link } from 'react-router';
import { menuPath, MENU_LABEL, reminderPath, type AgentMenu, type AgentRoute } from '../../features/agent/agentRoutes.ts';
import { GROUP_FILTERS, GROUP_LABEL, type GroupFilter } from '../../features/reminders/reminderModel.ts';
import { Select, cx } from '../../ui/index.ts';
import styles from './AgentPage.module.css';

const OTHER_MENUS: readonly Exclude<AgentMenu, 'reminders'>[] = ['briefing', 'drafts', 'chat', 'history', 'memory'];

interface Props {
  route: AgentRoute;
  /** 리마인더 API가 없으면(실제 서버에 아직 없음) null → 리마인더 · 브리핑 메뉴를 숨긴다 */
  counts: Record<GroupFilter, number> | null;
  /** 기한 묶음에 기한 지남이 있다 */
  dueAlert: boolean;
  drafts: number;
}

const isCurrent = (route: AgentRoute, menu: AgentMenu, group?: GroupFilter) =>
  route.menu === menu && (group === undefined || (route.menu === 'reminders' && route.group === group));

export function AgentNav({ route, counts, dueAlert, drafts }: Props) {
  const others = counts ? OTHER_MENUS : OTHER_MENUS.filter((m) => m !== 'briefing');
  return (
    <nav className={styles.nav} aria-label="에이전트 메뉴">
      {counts && (
        <>
          <p className={styles.navSection} id="agent-nav-reminders">
            리마인더
          </p>
          <ul className={styles.navList} aria-labelledby="agent-nav-reminders">
            {GROUP_FILTERS.map((g) => {
              const current = isCurrent(route, 'reminders', g);
              return (
                <li key={g}>
                  <Link to={reminderPath(g)} className={styles.navLink} aria-current={current ? 'page' : undefined}>
                    <span className={styles.navLabel}>{GROUP_LABEL[g]}</span>
                    <span className={cx(styles.navCount, g === 'due' && dueAlert && styles.navCountAlert)}>{counts[g]}</span>
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
              {m === 'drafts' && drafts > 0 && <span className={styles.navCount}>{drafts}</span>}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** 좁은 화면의 메뉴: 고르기 상자 하나 */
export function AgentMenuSelect({ route, counts, drafts, onGo }: Props & { onGo: (path: string) => void }) {
  const value = route.menu === 'reminders' ? reminderPath(route.group) : menuPath(route.menu);
  const options = [
    ...(counts ? GROUP_FILTERS.map((g) => ({ value: reminderPath(g), label: `리마인더 · ${GROUP_LABEL[g]} ${counts[g]}` })) : []),
    ...OTHER_MENUS.filter((m) => counts || m !== 'briefing').map((m) => ({
      value: menuPath(m),
      label: m === 'drafts' && drafts > 0 ? `${MENU_LABEL[m]} ${drafts}` : MENU_LABEL[m],
    })),
  ];
  return (
    <div className={styles.menuSelect}>
      <Select label="에이전트 메뉴" options={options} value={value} onValueChange={onGo} />
    </div>
  );
}
