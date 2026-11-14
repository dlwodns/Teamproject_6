// 버튼 (components.md 3절). 주 버튼은 한 영역에 하나만 둔다.
// loading: 글자를 숨겨 폭을 유지하고 스피너를 겹친다(300ms 뒤 보임). disabled 대신 aria-disabled라 포커스가 남는다.
// done: ✓를 잠깐 보인다. 얼마 동안 보일지(0.7초)는 부르는 쪽이 정한다.
import type { ComponentPropsWithRef, MouseEvent } from 'react';
import { cx } from './cx.ts';
import { Check } from './Icon.tsx';
import { LiveRegion } from './LiveRegion.tsx';
import styles from './Button.module.css';
import { Spinner } from './Spinner.tsx';

export interface ButtonProps extends ComponentPropsWithRef<'button'> {
  variant?: 'primary' | 'secondary' | 'ghost';
  size?: 'md' | 'sm';
  loading?: boolean;
  done?: boolean;
  /** 불러오는 중에 화면 읽기 프로그램이 읽는 글자(예: "보내는 중") */
  loadingText?: string;
  /** 끝났을 때 읽는 글자(예: "보냈어요") */
  doneText?: string;
}

export function Button({
  variant = 'secondary',
  size = 'md',
  loading,
  done,
  loadingText = '처리하는 중',
  doneText = '완료했어요',
  className,
  type = 'button',
  onClick,
  children,
  ...props
}: ButtonProps) {
  // loading · done을 넘긴 버튼만 상태 알림 영역을 둔다(모든 버튼에 두면 영역이 너무 많아진다)
  const morphs = loading !== undefined || done !== undefined;
  const busy = Boolean(loading || done);
  const state = loading ? 'loading' : done ? 'done' : undefined;

  const handleClick = (e: MouseEvent<HTMLButtonElement>) => {
    if (busy) {
      e.preventDefault();
      return;
    }
    onClick?.(e);
  };

  return (
    <>
      <button
        {...props}
        type={type}
        className={cx(styles.button, className)}
        data-variant={variant}
        data-size={size}
        data-state={state}
        aria-disabled={busy || props['aria-disabled'] || undefined}
        onClick={handleClick}
      >
        <span className={styles.label}>{children}</span>
        {state && (
          <span className={styles.overlay} aria-hidden="true">
            {loading ? <Spinner size={16} /> : <Check size={18} strokeWidth={2.5} aria-hidden="true" />}
          </span>
        )}
      </button>
      {/* 버튼 안에 두면 버튼 이름에 섞이므로 옆에 둔다 */}
      {morphs && <LiveRegion>{loading ? loadingText : done ? doneText : ''}</LiveRegion>}
    </>
  );
}
