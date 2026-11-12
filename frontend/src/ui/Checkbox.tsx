// 체크 상자 (Base UI Checkbox). 이름은 label(보이는 글자) 또는 aria-label(업무 글자)로 준다.
import { Checkbox as BaseCheckbox } from '@base-ui/react/checkbox';
import type { ReactNode } from 'react';
import styles from './Checkbox.module.css';
import { Check } from './Icon.tsx';

interface Props {
  checked?: boolean;
  defaultChecked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  disabled?: boolean;
  /** 보이는 이름. 없으면 aria-label이 필요하다 */
  label?: ReactNode;
  'aria-label'?: string;
  name?: string;
  value?: string;
}

export function Checkbox({ label, onCheckedChange, ...props }: Props) {
  const box = (
    <BaseCheckbox.Root
      {...props}
      className={styles.box}
      onCheckedChange={onCheckedChange ? (checked) => onCheckedChange(checked) : undefined}
    >
      <BaseCheckbox.Indicator className={styles.indicator}>
        <Check size={14} strokeWidth={3} aria-hidden="true" />
      </BaseCheckbox.Indicator>
    </BaseCheckbox.Root>
  );
  if (label === undefined) return box;
  return (
    <label className={styles.row}>
      {box}
      {label}
    </label>
  );
}
