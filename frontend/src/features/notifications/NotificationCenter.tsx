// 알림 센터 진입점(준비 중). 알림 API(GET /notifications, 구조도 8절 [제안])가 없어 숫자 배지를 달지 않는다.
// 연결되면 리마인더 · 답장 후 완료 확인(reply_confirm, D48) 두 종류가 이 목록에 들어온다.
import { useEffect, useId, useRef, useState } from 'react';

export function NotificationCenter() {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    const onPointer = (e: PointerEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('keydown', onKey, true);
    document.addEventListener('pointerdown', onPointer);
    return () => {
      document.removeEventListener('keydown', onKey, true);
      document.removeEventListener('pointerdown', onPointer);
    };
  }, [open]);

  return (
    <div ref={wrapRef}>
      <button
        ref={buttonRef}
        type="button"
        className="btn btn-icon"
        aria-label="알림 센터 (준비 중)"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
          <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
        </svg>
      </button>
      {open && (
        <section id={panelId} className="card popover" aria-labelledby={`${panelId}-title`}>
          <div className="popover-head">
            <h2 id={`${panelId}-title`}>알림 센터</h2>
            <span className="badge-soon">준비 중</span>
          </div>
          <p>알림 기능이 아직 연결되지 않았습니다.</p>
          <p className="note">
            리마인더와 답장 후 완료 확인 알림이 연결되면 여기에 표시됩니다. 지금은 알림 수를 세지 않으므로 숫자를 표시하지 않습니다.
          </p>
        </section>
      )}
    </div>
  );
}
