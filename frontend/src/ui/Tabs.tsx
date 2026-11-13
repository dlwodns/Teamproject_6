// 탭 (Base UI Tabs). 예: I1 [확인 | 참고] · 알림 센터 [리마인더 | 알림]. 화살표 키로 탭을 옮긴다(라이브러리).
import { Tabs as BaseTabs } from '@base-ui/react/tabs';
import type { ReactNode } from 'react';
import styles from './Tabs.module.css';

export interface TabItem<V extends string> {
  value: V;
  label: string;
  /** 탭 옆 건수. 없으면 숨긴다 */
  count?: number;
  content: ReactNode;
}

interface Props<V extends string> {
  /** 탭 묶음 이름(화면 읽기용) */
  label: string;
  items: readonly TabItem<V>[];
  value?: V;
  defaultValue?: V;
  onValueChange?: (value: V) => void;
  className?: string;
}

export function Tabs<V extends string>({ label, items, value, defaultValue, onValueChange, className }: Props<V>) {
  return (
    <BaseTabs.Root
      className={className}
      value={value}
      defaultValue={defaultValue ?? items[0]?.value}
      onValueChange={onValueChange ? (v) => onValueChange(v as V) : undefined}
    >
      <BaseTabs.List className={styles.list} aria-label={label}>
        {items.map((it) => (
          <BaseTabs.Tab key={it.value} value={it.value} className={styles.tab}>
            {it.label}
            {it.count !== undefined && <span className={styles.count}>{it.count}</span>}
          </BaseTabs.Tab>
        ))}
      </BaseTabs.List>
      {items.map((it) => (
        <BaseTabs.Panel key={it.value} value={it.value} className={styles.panel}>
          {it.content}
        </BaseTabs.Panel>
      ))}
    </BaseTabs.Root>
  );
}
