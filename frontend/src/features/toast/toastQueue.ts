// 일반 토스트 규칙(wireframe 13-6): 검정 바탕 · 정보 5초 · 되돌리기 같은 버튼이 있으면 8초 · 마우스 · 포커스가 있으면 멈춤 ·
// 동시에 3개까지(넘으면 오래된 것부터 닫음) · 오류만 role="alert", 나머지는 role="status".
// 리마인더 토스트(자동으로 사라지지 않는 흰 카드)는 알림 센터 작업에서 따로 만든다.

export type ToastKind = 'info' | 'error';

export interface ToastAction {
  label: string;
  run: () => void;
}

export interface ToastInput {
  kind: ToastKind;
  text: string;
  action?: ToastAction;
}

export interface Toast extends ToastInput {
  id: number;
  durationMs: number;
}

export const MAX_TOASTS = 3;
export const INFO_MS = 5000;
export const WITH_ACTION_MS = 8000;

/** 버튼이 있으면 누를 시간을 더 준다. 오류도 읽을 시간을 더 준다. */
export function durationFor(t: ToastInput): number {
  return t.action || t.kind === 'error' ? WITH_ACTION_MS : INFO_MS;
}

/** 새 토스트를 맨 뒤에 넣고, 최대 개수를 넘으면 오래된 것(앞)부터 뺀다. */
export function pushToast(list: readonly Toast[], toast: Toast, max = MAX_TOASTS): Toast[] {
  const next = [...list, toast];
  return next.length > max ? next.slice(next.length - max) : next;
}

export function removeToast(list: readonly Toast[], id: number): Toast[] {
  return list.filter((t) => t.id !== id);
}

/**
 * 멈출 수 있는 타이머의 남은 시간. 멈춘 동안은 줄지 않는다.
 * startedAtMs: 마지막으로 다시 흐르기 시작한 시각, remainingMs: 그때 남아 있던 시간.
 */
export function remainingAfter(remainingMs: number, startedAtMs: number, nowMs: number): number {
  return Math.max(0, remainingMs - Math.max(0, nowMs - startedAtMs));
}
