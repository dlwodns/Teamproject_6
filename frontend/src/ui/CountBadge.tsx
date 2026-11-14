// 건수 배지. 10 이상은 '9+'. 숫자는 버튼 이름에 따로 넣는다(예: "알림 센터, 리마인더 3개") → 배지는 숨김.
import styles from './CountBadge.module.css';

export function countBadgeText(count: number): string {
  return count > 9 ? '9+' : String(count);
}

interface Props {
  count: number;
  /** corner = 아이콘 버튼 오른쪽 위에 겹침 */
  placement?: 'inline' | 'corner';
}

export function CountBadge({ count, placement = 'inline' }: Props) {
  if (count <= 0) return null;
  return (
    <span className={styles.badge} data-placement={placement} aria-hidden="true">
      {countBadgeText(count)}
    </span>
  );
}
