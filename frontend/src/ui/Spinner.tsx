import type { CSSProperties } from 'react';
import styles from './Spinner.module.css';
import { VisuallyHidden } from './VisuallyHidden.tsx';

interface Props {
  size?: 16 | 20;
  /** 화면 읽기용 이름. 주변 글자가 이미 상태를 말하면 비워 둔다(장식) */
  label?: string;
}

export function Spinner({ size = 16, label }: Props) {
  return (
    <>
      <span className={styles.spinner} style={{ '--spinner-size': `${size}px` } as CSSProperties} aria-hidden="true" />
      {label && <VisuallyHidden>{label}</VisuallyHidden>}
    </>
  );
}
