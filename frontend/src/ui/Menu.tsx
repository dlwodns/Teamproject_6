// 드롭다운 메뉴 (Base UI Menu). 예: [나중에 ▾] · ⋯. 화살표 키 이동 · 글자로 찾기는 라이브러리가 한다.
//   <Menu label="나중에" trigger={<Button>나중에</Button>} items={snoozeOptions(now).map(…)} />
import { Menu as BaseMenu } from '@base-ui/react/menu';
import { Fragment, type ReactElement, type ReactNode } from 'react';
import styles from './Menu.module.css';

export interface MenuItemSpec {
  key: string;
  label: string;
  /** 오른쪽 보조 글자(예: 실제 시각 "11/7(토) 08:30") */
  detail?: ReactNode;
  onSelect: () => void;
  disabled?: boolean;
  /** 이 줄 위에 구분선 */
  separatorBefore?: boolean;
}

interface Props {
  /** 여는 버튼. ref와 props를 DOM 버튼에 넘기는 부품이어야 한다(Button · IconButton) */
  trigger: ReactElement;
  items: readonly MenuItemSpec[];
  align?: 'start' | 'center' | 'end';
}

export function Menu({ trigger, items, align = 'start' }: Props) {
  return (
    <BaseMenu.Root>
      <BaseMenu.Trigger render={trigger} />
      <BaseMenu.Portal>
        <BaseMenu.Positioner className={styles.positioner} align={align} sideOffset={4} collisionPadding={12}>
          <BaseMenu.Popup className={styles.popup}>
            {items.map((it) => (
              <Fragment key={it.key}>
                {it.separatorBefore && <BaseMenu.Separator className={styles.separator} />}
                <BaseMenu.Item className={styles.item} label={it.label} disabled={it.disabled} onClick={it.onSelect}>
                  <span>{it.label}</span>
                  {it.detail && <span className={styles.detail}>{it.detail}</span>}
                </BaseMenu.Item>
              </Fragment>
            ))}
          </BaseMenu.Popup>
        </BaseMenu.Positioner>
      </BaseMenu.Portal>
    </BaseMenu.Root>
  );
}
