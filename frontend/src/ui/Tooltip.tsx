// 말풍선 (Base UI Tooltip). 보조 설명일 뿐이고, 이름은 버튼 · 칩에 따로 단다(components.md 3절).
// 터치 기기에서는 라이브러리가 말풍선을 띄우지 않는다 → 뜻은 항상 글자나 aria-label로도 전한다.
import { Tooltip as BaseTooltip } from '@base-ui/react/tooltip';
import type { ReactElement, ReactNode } from 'react';
import styles from './Tooltip.module.css';

/** 앱 바탕에 한 번 둔다. 말풍선 사이를 옮길 때 지연 없이 바로 보인다. */
export function TooltipProvider({ children }: { children: ReactNode }) {
  return (
    <BaseTooltip.Provider delay={400} closeDelay={0}>
      {children}
    </BaseTooltip.Provider>
  );
}

interface TooltipContentProps {
  content: ReactNode;
  side?: 'top' | 'bottom' | 'left' | 'right';
}

/** Tooltip.Root 안에서 쓰는 말풍선 본체(IconButton처럼 트리거를 직접 그리는 부품용) */
export function TooltipPopup({ content, side = 'bottom' }: TooltipContentProps) {
  return (
    <BaseTooltip.Portal>
      <BaseTooltip.Positioner className={styles.positioner} side={side} sideOffset={6} collisionPadding={8}>
        <BaseTooltip.Popup className={styles.popup}>{content}</BaseTooltip.Popup>
      </BaseTooltip.Positioner>
    </BaseTooltip.Portal>
  );
}

interface TooltipProps extends TooltipContentProps {
  /** 말풍선을 붙일 요소. ref를 받고 props를 DOM에 펼치는 요소여야 한다(예: <span tabIndex={0}>) */
  children: ReactElement;
  disabled?: boolean;
}

/** 아무 요소에 말풍선을 붙인다. 포커스로도 보이려면 children이 포커스를 받을 수 있어야 한다. */
export function Tooltip({ children, content, side, disabled }: TooltipProps) {
  return (
    <BaseTooltip.Root disabled={disabled}>
      <BaseTooltip.Trigger render={children} />
      <TooltipPopup content={content} side={side} />
    </BaseTooltip.Root>
  );
}

export { BaseTooltip };
