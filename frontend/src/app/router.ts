// 해시 라우터(#/dashboard · #/mail · #/settings). 배포 서버에 SPA 되돌림 설정이 없어도 새로고침이 된다.
// 화면이 세 개뿐이라 라우터 라이브러리를 쓰지 않았다. 메일 상세 등 경로가 늘면(FE-5) 바꾼다.
import { useSyncExternalStore } from 'react';

export const ROUTES = [
  { key: 'dashboard', path: '#/dashboard', label: '대시보드' },
  { key: 'mail', path: '#/mail', label: '메일' },
  { key: 'settings', path: '#/settings', label: '설정' },
] as const;

export type RouteKey = (typeof ROUTES)[number]['key'];

/** 해시에서 경로만 읽는다. '#/dashboard?mock=error'처럼 해시 뒤에 쿼리가 붙어도 '?' 앞부분으로 맞춘다. 모르는 경로는 대시보드. */
export function routeFromHash(hash: string): RouteKey {
  const path = hash.split('?', 1)[0];
  return ROUTES.find((r) => r.path === path)?.key ?? 'dashboard';
}

function current(): RouteKey {
  return routeFromHash(window.location.hash);
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener('hashchange', onChange);
  return () => window.removeEventListener('hashchange', onChange);
}

export function useRoute(): RouteKey {
  return useSyncExternalStore(subscribe, current, () => 'dashboard');
}
