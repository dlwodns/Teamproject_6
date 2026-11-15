// 체크 상자 (Base UI Checkbox). 이름은 label(보이는 글자) 또는 aria-label(업무 글자)로 준다.
import { Checkbox as BaseCheckbox } from '@base-ui/react/checkbox';
import type { ReactNode } from 'react';
import styles from './Checkbox.module.css';
import { Check, Minus } from './Icon.tsx';

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
  /** square = 고르기(확인 카드 · 시트), circle = 업무 완료(업무 줄 · 읽기 화면). 완료와 고르기를 모양으로 나눈다 */
  shape?: 'square' | 'circle';
  /** 일부만 골랐을 때(전체 고르기 상자) */
  indeterminate?: boolean;
  /** 목록처럼 한 줄만 Tab에 걸리게 할 때(-1) */
  tabIndex?: number;
  className?: string;
}

export function Checkbox({ label, onCheckedChange, shape = 'square', className, ...props }: Props) {
  const box = (
    <BaseCheckbox.Root
      {...props}
      className={className ? `${styles.box} ${className}` : styles.box}
      data-shape={shape}
      onCheckedChange={onCheckedChange ? (checked) => onCheckedChange(checked) : undefined}
    >
      <BaseCheckbox.Indicator className={styles.indicator}>
        {props.indeterminate ? <Minus size={14} strokeWidth={3} aria-hidden="true" /> : <Check size={14} strokeWidth={3} aria-hidden="true" />}
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
