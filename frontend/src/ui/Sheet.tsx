// 아래 시트 (Base UI Drawer, 모달). 예: BS "완료로 처리할까요?" — 제목 · 체크 상자 · [아니오] [예]만 둔다.
// 아니오 · Esc · 바깥 누르기 · 아래로 쓸어내리기는 모두 onNo 하나로 모은다(components.md 3절).
// 열리면 [예]에 포커스, Tab은 시트 안에서만 돌고, 닫히면 연 자리로 포커스가 돌아간다(라이브러리).
import { Drawer } from '@base-ui/react/drawer';
import { useRef, type ReactNode } from 'react';
import { Button } from './Button.tsx';
import styles from './Sheet.module.css';

interface Props {
  open: boolean;
  title: string;
  children?: ReactNode;
  onYes: () => void;
  onNo: () => void;
  yesLabel?: string;
  noLabel?: string;
  /** [예]를 누른 뒤 서버 응답을 기다리는 동안 */
  yesLoading?: boolean;
}

export function Sheet({ open, title, children, onYes, onNo, yesLabel = '예', noLabel = '아니오', yesLoading }: Props) {
  const yesRef = useRef<HTMLButtonElement>(null);
  return (
    <Drawer.Root
      open={open}
      onOpenChange={(next) => {
        if (!next) onNo();
      }}
    >
      <Drawer.Portal>
        <Drawer.Backdrop className={styles.backdrop} />
        <Drawer.Viewport className={styles.viewport}>
          <Drawer.Popup className={styles.popup} initialFocus={yesRef}>
            <div className={styles.handle} aria-hidden="true" />
            <Drawer.Title className={styles.title}>{title}</Drawer.Title>
            {children && <div className={styles.body}>{children}</div>}
            <div className={styles.actions}>
              <Drawer.Close render={<Button variant="secondary" />}>{noLabel}</Drawer.Close>
              <Button ref={yesRef} variant="primary" loading={yesLoading} loadingText="처리하는 중" onClick={onYes}>
                {yesLabel}
              </Button>
            </div>
          </Drawer.Popup>
        </Drawer.Viewport>
      </Drawer.Portal>
    </Drawer.Root>
  );
}
