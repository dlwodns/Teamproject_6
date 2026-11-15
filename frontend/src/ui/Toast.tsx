// 토스트 (Base UI Toast · components.md 3절). 모양 · 자리 · 띄우는 함수만 여기에 둔다.
// 어떤 문구를 언제 띄우는지, 완료 · 되돌리기 동작은 FE-4 담당(features/tasks/useTaskActions.ts · lib/toastPolicy.ts)이 이 위에 만든다.
// - 오른쪽 아래, 최대 3개(넘으면 오래된 것부터 닫음). 마우스 · 포커스가 있으면 시간이 멈춘다(라이브러리 기본)
// - 오류만 경고(priority 'high'), 나머지는 상태 알림. F6으로 토스트 영역으로 이동(라이브러리)
import { Toast } from '@base-ui/react/toast';
import { useEffect, type ReactNode } from 'react';
import { AlarmClock, X } from './Icon.tsx';
import styles from './Toast.module.css';
import { TOAST_LIMIT } from './toastApi.ts';

export { TOAST_DEFAULT_TIMEOUT, useToast, type ShowToastOptions, type ToastKind } from './toastApi.ts';

function ToastList() {
  const { toasts, close } = Toast.useToastManager();

  // 라이브러리는 넘친 토스트를 숨김 표시(limited)만 한다 → 명세대로 오래된 것부터 실제로 닫는다
  useEffect(() => {
    for (const t of toasts) {
      if (t.limited && t.transitionStatus !== 'ending') close(t.id);
    }
  }, [toasts, close]);

  return toasts.map((toast) => (
    <Toast.Root key={toast.id} toast={toast} className={styles.toast} swipeDirection={['right', 'down']}>
      <Toast.Content className={styles.content}>
        {toast.type === 'reminder' && (
          <span className={styles.remindIcon} aria-hidden="true">
            <AlarmClock size={16} />
          </span>
        )}
        <div className={styles.text}>
          <Toast.Title className={styles.title} />
          <Toast.Description className={styles.description} />
        </div>
        <Toast.Action className={styles.action} />
        <Toast.Close className={styles.close} aria-label="닫기">
          <X size={16} aria-hidden="true" />
        </Toast.Close>
      </Toast.Content>
    </Toast.Root>
  ));
}

/** 앱 바탕에 한 번 둔다. 토스트 영역(오른쪽 아래)을 함께 그린다 */
export function ToastProvider({ children }: { children: ReactNode }) {
  return (
    <Toast.Provider limit={TOAST_LIMIT}>
      {children}
      <Toast.Portal>
        <Toast.Viewport className={styles.viewport} aria-label="알림 메시지">
          <ToastList />
        </Toast.Viewport>
      </Toast.Portal>
    </Toast.Provider>
  );
}
