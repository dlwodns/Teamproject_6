// 해시 라우터(#/dashboard · #/mail · #/settings). 배포 서버에 SPA 되돌림 설정이 없어도 새로고침이 된다.
// 화면이 세 개뿐이라 라우터 라이브러리를 쓰지 않았다. 메일 상세 등 경로가 늘면(FE-5) 바꾼다.
import { useSyncExternalStore } from 'react';

export const ROUTES = [
  { key: 'dashboard', path: '#/dashboard', label: '대시보드' },
  { key: 'mail', path: '#/mail', label: '메일' },
  { key: 'settings', path: '#/settings', label: '설정' },
] as const;

export type RouteKey = (typeof ROUTES)[number]['key'];

function current(): RouteKey {
  const hash = window.location.hash;
  return ROUTES.find((r) => r.path === hash)?.key ?? 'dashboard';
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener('hashchange', onChange);
  return () => window.removeEventListener('hashchange', onChange);
}

export function useRoute(): RouteKey {
  return useSyncExternalStore(subscribe, current, () => 'dashboard');
}
