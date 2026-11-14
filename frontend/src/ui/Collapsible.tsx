// 접기 · 펼치기 (Base UI Collapsible). 예: 에이전트 단계 목록 · '어떻게 해석했나요'.
// 여닫는 버튼의 aria-expanded는 라이브러리가 붙인다.
import { Collapsible as BaseCollapsible } from '@base-ui/react/collapsible';
import type { ReactNode } from 'react';
import styles from './Collapsible.module.css';
import { ChevronDown } from './Icon.tsx';

interface Props {
  /** 여닫는 버튼 글자 */
  label: ReactNode;
  children: ReactNode;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
}

export function Collapsible({ label, children, open, defaultOpen, onOpenChange, className }: Props) {
  return (
    <BaseCollapsible.Root
      className={className}
      open={open}
      defaultOpen={defaultOpen}
      onOpenChange={onOpenChange ? (next) => onOpenChange(next) : undefined}
    >
      <BaseCollapsible.Trigger className={styles.trigger}>
        {label}
        <ChevronDown size={16} className={styles.chevron} aria-hidden="true" />
      </BaseCollapsible.Trigger>
      <BaseCollapsible.Panel className={styles.panel}>{children}</BaseCollapsible.Panel>
    </BaseCollapsible.Root>
  );
}
