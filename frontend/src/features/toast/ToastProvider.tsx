// 일반 토스트(FE-4). 규칙은 toastQueue.ts 머리말. 화면 아래 가운데에 띄운다(오른쪽 아래는 에이전트 버튼 자리).
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type FocusEvent, type MouseEvent, type ReactNode } from 'react';
import { durationFor, pushToast, remainingAfter, removeToast, type Toast, type ToastInput } from './toastQueue.ts';

type Show = (t: ToastInput) => void;

const ToastContext = createContext<Show | null>(null);

/** 토스트 띄우기. ToastProvider 안에서만 쓴다. */
export function useToast(): Show {
  const show = useContext(ToastContext);
  if (!show) throw new Error('useToast는 ToastProvider 안에서만 쓸 수 있다');
  return show;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);
  const pendingFocus = useRef<number | null>(null); // 띄운 뒤 버튼으로 포커스를 옮길 토스트 id

  const show = useCallback<Show>((t) => {
    // 행동 직후 포커스가 사라졌으면(체크한 줄이 목록에서 빠짐) 키보드 사용자가 바로 되돌릴 수 있게 버튼으로 옮긴다
    const focusLost = document.activeElement === null || document.activeElement === document.body;
    const toast: Toast = { ...t, id: nextId.current++, durationMs: durationFor(t) };
    setToasts((list) => pushToast(list, toast));
    if (focusLost && t.action) pendingFocus.current = toast.id;
  }, []);

  const close = useCallback((id: number) => setToasts((list) => removeToast(list, id)), []);

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className="toasts" aria-label="알림 메시지">
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onClose={close} takeFocus={pendingFocus} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastItem({ toast, onClose, takeFocus }: { toast: Toast; onClose: (id: number) => void; takeFocus: { current: number | null } }) {
  const [paused, setPaused] = useState(false);
  const left = useRef(toast.durationMs);
  const actionRef = useRef<HTMLButtonElement>(null);

  // 흐르는 동안만 타이머를 건다. 멈추면 그때까지 지난 시간만큼만 줄여 둔다.
  useEffect(() => {
    if (paused) return;
    const started = Date.now();
    const timer = window.setTimeout(() => onClose(toast.id), left.current);
    return () => {
      window.clearTimeout(timer);
      left.current = remainingAfter(left.current, started, Date.now());
    };
  }, [paused, onClose, toast.id]);

  useEffect(() => {
    if (takeFocus.current !== toast.id) return;
    takeFocus.current = null;
    actionRef.current?.focus();
  }, [takeFocus, toast.id]);

  const keepWhile = useMemo(
    () => ({
      onMouseEnter: () => setPaused(true),
      onMouseLeave: (e: MouseEvent<HTMLDivElement>) => {
        if (!e.currentTarget.contains(document.activeElement)) setPaused(false);
      },
      onFocus: () => setPaused(true),
      onBlur: (e: FocusEvent<HTMLDivElement>) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setPaused(false);
      },
    }),
    [],
  );

  return (
    <div className="toast" data-kind={toast.kind} role={toast.kind === 'error' ? 'alert' : 'status'} {...keepWhile}>
      <span className="toast-text">{toast.text}</span>
      {toast.action && (
        <button
          ref={actionRef}
          type="button"
          className="toast-action"
          onClick={() => {
            toast.action!.run();
            onClose(toast.id);
          }}
        >
          {toast.action.label}
        </button>
      )}
      <button type="button" className="toast-close" aria-label="알림 닫기" onClick={() => onClose(toast.id)}>
        <span aria-hidden="true">✕</span>
      </button>
    </div>
  );
}
