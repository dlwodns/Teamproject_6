// 확인사항 줄(I1) · 응답 대기 줄(W1). 카드와 더보기 사이드바가 같이 쓴다.
import type { Awaiting } from '../../api/types.ts';
import type { CheckItem } from '../../features/tasks/aggregate.ts';
import { useOpenMail } from '../../features/tasks/useOpenMail.ts';
import { Chip, DueLabel, VisuallyHidden } from '../../ui/index.ts';
import styles from './InfoRows.module.css';

/** 확인사항 한 줄: 사유 칩 · 제목 · 받은 때 / 발신자. 누르면 메일 화면의 그 메일로 */
function CheckItemRow({ item }: { item: CheckItem }) {
  const openMail = useOpenMail();
  return (
    <li>
      <button type="button" className={styles.check} data-unread={item.unread ? '' : undefined} onClick={() => openMail(item.mailId)}>
        {item.chip ? <Chip kind={item.lane === '확인' ? 'reason' : 'category'}>{item.chip}</Chip> : <span />}
        <span className={styles.subject}>
          {item.subject}
          {item.unread && <VisuallyHidden> · 안 읽음</VisuallyHidden>}
        </span>
        <span className={styles.when}>{item.whenText}</span>
        <span className={styles.meta}>{item.sender}</span>
      </button>
    </li>
  );
}

export function CheckItemList({ items }: { items: readonly CheckItem[] }) {
  return (
    <ul className={styles.list}>
      {items.map((it) => (
        <CheckItemRow key={it.mailId} item={it} />
      ))}
    </ul>
  );
}

/** 응답 대기 한 줄: 제목 / 받는 사람 + 회색 경과일 라벨. 보낸 메일이라 메일 화면으로 가지 않는다 */
export function AwaitingList({ items }: { items: readonly Awaiting[] }) {
  return (
    <ul className={styles.list}>
      {items.map((w) => (
        <li key={w.mailId} className={styles.wait}>
          <span className={styles.waitText}>
            <span className={styles.subject}>{w.subject}</span>
            <span className={styles.meta}>{w.to}</span>
          </span>
          <DueLabel kind="none" text={`${w.days}일`} srText={`보낸 지 ${w.days}일`} />
        </li>
      ))}
    </ul>
  );
}
