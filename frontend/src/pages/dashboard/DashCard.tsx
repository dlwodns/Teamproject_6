// 대시보드 카드 틀: 제목 · 건수 · 오른쪽 도구(더보기 · 기간) + 내용. 건수는 불러오는 중 · 오류일 때 '–'(13-8).
import { useId, type ReactNode } from 'react';
import { Button, VisuallyHidden } from '../../ui/index.ts';
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

/** 카드 머리의 [더보기]. 이름에 칸 이름을 넣는다(예: '요청 더보기') */
export function MoreButton({ name, onClick }: { name: string; onClick: () => void }) {
  return (
    <Button variant="ghost" size="sm" aria-label={`${name} 더보기`} aria-controls={PANEL_ID} onClick={onClick}>
      더보기
    </Button>
  );
}

/** 칸 아래 '+N건 더보기' */
export function ExpandButton({ hidden, name, onClick }: { hidden: number; name: string; onClick: () => void }) {
  return (
    <button type="button" className={styles.expand} aria-label={`${name} +${hidden}건 더보기`} aria-controls={PANEL_ID} onClick={onClick}>
      +{hidden}건 더보기
    </button>
  );
}
