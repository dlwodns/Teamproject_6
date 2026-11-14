// 업무 완료의 움직임(components.md 4.2 · UX-D9 · wireframe 13-3) — 판단만 모은 순수 모듈.
//
//   체크 상자 채워짐(--d-short) → 그 업무의 모든 줄에 data-leaving: 오른쪽으로 빠지며 흐려짐(--d-move)
//   → 높이 접힘(--d-exit) → useTaskActions().complete 호출(화면 먼저 바꾸기 → 건수 갱신)
//
// 같은 업무가 긴급 · 유형 칸 · 더보기 사이드바에 함께 있으므로 '어느 업무가 지금 빠지는 중인가'를 줄 하나가 아니라
// 이 저장소 하나에 둔다. 사이드바 내용은 대시보드 화면 밖(앱 틀 패널 자리)에서 그려져 React 문맥을 나눠 쓸 수 없어서
// 모듈 저장소(useSyncExternalStore로 읽음)로 만들었다.
// 서버 요청이 실패하면 단계를 지워 줄이 돌아온다(캐시는 useTaskActions가 되돌린다).
import type { TaskId } from '../../api/types.ts';

export type CompletionPhase = 'checked' | 'leaving';

export interface CompletionStore {
  get(id: TaskId): CompletionPhase | undefined;
  set(id: TaskId, phase: CompletionPhase | null): void;
  subscribe(listener: () => void): () => void;
}

export function createCompletionStore(): CompletionStore {
  const phases = new Map<TaskId, CompletionPhase>();
  const listeners = new Set<() => void>();
  return {
    get: (id) => phases.get(id),
    set(id, phase) {
      if ((phases.get(id) ?? null) === phase) return;
      if (phase === null) phases.delete(id);
      else phases.set(id, phase);
      for (const l of [...listeners]) l();
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

/** 앱 전체가 나눠 쓰는 하나(대시보드 칸 · 더보기 사이드바) */
export const completionStore = createCompletionStore();

/** 움직임 시간(밀리초). 값은 토큰(--d-short · --d-move · --d-exit)에서 읽는다 */
export interface CompletionTimings {
  checkMs: number;
  slideMs: number;
  collapseMs: number;
}

/** CSS 시간 값 → 밀리초. '150ms' → 150, '0.25s' → 250. 읽지 못하면 0(기다리지 않음) */
export function parseCssTimeMs(value: string): number {
  const m = /^\s*(-?\d*\.?\d+)\s*(ms|s)\s*$/i.exec(value);
  if (!m) return 0;
  const n = Number(m[1]);
  const ms = m[2]!.toLowerCase() === 's' ? n * 1000 : n;
  return Number.isFinite(ms) && ms > 0 ? Math.round(ms) : 0;
}

export interface CompletionDeps {
  store: CompletionStore;
  timings: CompletionTimings;
  /** 동작 줄이기 설정이면 기다리지 않고 바로 처리한다 */
  reduceMotion: boolean;
  wait: (ms: number) => Promise<void>;
  complete: (ids: readonly TaskId[]) => Promise<unknown>;
}

/**
 * 업무 한 건 완료 흐름. 이미 진행 중이면 아무것도 하지 않고 false.
 * 성공하면 true, 서버가 실패하면 false(줄이 돌아온다). 실패 문구 · 되돌리기 토스트는 useTaskActions(FE-4)가 맡는다.
 */
export async function runCompletion(id: TaskId, deps: CompletionDeps): Promise<boolean> {
  const { store, timings, reduceMotion, wait } = deps;
  if (store.get(id) !== undefined) return false;
  store.set(id, 'checked');
  try {
    if (!reduceMotion && timings.checkMs > 0) await wait(timings.checkMs);
    store.set(id, 'leaving');
    const out = timings.slideMs + timings.collapseMs;
    if (!reduceMotion && out > 0) await wait(out);
    await deps.complete([id]);
    return true;
  } catch {
    return false;
  } finally {
    store.set(id, null);
  }
}
