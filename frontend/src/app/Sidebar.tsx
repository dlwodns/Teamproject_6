// 왼쪽 접이식 주 메뉴(#18 리뷰 합의 방향 · FE-D12 [제안], D20-5 '오른쪽 위 메뉴'와 다름 — 공통 문서 갱신 대기).
// 펼침: 아이콘 + 이름, 접힘: 아이콘만 보이고 이름은 마우스 올림 · 키보드 포커스 때 말풍선으로 보인다.
// 접혀도 이름은 DOM에 남아 링크의 접근 가능한 이름이 된다. 전역 단축키는 두지 않는다(후속 작업).
import type { ReactNode } from 'react';
import { ROUTES, type RouteKey } from './router.ts';

const ICONS: Record<RouteKey, ReactNode> = {
  dashboard: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </svg>
  ),
  mail: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="m3 7 9 6 9-6" />
    </svg>
  ),
  settings: (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1 7 17M17 7l2.1-2.1" />
    </svg>
  ),
};

interface Props {
  route: RouteKey;
  expanded: boolean;
  onToggle: () => void;
}

export function Sidebar({ route, expanded, onToggle }: Props) {
  return (
    <div className="sidebar" data-expanded={expanded}>
      <div className="sidebar-head">
        <button type="button" className="side-toggle" aria-expanded={expanded} aria-controls="side-nav" onClick={onToggle}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <rect x="3" y="4" width="18" height="16" rx="2" />
            <path d="M9 4v16" />
          </svg>
          <span className="side-label">{expanded ? '메뉴 접기' : '메뉴 펼치기'}</span>
        </button>
      </div>
      <nav id="side-nav" aria-label="주 메뉴">
        <ul className="side-list">
          {ROUTES.map((r) => (
            <li key={r.key}>
              <a className="side-link" href={r.path} aria-current={r.key === route ? 'page' : undefined}>
                <span className="side-icon">{ICONS[r.key]}</span>
                <span className="side-label">{r.label}</span>
              </a>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}
