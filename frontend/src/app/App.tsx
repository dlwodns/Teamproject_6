// 앱 바탕: 서버 데이터(Query) · 토스트 · 말풍선 공급자 + 해시 라우터.
// 앱 바탕 요소(#root)에는 global.css가 isolation: isolate를 준다(Base UI 팝업 겹침 순서, FE-D15).
import { QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router/dom';
import { ToastProvider, TooltipProvider } from '../ui/index.ts';
import { queryClient } from './queryClient.ts';
import { router } from './router.tsx';

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <ToastProvider>
          <RouterProvider router={router} />
        </ToastProvider>
      </TooltipProvider>
    </QueryClientProvider>
  );
}
