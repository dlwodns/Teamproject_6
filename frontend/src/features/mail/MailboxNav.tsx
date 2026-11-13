// 왼쪽 메일함 (components.md 4.3 · wireframe 13-7). 받은편지함 · 업무 · 확인사항 / 빠른 보기 / 분류 / 계정, 메일함마다 건수.
// 메일함은 주소(#/mail/<box>)라 링크로 둔다. 선택은 굵은 글씨 + 왼쪽 포인트 선(aria-current).
import { Link } from 'react-router';
import { Building, Clock, RankIcon, Star } from '../../ui/index.ts';
import type { BoxItem, BoxSection } from './mailboxes.ts';
import styles from './MailboxNav.module.css';
import { mailPath } from './routes.ts';

interface Props {
  id: string;
  /** 불러오는 중이면 null(건수 자리 '–') */
  sections: BoxSection[] | null;
  selected: string;
}

function BoxIcon({ item }: { item: BoxItem }) {
  if (item.flag === 'superior') return <RankIcon size={16} className={styles.icon} />;
  if (item.flag === 'favorite') return <Star size={14} className={styles.icon} aria-hidden="true" />;
  if (item.flag === 'client') return <Building size={14} className={styles.icon} aria-hidden="true" />;
  if (item.slug === 'due') return <Clock size={14} className={styles.icon} aria-hidden="true" />;
  return null;
}

// 불러오는 중에도 메일함 이름은 보인다(건수만 '–')
const LOADING_SECTIONS: BoxSection[] = [
  {
    title: null,
    items: [
      { slug: 'inbox', label: '받은편지함', count: 0 },
      { slug: 'tasks', label: '업무', count: 0 },
    ],
  },
];

export function MailboxNav({ id, sections, selected }: Props) {
  const loading = sections === null;
  return (
    <nav id={id} className={styles.nav} aria-label="메일함">
      {(sections ?? LOADING_SECTIONS).map((section) => (
        <div key={section.title ?? 'main'} className={styles.section}>
          {section.title && <h2 className={styles.title}>{section.title}</h2>}
          <ul className={styles.list}>
            {section.items.map((item) => (
              <li key={item.slug}>
                <Link to={mailPath(item.slug)} className={styles.item} aria-current={item.slug === selected ? 'true' : undefined}>
                  <span className={styles.name}>
                    <BoxIcon item={item} />
                    {item.label}
                  </span>
                  <span className={styles.count}>{loading ? '–' : item.count}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}
