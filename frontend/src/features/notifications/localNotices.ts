// 앱 안에서 생긴 알림(서버를 거치지 않는 것) — 지금은 에이전트 작업이 끝났다는 알림 하나다(FE-15 · FE-D22 ③).
// 대화(agentSession)처럼 모듈에 하나만 두고, 알림 센터의 '알림' 탭이 서버 알림과 함께 보인다. 새로고침하면 사라진다.
import { useSyncExternalStore } from 'react';

export interface LocalNotice {
  id: string;
  title: string;
  body: string | null;
  atMs: number;
  read: boolean;
  /** 누르면 갈 에이전트 결과(run id) */
  runId: number | null;
}

const MAX = 20;
let notices: LocalNotice[] = [];
const listeners = new Set<() => void>();

function set(next: LocalNotice[]) {
  notices = next;
  for (const l of listeners) l();
}

export const localNotices = {
  get: (): LocalNotice[] => notices,
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  add(n: Omit<LocalNotice, 'read'>) {
    set([{ ...n, read: false }, ...notices.filter((x) => x.id !== n.id)].slice(0, MAX));
  },
  markRead(id: string) {
    set(notices.map((n) => (n.id === id ? { ...n, read: true } : n)));
  },
  markAllRead() {
    if (notices.some((n) => !n.read)) set(notices.map((n) => ({ ...n, read: true })));
  },
  /** 시험용 */
  reset() {
    set([]);
  },
};

export function useLocalNotices(): LocalNotice[] {
  return useSyncExternalStore(localNotices.subscribe, localNotices.get);
}
