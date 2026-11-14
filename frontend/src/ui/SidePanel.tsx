// 오른쪽 패널 (components.md 3절 SidePanel). <aside>로 만들고 모달이 아니다 — 배경 조작을 막지 않고 포커스를 가두지 않는다.
// - 열리면 패널 제목으로 포커스, 닫히면(✕ · Esc) 연 버튼으로 포커스를 돌려준다
// - Esc: 위에 열린 메뉴 · 팝오버가 먼저 닫힌다(Base UI가 그 Esc를 preventDefault 하므로 여기서는 건너뛴다)
// - 한 번에 하나만 여는 것은 앱 틀의 usePanel()이 맡는다
import { useEffect, useId, useRef, type CSSProperties, type ReactNode } from 'react';
import { X } from './Icon.tsx';
import { IconButton } from './IconButton.tsx';
import styles from './SidePanel.module.css';

interface Props {
  title: string;
  onClose: () => void;
  children: ReactNode;
  /** 패널 폭(CSS 값). 기본 에이전트 폭 */
  width?: string;
  id?: string;
  /** 제목 옆(✕ 앞)에 붙일 것 */
  headerExtra?: ReactNode;
  /** 닫기 버튼 이름. 기본 "닫기" */
  closeLabel?: string;
}

export function SidePanel({ title, onClose, children, width = 'var(--agent-width)', id, headerExtra, closeLabel = '닫기' }: Props) {
  const titleId = useId();
  const panelRef = useRef<HTMLElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  // 열 때: 연 요소를 기억하고 제목으로 포커스. 닫힐 때(사라질 때): 포커스가 패널 안에 있었거나 사라졌으면 연 요소로 돌려준다
  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const panel = panelRef.current;
    titleRef.current?.focus();
    return () => {
      const active = document.activeElement;
      const focusLost = !active || active === document.body || (panel?.contains(active) ?? false);
      if (focusLost && opener?.isConnected) opener.focus();
    };
  }, []);

  // window에서 듣는다: 메뉴 · 팝오버의 Esc는 document에서 먼저 처리되고 preventDefault 된다
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented || e.isComposing || e.keyCode === 229) return;
      onCloseRef.current();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <aside
      ref={panelRef}
      id={id}
      className={styles.panel}
      style={{ '--panel-width': width } as CSSProperties}
      aria-labelledby={titleId}
    >
      <div className={styles.head}>
        <h2 id={titleId} ref={titleRef} className={styles.title} tabIndex={-1}>
          {title}
        </h2>
        {headerExtra}
        <IconButton label={closeLabel} icon={<X size={20} aria-hidden="true" />} onClick={onClose} />
      </div>
      <div className={styles.body}>{children}</div>
    </aside>
  );
}
