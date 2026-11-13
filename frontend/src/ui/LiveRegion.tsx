import type { ReactNode } from 'react';
import { VisuallyHidden } from './VisuallyHidden.tsx';

interface Props {
  /** 바뀔 때마다 한 번 읽히는 글자. 처음부터 그려 두고 글자만 바꾼다(빈 글자로 시작해도 된다). */
  children?: ReactNode;
  /** 오류만 'assertive'(design_system 6절). 기본은 'polite' */
  politeness?: 'polite' | 'assertive';
}

/** 숨은 상태 알림 영역. 진행 · 결과 문구('보내는 중' · '보냈어요')를 화면 읽기 프로그램에 알린다. */
export function LiveRegion({ children, politeness = 'polite' }: Props) {
  return (
    <VisuallyHidden role={politeness === 'assertive' ? 'alert' : 'status'} aria-live={politeness} aria-atomic="true">
      {children}
    </VisuallyHidden>
  );
}
