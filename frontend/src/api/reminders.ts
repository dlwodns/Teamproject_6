// 리마인더 · 브리핑 · 알림 모두 읽음의 Query 훅 (FE-16 · BE-12 계약). queries.ts와 같은 규칙이다.
// 키는 에이전트 키(['agent', …]) 아래에 둔다. 업무 상태가 바뀌면 useTaskActions가 ['agent']를 다시 부르므로
// 리마인더 목록 · 브리핑도 따로 챙기지 않아도 함께 새로 고쳐진다.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client.ts';
import type { BriefingKind, DismissReason, ReminderType } from './contract.ts';
import { queryKeys, shouldRetry, withAvailability } from './queries.ts';

export const reminderKeys = {
  /** 리마인더 전체 목록(묶음별 건수 · 패널 리마인더 탭 · 🔔 줄이 같은 캐시를 나눠 쓴다) */
  list: ['agent', 'reminders'] as const,
  briefing: (kind: BriefingKind, date: string) => ['agent', 'briefing', kind, date] as const,
};

/** 1분마다 다시 묻는다(엔진이 1분마다 항목을 다시 계산한다, 명세 7.3절) */
export const REMINDER_REFRESH_MS = 60_000;

export function useRemindersQuery() {
  return withAvailability(
    useQuery({
      queryKey: reminderKeys.list,
      queryFn: ({ signal }) => api.getReminders('all', signal),
      refetchInterval: REMINDER_REFRESH_MS,
      retry: shouldRetry,
    }),
  );
}

export function useBriefingQuery(kind: BriefingKind, date: string) {
  return withAvailability(
    useQuery({ queryKey: reminderKeys.briefing(kind, date), queryFn: ({ signal }) => api.getBriefing(kind, date, signal), retry: shouldRetry }),
  );
}

/** 숨김 · 적용 · 유형 알림 끄기. 끝나면 목록 · 원자료 · 알림을 다시 부른다(적용은 업무 상태 · 기한을 바꾼다) */
export function useReminderMutations() {
  const client = useQueryClient();
  const settle = () => {
    void client.invalidateQueries({ queryKey: queryKeys.agent });
    void client.invalidateQueries({ queryKey: queryKeys.dashboard });
    void client.invalidateQueries({ queryKey: queryKeys.notifications });
  };
  const dismiss = useMutation({
    mutationFn: ({ key, reason }: { key: string; reason: DismissReason }) => api.dismissReminder(key, reason),
    onSettled: settle,
  });
  const apply = useMutation({ mutationFn: (key: string) => api.applyReminder(key), onSettled: settle });
  const typeNotify = useMutation({
    mutationFn: ({ type, notify }: { type: ReminderType; notify: boolean }) => api.setReminderTypeNotify(type, notify),
    onSettled: () => void client.invalidateQueries({ queryKey: reminderKeys.list }),
  });
  return { dismiss, apply, typeNotify };
}

export function useReadAllNotifications() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.readAllNotifications(),
    onSettled: () => void client.invalidateQueries({ queryKey: queryKeys.notifications }),
  });
}
