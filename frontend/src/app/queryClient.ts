// 서버 데이터 캐시 (TanStack Query 5, FE-D16).
// - retry 1: 순간 끊김은 한 번 다시 묻고, 그래도 실패하면 오류 상태("불러오지 못함 [다시 시도]")를 보인다
// - 창으로 돌아올 때 다시 불러오지 않는다: 업무 줄이 사용자가 보는 중에 바뀌지 않게 한다. 다시 불러오기는 동작(완료 · 되돌리기) 뒤에만
import { QueryClient } from '@tanstack/react-query';

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
        refetchOnWindowFocus: false,
        staleTime: 30_000,
      },
      mutations: {
        retry: 0, // 업무 상태 바꾸기는 두 번 보내지 않는다
      },
    },
  });
}

export const queryClient = createQueryClient();
