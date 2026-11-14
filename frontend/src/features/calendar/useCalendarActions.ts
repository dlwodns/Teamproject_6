// 캘린더 일정 넣기 · 빼기 · 되돌리기(FE-12). 끝나면 달력 · 기록 탭을 서버 값으로 다시 맞춘다.
import { useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';
import { api } from '../../api/client.ts';
import type { CalendarEventCreate, CalendarEventResult } from '../../api/contract.ts';
import { queryKeys } from '../../api/queries.ts';

export interface CalendarActions {
  add(request: CalendarEventCreate): Promise<CalendarEventResult>;
  remove(eventId: number): Promise<CalendarEventResult>;
  undo(actionId: number): Promise<void>;
}

export function useCalendarActions(): CalendarActions {
  const queryClient = useQueryClient();
  return useMemo(() => {
    const settle = () => {
      void queryClient.invalidateQueries({ queryKey: ['calendar'] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.agent }); // 기록 탭
    };
    const run = async <T>(p: Promise<T>): Promise<T> => {
      try {
        return await p;
      } finally {
        settle();
      }
    };
    return {
      add: (request) => run(api.addCalendarEvent(request)),
      remove: (eventId) => run(api.removeCalendarEvent(eventId)),
      undo: async (actionId) => {
        await run(api.undoAction(actionId));
      },
    };
  }, [queryClient]);
}
