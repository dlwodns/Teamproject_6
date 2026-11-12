// 칸 · 카드의 불러오는 중 · 빈 상태 · 오류 · 분류 대기 줄 (components.md 3절 · wireframe 13-8).
// 문구 규칙(design_system 5절): 빈 상태는 "없음", 오류는 "불러오지 못함" + [다시 시도]. 오류 줄만 role="alert".
import type { ReactNode } from 'react';
import { Button } from './Button.tsx';
import { Info } from './Icon.tsx';
import styles from './StateRow.module.css';
import { VisuallyHidden } from './VisuallyHidden.tsx';

export type StateRowProps =
  | { state: 'loading' }
  | { state: 'empty'; text?: string }
  | { state: 'error'; onRetry: () => void; text?: string }
  | { state: 'pending'; children: ReactNode };

export function StateRow(props: StateRowProps) {
  switch (props.state) {
    case 'loading':
      return (
        <div className={styles.loading} aria-busy="true">
          <span className={styles.skeleton} aria-hidden="true" />
          <span className={styles.skeleton} aria-hidden="true" />
          <span className={styles.skeleton} aria-hidden="true" />
          <VisuallyHidden>불러오는 중</VisuallyHidden>
        </div>
      );
    case 'empty':
      return <p className={styles.empty}>{props.text ?? '없음'}</p>;
    case 'error':
      return (
        <div className={styles.error} role="alert">
          <p className={styles.errorText}>{props.text ?? '불러오지 못함'}</p>
          <Button size="sm" onClick={props.onRetry}>
            다시 시도
          </Button>
        </div>
      );
    case 'pending':
      return (
        <p className={styles.pending}>
          <Info size={16} className={styles.pendingIcon} aria-hidden="true" />
          <span>{props.children}</span>
        </p>
      );
  }
}
