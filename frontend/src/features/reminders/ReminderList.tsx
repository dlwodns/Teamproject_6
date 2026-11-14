// 리마인더 목록 (FE-16 · 명세 5절 가운데 칸). 한 줄 = 제목 + 둘째 줄(유형 · 이유, 회색).
// - 목록 상자(listbox): ↑ ↓ · Home · End로 줄을 옮기고 Enter · Space로 고른다(메일 목록과 같은 방식). 고른 줄은 진한 테두리 + aria-selected
// - '조용히 둔 것 N건'은 맨 아래 접기 한 곳에(알림을 3번 보내 이제 목록에만 두는 항목)
// - 빈 상태는 무엇이 여기에 나타날지 + 다음 행동을 말한다
import { useRef, type KeyboardEvent, type ReactNode } from 'react';
import type { ReminderItem } from '../../api/contract.ts';
import { Collapsible, cx } from '../../ui/index.ts';
import { secondLine } from './reminderModel.ts';
import styles from './ReminderList.module.css';

interface Props {
  label: string;
  items: readonly ReminderItem[];
  quiet: readonly ReminderItem[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
  empty: ReactNode;
}

/** 줄 요소 id(목록 밖에서 포커스를 옮길 때) */
export const reminderOptionId = (key: string) => `reminder-option-${key.replace(/[^A-Za-z0-9_-]/g, '-')}`;

function Options({ label, items, selectedKey, onSelect }: Pick<Props, 'label' | 'items' | 'selectedKey' | 'onSelect'>) {
  const ref = useRef<HTMLUListElement>(null);
  // 고른 줄(없으면 첫 줄)만 Tab으로 들어온다
  const tabKey = items.some((i) => i.key === selectedKey) ? selectedKey : (items[0]?.key ?? null);

  const onKeyDown = (e: KeyboardEvent<HTMLUListElement>) => {
    const options = [...(ref.current?.querySelectorAll<HTMLElement>('[role="option"]') ?? [])];
    const at = options.indexOf(document.activeElement as HTMLElement);
    let next = -1;
    if (e.key === 'ArrowDown') next = Math.min(options.length - 1, at + 1);
    else if (e.key === 'ArrowUp') next = Math.max(0, at - 1);
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = options.length - 1;
    else if ((e.key === 'Enter' || e.key === ' ') && at >= 0) {
      e.preventDefault();
      const key = options[at]?.dataset['key'];
      if (key) onSelect(key);
      return;
    } else return;
    e.preventDefault();
    options[next]?.focus();
  };

  return (
    <ul ref={ref} role="listbox" aria-label={label} className={styles.list} onKeyDown={onKeyDown}>
      {items.map((it) => (
        <li
          key={it.key}
          id={reminderOptionId(it.key)}
          role="option"
          aria-selected={it.key === selectedKey}
          tabIndex={it.key === tabKey ? 0 : -1}
          data-key={it.key}
          className={cx(styles.row, it.key === selectedKey && styles.selected)}
          onClick={() => onSelect(it.key)}
        >
          <span className={styles.title}>{it.title}</span>
          <span className={styles.sub}>{secondLine(it)}</span>
        </li>
      ))}
    </ul>
  );
}

export function ReminderList({ label, items, quiet, selectedKey, onSelect, empty }: Props) {
  if (items.length === 0 && quiet.length === 0) return <div className={styles.empty}>{empty}</div>;
  const quietSelected = quiet.some((q) => q.key === selectedKey);
  return (
    <div className={styles.root}>
      {items.length > 0 && <Options label={label} items={items} selectedKey={selectedKey} onSelect={onSelect} />}
      {quiet.length > 0 && (
        <Collapsible className={styles.quiet} label={<span className={styles.quietLabel}>{`조용히 둔 것 ${quiet.length}건`}</span>} defaultOpen={quietSelected}>
          <Options label={`${label} · 조용히 둔 것`} items={quiet} selectedKey={selectedKey} onSelect={onSelect} />
        </Collapsible>
      )}
    </div>
  );
}
