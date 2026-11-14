// 왼쪽 메일함 (components.md 4.3 · wireframe 13-7). 받은편지함 · 업무 · 확인사항 / 빠른 보기 / 분류 / 계정, 메일함마다 건수.
// 메일함은 주소(#/mail/<box>)라 링크로 둔다. 선택은 굵은 글씨 + 왼쪽 포인트 선(aria-current).
// 줄: [아이콘 칸 16px] 이름 · (안 읽은 수) · 전체 건수. 묶음 제목은 이름과 같은 선에서 시작한다.
import { Link } from 'react-router';
import { Building, Clock, RankIcon, Star, VisuallyHidden } from '../../ui/index.ts';
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
                  {/* 아이콘이 없는 메일함도 같은 자리를 비워 둬 이름이 한 줄로 맞는다 */}
                  <span className={styles.iconSlot}>
                    <BoxIcon item={item} />
                  </span>
                  <span className={styles.name} data-unread={item.unread ? '' : undefined}>
                    {item.label}
                  </span>
                  {/* 숫자는 한 칸만(전체 건수, wireframe V-12). 안 읽은 메일이 있으면 이름이 굵어지고 화면 읽기로 수를 알린다.
                      숫자 두 개를 나란히 두면 무엇이 무엇인지 헷갈린다 */}
                  {!loading && item.unread ? <VisuallyHidden>안 읽음 {item.unread}통, 전체</VisuallyHidden> : null}
                  <span className={styles.count}>
                    {loading ? '–' : item.count}
                    <VisuallyHidden>통</VisuallyHidden>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}
