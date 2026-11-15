// 대시보드 원자료(['dashboard'] 쿼리) → v3.1 집계. 메일 목록과 같은 캐시를 나눠 쓰고, 완료하면 useTaskActions가 이 캐시를 바꾼다.
// 대시보드 화면과 더보기 사이드바가 각자 이 훅을 불러 같은 값을 본다(사이드바 내용도 완료 즉시 갱신).
import { useMemo } from 'react';
import { useDashboardQuery } from '../../api/queries.ts';
import type { DataOrigin } from '../../api/types.ts';
import { buildDashboard, type DashboardModel } from '../../features/tasks/aggregate.ts';

export type DashboardState =
  | { kind: 'loading' }
  | { kind: 'error'; retry: () => void }
  | { kind: 'ready'; model: DashboardModel; origin: DataOrigin };

export function useDashboardModel(): DashboardState {
  const query = useDashboardQuery();
  const { data, refetch } = query;
  const built = useMemo(() => {
    if (!data) return null;
    try {
      return { ok: true as const, model: buildDashboard(data), origin: data.origin };
    } catch (error) {
      // 응답 계약 위반(id 중복 등)은 대시보드 전체 오류로 보인다. 진단은 개발 중에만 남긴다
      if (import.meta.env?.DEV) console.warn('[대시보드] 집계 실패', error instanceof Error ? `${error.name}: ${error.message}` : typeof error);
      return { ok: false as const };
    }
  }, [data]);

  // 다시 불러오기가 실패해도 이미 받은 데이터가 있으면 그대로 보인다
  if (built?.ok) return { kind: 'ready', model: built.model, origin: built.origin };
  if (query.isPending || (query.isFetching && !data)) return { kind: 'loading' };
  return { kind: 'error', retry: () => void refetch() };
}
