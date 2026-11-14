// 메일 읽음 · 고정 바꾸기(FE-5d). 업무 상태(useTaskActions)와 같은 방식: 화면 먼저 바꾸기 → 서버 → 실패 시 그 메일만 되돌리기 → 끝나면 서버 값으로 다시 불러오기.
// 서버에 요청이 아직 없으면(NotAvailableError) 이 화면이 열려 있는 동안 읽음 · 고정 동작을 숨긴다(없는 기능을 있는 척하지 않는다).
import { useQueryClient } from '@tanstack/react-query';
import { useMemo, useRef, useState } from 'react';
import { api } from '../../api/client.ts';
import type { MailPatch } from '../../api/contract.ts';
import { NotAvailableError } from '../../api/errors.ts';
import { queryKeys } from '../../api/queries.ts';
import type { DashboardSource, MailId } from '../../api/types.ts';
import { restoreMails, withMailPatch, withMailsReplaced } from './listView.ts';

export interface MailActions {
  /** 서버가 읽음 · 고정 요청을 받는가(한 번 NotAvailableError를 받으면 거짓) */
  available: boolean;
  patch(ids: readonly MailId[], patch: MailPatch): Promise<void>;
}

export function useMailActions(nowMs: () => number): MailActions {
  const queryClient = useQueryClient();
  const [available, setAvailable] = useState(true);
  const clock = useRef(nowMs);
  clock.current = nowMs;

  const patch = useMemo(
    () =>
      async function patch(ids: readonly MailId[], change: MailPatch): Promise<void> {
        const unique = [...new Set(ids)];
        if (unique.length === 0) return;
        await queryClient.cancelQueries({ queryKey: queryKeys.dashboard });
        const before = queryClient.getQueryData<DashboardSource>(queryKeys.dashboard);
        queryClient.setQueryData<DashboardSource>(queryKeys.dashboard, (cur) => cur && withMailPatch(cur, unique, change, clock.current()));
        try {
          const updated = await Promise.all(unique.map((id) => api.patchMail(id, change)));
          queryClient.setQueryData<DashboardSource>(queryKeys.dashboard, (cur) => cur && withMailsReplaced(cur, updated));
        } catch (e) {
          if (before) queryClient.setQueryData<DashboardSource>(queryKeys.dashboard, (cur) => cur && restoreMails(cur, before, unique));
          if (e instanceof NotAvailableError) setAvailable(false);
          throw e;
        } finally {
          // 성공해도 실패해도 서버 값으로 맞춘다(#59 리뷰): 위 cancelQueries가 취소한 다시 불러오기를 되살리고,
          // 여러 통 중 일부만 실패해 화면을 되돌렸어도 서버에서 이미 바뀐 메일은 바뀐 대로 보이게
          void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
        }
      },
    [queryClient],
  );

  return useMemo(() => ({ available, patch }), [available, patch]);
}
