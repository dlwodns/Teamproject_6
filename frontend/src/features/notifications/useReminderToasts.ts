// 🔔 알림 목록을 1분마다 다시 받고, 처음 받은 뒤 새로 온 리마인더 알림은 흰 카드 토스트로 띄운다(자동으로 닫히지 않음, components.md 4.5).
// 토스트를 닫아도 알림 센터에는 남는다. [열기]는 줄을 누른 것과 같다(읽음 + 에이전트 화면의 그 항목).
import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { api } from '../../api/client.ts';
import type { AppNotification, ReminderItem } from '../../api/contract.ts';
import { queryKeys, shouldRetry, withAvailability } from '../../api/queries.ts';
import { REMINDER_REFRESH_MS } from '../../api/reminders.ts';
import { useToast } from '../../ui/index.ts';
import { secondLine } from '../reminders/reminderModel.ts';
import { newReminderNotifications } from './notificationModel.ts';

export function useNotificationFeed() {
  return withAvailability(
    useQuery({
      queryKey: queryKeys.notifications,
      queryFn: ({ signal }) => api.getNotifications(signal),
      refetchInterval: REMINDER_REFRESH_MS,
      retry: shouldRetry,
    }),
  );
}

export function useReminderToasts(
  list: AppNotification[] | undefined,
  byKey: ReadonlyMap<string, ReminderItem>,
  onOpen: (n: AppNotification) => void,
) {
  const toast = useToast();
  const seen = useRef<Set<number> | null>(null);
  const openRef = useRef(onOpen);
  openRef.current = onOpen;
  const keyRef = useRef(byKey);
  keyRef.current = byKey;

  useEffect(() => {
    if (!list) return;
    for (const n of newReminderNotifications(seen.current, list)) {
      const item = n.reminderKey ? keyRef.current.get(n.reminderKey) : undefined;
      const id = `reminder-${n.id}`;
      toast.show({
        id,
        kind: 'reminder',
        title: item?.title ?? n.title,
        description: item ? secondLine(item) : (n.body ?? undefined),
        actionLabel: '열기',
        onAction: () => {
          toast.close(id);
          openRef.current(n);
        },
      });
    }
    seen.current = new Set(list.map((n) => n.id));
  }, [list, toast]);
}
