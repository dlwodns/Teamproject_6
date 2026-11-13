import type { ComponentPropsWithRef } from 'react';
import { cx } from './cx.ts';
import styles from './VisuallyHidden.module.css';

/** 화면 읽기 전용 글자. 보이는 글자를 대신하지 않고 덧붙일 때만 쓴다. */
export function VisuallyHidden({ className, ...props }: ComponentPropsWithRef<'span'>) {
  return <span {...props} className={cx(styles.hidden, className)} />;
}
