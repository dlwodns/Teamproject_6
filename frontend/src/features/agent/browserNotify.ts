// 브라우저 알림 (FE-15 · FE-D22). 허락은 절대 저절로 묻지 않는다 — 에이전트 화면의 '작업이 끝나면 브라우저 알림 받기'를
// 사용자가 켤 때만 묻는다. 켠 값은 이 브라우저에만 남긴다(localStorage, 막혀 있으면 이번 접속 동안만).
import { useCallback, useSyncExternalStore } from 'react';
import type { BrowserPermission } from './agentNotify.ts';

const KEY = 'cne.agent.browserNotify';
let optIn = readOptIn();
const listeners = new Set<() => void>();

function readOptIn(): boolean {
  try {
    return globalThis.localStorage?.getItem(KEY) === '1';
  } catch {
    return false;
  }
}

export function browserPermission(): BrowserPermission {
  if (typeof Notification === 'undefined') return 'unsupported';
  return Notification.permission;
}

export function browserOptIn(): boolean {
  return optIn;
}

function setOptIn(on: boolean) {
  optIn = on;
  try {
    globalThis.localStorage?.setItem(KEY, on ? '1' : '0');
  } catch {
    // 저장이 막힌 브라우저: 이번 접속 동안만 기억한다
  }
  for (const l of listeners) l();
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

/** 켜기 · 끄기. 켤 때 아직 묻지 않았으면 이때 한 번 묻는다 */
export function useBrowserNotify(): { on: boolean; permission: BrowserPermission; toggle: (on: boolean) => Promise<void> } {
  const on = useSyncExternalStore(subscribe, browserOptIn);
  const permission = browserPermission();
  const toggle = useCallback(async (next: boolean) => {
    if (!next) {
      setOptIn(false);
      return;
    }
    if (typeof Notification === 'undefined') return;
    let p = Notification.permission;
    if (p === 'default') {
      try {
        p = await Notification.requestPermission();
      } catch {
        p = 'denied';
      }
    }
    setOptIn(p === 'granted');
  }, []);
  return { on: on && permission === 'granted', permission, toggle };
}

/** 브라우저 알림 하나. 누르면 이 탭으로 돌아와 onClick */
export function showBrowserNotification(title: string, body: string, tag: string, onClick: () => void) {
  if (browserPermission() !== 'granted') return;
  try {
    const n = new Notification(title, { body, tag });
    n.onclick = () => {
      window.focus();
      onClick();
      n.close();
    };
  } catch {
    // 일부 브라우저(안드로이드 크롬)는 서비스 워커 없이 알림을 만들 수 없다 — 토스트로 충분하다
  }
}
