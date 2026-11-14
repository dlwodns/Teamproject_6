// 팝오버 (Base UI Popover). 예: 🔔 알림 센터. 바깥 누르기 · Esc로 닫히고 여는 버튼으로 포커스가 돌아간다(라이브러리).
//   <Popover title="알림 센터" trigger={<IconButton label="알림 센터 열기" icon={<Bell />} />}>…</Popover>
import { Popover as BasePopover } from '@base-ui/react/popover';
import type { ReactElement, ReactNode } from 'react';
import styles from './Popover.module.css';

interface Props {
  /** 여는 버튼. ref와 props를 DOM 버튼에 넘기는 부품이어야 한다(Button · IconButton) */
  trigger: ReactElement;
  /** 팝업 제목(h2). 팝업의 접근성 이름이 된다 */
  title: string;
  /** 제목 줄 오른쪽(탭 · 버튼 등) */
  headerExtra?: ReactNode;
  children: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  side?: 'top' | 'bottom';
  align?: 'start' | 'center' | 'end';
}

export function Popover({ trigger, title, headerExtra, children, open, onOpenChange, side = 'bottom', align = 'end' }: Props) {
  return (
    <BasePopover.Root open={open} onOpenChange={onOpenChange ? (next) => onOpenChange(next) : undefined}>
      <BasePopover.Trigger render={trigger} />
      <BasePopover.Portal>
        <BasePopover.Positioner className={styles.positioner} side={side} align={align} sideOffset={6} collisionPadding={12}>
          <BasePopover.Popup className={styles.popup}>
            <div className={styles.head}>
              <BasePopover.Title className={styles.title}>{title}</BasePopover.Title>
              {headerExtra}
            </div>
            <div className={styles.body}>{children}</div>
          </BasePopover.Popup>
        </BasePopover.Positioner>
      </BasePopover.Portal>
    </BasePopover.Root>
  );
}
