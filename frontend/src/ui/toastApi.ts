// 토스트를 띄우고 닫는 함수(useToast)와 종류 · 기본 시간. 화면 파일(.tsx) 없이 불러올 수 있게 Toast.tsx에서 떼어 냈다.
// 로직 시험(node --test, FE-D18)은 .tsx를 읽지 못해서, 토스트를 띄우는 로직(features/tasks/useTaskActions.ts)이 이 파일만 부른다.
// 모양 · 자리는 그대로 Toast.tsx(ToastProvider)에 있다. Toast.tsx가 이 파일을 다시 내보내므로 ui/index.ts는 바뀌지 않는다.
import { Toast } from '@base-ui/react/toast';
import { useCallback, useMemo, type ReactNode } from 'react';

export type ToastKind = 'info' | 'undo' | 'error' | 'reminder';

/** 종류별 기본 시간(ms). 0 = 자동으로 닫히지 않음. 정책을 바꿀 때는 show()의 timeout으로 덮어쓴다 */
export const TOAST_DEFAULT_TIMEOUT: Record<ToastKind, number> = {
  info: 5000,
  undo: 8000,
  error: 8000,
  reminder: 0,
};

export const TOAST_LIMIT = 3;

export interface ShowToastOptions {
  kind: ToastKind;
  /** 한 줄 결과(예: "3건을 완료로 바꿨어요") */
  title: ReactNode;
  description?: ReactNode;
  /** 버튼 글자. undo의 기본은 "실행 취소"(에이전트 결과 카드 · 캐치봇과 같게, #85 리뷰), error는 onAction이 있으면 "다시 시도" */
  actionLabel?: string;
  onAction?: () => void;
  timeout?: number;
  /** 같은 id로 다시 띄우면 그 토스트를 바꾸고 시간을 다시 잰다 */
  id?: string;
  onClose?: () => void;
}

const DEFAULT_ACTION_LABEL: Partial<Record<ToastKind, string>> = { undo: '실행 취소', error: '다시 시도' };

/** 토스트를 띄우고 닫는 함수. ToastProvider 안에서만 쓴다 */
export function useToast(): { show: (opts: ShowToastOptions) => string; close: (id: string) => void } {
  const manager = Toast.useToastManager();
  const { add, close: closeToast } = manager;

  const show = useCallback(
    ({ kind, title, description, actionLabel, onAction, timeout, id, onClose }: ShowToastOptions) => {
      const label = actionLabel ?? DEFAULT_ACTION_LABEL[kind];
      return add({
        id,
        type: kind,
        title,
        description,
        timeout: timeout ?? TOAST_DEFAULT_TIMEOUT[kind],
        priority: kind === 'error' ? 'high' : 'low',
        onClose,
        actionProps: onAction && label ? { children: label, onClick: onAction } : undefined,
      });
    },
    [add],
  );

  const close = useCallback((id: string) => closeToast(id), [closeToast]);
  return useMemo(() => ({ show, close }), [show, close]);
}

