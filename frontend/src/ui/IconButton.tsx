// 아이콘만 있는 버튼. 접근성 이름(label)이 필수이고, 같은 글자를 말풍선으로도 보인다(components.md 3절).
// 다른 Base UI 트리거와 겹쳐 쓸 수 있도록 ref와 받은 props를 모두 버튼에 넘긴다:
//   <Popover.Trigger render={<IconButton label="알림 센터 열기" icon={<Bell />} />} />
import type { ComponentPropsWithRef, ReactNode } from 'react';
import { cx } from './cx.ts';
import styles from './IconButton.module.css';
import { BaseTooltip, TooltipPopup } from './Tooltip.tsx';

export interface IconButtonProps extends Omit<ComponentPropsWithRef<'button'>, 'children' | 'aria-label'> {
  /** 화면 읽기 이름 겸 말풍선 글자(예: "알림 센터 열기") */
  label: string;
  /** 아이콘(20px, currentColor). 아이콘 옆 숫자 배지 같은 덧붙임도 여기에 */
  icon: ReactNode;
  /** md = 32px(기본), lg = 40px(상단 바) */
  size?: 'md' | 'lg';
  /** 말풍선 글자를 이름과 다르게 할 때(보통은 비운다) */
  tooltip?: ReactNode;
}

export function IconButton({ label, icon, size = 'md', tooltip, className, type = 'button', ref, ...props }: IconButtonProps) {
  return (
    <BaseTooltip.Root>
      <BaseTooltip.Trigger
        {...props}
        ref={ref}
        type={type}
        aria-label={label}
        data-size={size}
        className={cx(styles.iconButton, className)}
      >
        {icon}
      </BaseTooltip.Trigger>
      <TooltipPopup content={tooltip ?? label} />
    </BaseTooltip.Root>
  );
}
