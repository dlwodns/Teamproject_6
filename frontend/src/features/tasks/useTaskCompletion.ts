// 업무 줄 완료(체크 상자) 훅. 움직임 순서 · 실패 시 복귀 판단은 completion.ts, 서버 요청은 useTaskActions(FE-4 담당)가 맡는다.
import { useCallback, useSyncExternalStore } from 'react';
import type { TaskId } from '../../api/types.ts';
import { reducedMotion } from '../../lib/motion.ts';
import { completionStore, parseCssTimeMs, runCompletion, type CompletionPhase, type CompletionTimings } from './completion.ts';
import { useTaskActions } from './useTaskActions.ts';

/** 그 업무가 지금 빠지는 중인가. 같은 업무의 모든 줄(긴급 · 유형 · 사이드바)이 같은 값을 본다 */
export function useCompletionPhase(id: TaskId): CompletionPhase | undefined {
  return useSyncExternalStore(
    completionStore.subscribe,
    () => completionStore.get(id),
    () => undefined,
  );
}

function readTimings(): CompletionTimings {
  const css = getComputedStyle(document.documentElement);
  const ms = (name: string) => parseCssTimeMs(css.getPropertyValue(name));
  return { checkMs: ms('--d-short'), slideMs: ms('--d-move'), collapseMs: ms('--d-exit') };
}

const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/** 체크 상자를 누르면 부른다. 성공하면 true, 실패하면 false(줄이 돌아온다) */
export function useCompleteTask(): (id: TaskId) => Promise<boolean> {
  const { complete } = useTaskActions();
  return useCallback(
    (id: TaskId) =>
      runCompletion(id, {
        store: completionStore,
        timings: readTimings(),
        reduceMotion: reducedMotion(),
        wait,
        complete: (ids) => complete(ids, { source: 'button' }),
      }),
    [complete],
  );
}
