// 대시보드 카드 틀: 제목 · 건수 · 오른쪽 위 도구(기간 · 더보기) + 내용. 건수는 불러오는 중 · 오류일 때 '–'(13-8).
import { useEffect, useId, useRef, type ReactNode } from 'react';
import { ChevronRight, VisuallyHidden } from '../../ui/index.ts';
import { PANEL_ID } from '../../app/panel.tsx';
import styles from './DashCard.module.css';

interface Props {
  title: string;
  /** 숫자 = 건수, null = 모름('–'), undefined = 건수 자리 없음 */
  count?: number | null;
  /** 긴급 칸: 제목 앞 검정 점 */
  dot?: boolean;
  tools?: ReactNode;
  children: ReactNode;
}

export function DashCard({ title, count, dot = false, tools, children }: Props) {
  const titleId = useId();
  return (
    <section className={styles.card} aria-labelledby={titleId}>
      <div className={styles.head}>
        <h2 id={titleId} className={styles.title} data-dot={dot ? '' : undefined}>
          {title}
        </h2>
        {count !== undefined && (
          <span className={styles.count}>
            {count ?? '–'}
            {count !== null && <VisuallyHidden>건</VisuallyHidden>}
          </span>
        )}
        {tools && <div className={styles.tools}>{tools}</div>}
      </div>
      {children}
    </section>
  );
}

/** 카드 오른쪽 위 '더보기' → 오른쪽 사이드바 */
export function MoreButton({ name, onClick }: { name: string; onClick: () => void }) {
  return (
    <button type="button" className={styles.more} aria-label={`${name} 더보기`} aria-controls={PANEL_ID} onClick={onClick}>
      더보기
      <ChevronRight size={16} aria-hidden="true" />
    </button>
  );
}

/**
 * 목록을 5줄 높이로 두고 안에서 스크롤한다. check = 확인사항 줄(두 줄 사이 4px 더 높다).
 * 끝에 닿은 뒤 같은 방향 휠은 바로 화면 전체를 움직인다. 브라우저 기본 이어짐(scroll chaining)은
 * 휠을 잠깐 멈춰야 넘어가서(휠 래칭) 목록 위에서는 화면이 안 내려가는 것처럼 느껴진다.
 */
export function ScrollArea({ check = false, children }: { check?: boolean; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (e.ctrlKey || e.deltaY === 0 || el.scrollHeight <= el.clientHeight) return; // 확대 · 가로 휠 · 넘치지 않는 목록은 그대로
      const atTop = el.scrollTop <= 0;
      const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 1;
      if ((e.deltaY > 0 && atBottom) || (e.deltaY < 0 && atTop)) {
        e.preventDefault();
        const line = e.deltaMode === WheelEvent.DOM_DELTA_LINE ? 40 : e.deltaMode === WheelEvent.DOM_DELTA_PAGE ? window.innerHeight : 1;
        window.scrollBy({ top: e.deltaY * line });
      }
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, []);
  return (
    <div ref={ref} className={styles.scroll} data-check={check ? '' : undefined}>
      {children}
    </div>
  );
}
