// 리마인더 버튼을 실제로 부른다 (FE-16). 에이전트 화면 상세 · 🔔 팝업 · 패널 리마인더 탭이 같은 훅을 쓴다.
// - 완료 · 미루기 · 내 일 아님(업무): useTaskActions(모든 화면이 같은 함수, components.md 5.1) + via 'reminder:<유형>'
// - 적용 · 숨김 · 유형 알림 끄기: api(useReminderMutations)
// - 초안 · 그날 업무: 기존 에이전트 명령 경로(부르는 쪽이 onCommand로 받는다)
// - 메일 열기: 받은 메일이면 그 메일, 답을 기다리는 보낸 메일이면 응답 대기 메일함
// 결과는 토스트 한 줄 + [실행 취소](되돌릴 기록이 있을 때). 실패는 오류 토스트.
import { useCallback, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import type { DismissReason, ReminderItem } from '../../api/contract.ts';
import { useDashboardQuery } from '../../api/queries.ts';
import { useReminderMutations } from '../../api/reminders.ts';
import type { MailId, TaskId } from '../../api/types.ts';
import { useToast } from '../../ui/index.ts';
import { useOpenMail } from '../tasks/useOpenMail.ts';
import { useTaskActions } from '../tasks/useTaskActions.ts';
import { reminderResultText, type MailTarget, type MenuKind, type PlanContext, type ReminderPlan } from './reminderModel.ts';

export interface CommandRequest {
  text: string;
  selectedMailIds?: MailId[];
  taskIds?: TaskId[];
  reminderKey?: string;
}

export interface ReminderRunner {
  ctx: PlanContext;
  /** 실행 중인 항목 키들(그 항목 버튼만 잠근다. 다른 항목은 그동안에도 누를 수 있다) */
  pending: ReadonlySet<string>;
  run(item: ReminderItem, plan: ReminderPlan, opts?: { untilMs?: number; taskId?: TaskId }): Promise<void>;
  runMenu(item: ReminderItem, kind: MenuKind): Promise<void>;
}

export function useReminderRunner(onCommand: (req: CommandRequest) => void): ReminderRunner {
  const dashboard = useDashboardQuery();
  const actions = useTaskActions();
  const { dismiss, apply, typeNotify } = useReminderMutations();
  const toast = useToast();
  const openMail = useOpenMail('agent');
  const navigate = useNavigate();
  // 잠금은 항목마다. 화면 다시 그리기를 기다리지 않게 ref로 먼저 막고(같은 순간 두 번 누름), 그리기용 상태는 따로 둔다
  const inflight = useRef(new Set<string>());
  const [pending, setPending] = useState<ReadonlySet<string>>(() => new Set());

  const ctx = useMemo<PlanContext>(() => {
    const received = new Set(dashboard.data?.mails.map((m) => m.id) ?? []);
    const waiting = new Set(dashboard.data?.awaiting?.map((a) => a.mailId) ?? []);
    return { mailTarget: (id: MailId): MailTarget => (received.has(id) ? 'mail' : waiting.has(id) ? 'waiting' : null) };
  }, [dashboard.data]);

  /** 결과 토스트. 되돌릴 기록이 있으면 [실행 취소] */
  const done = useCallback(
    (text: string, actionId: number | null) => {
      const id = `reminder-result-${Date.now()}`;
      if (actionId === null) {
        toast.show({ id, kind: 'info', title: text });
        return;
      }
      toast.show({
        id,
        kind: 'undo',
        title: text,
        actionLabel: '실행 취소',
        onAction: () => {
          toast.close(id);
          void actions.undo(actionId, { source: 'button', toast: false }).then(
            () => toast.show({ kind: 'info', title: '되돌렸어요' }),
            () => toast.show({ kind: 'error', title: '되돌리지 못했어요' }),
          );
        },
      });
    },
    [toast, actions],
  );

  const guard = useCallback(
    async (key: string, work: () => Promise<void>) => {
      if (inflight.current.has(key)) return;
      inflight.current.add(key);
      setPending(new Set(inflight.current));
      try {
        await work();
      } catch {
        toast.show({ kind: 'error', title: '처리하지 못했어요. 다시 눌러 주세요' });
      } finally {
        inflight.current.delete(key);
        setPending(new Set(inflight.current));
      }
    },
    [toast],
  );

  const run = useCallback<ReminderRunner['run']>(
    async (item, plan, opts = {}) => {
      const via = `reminder:${item.type}`;
      const taskOpts = { source: 'button' as const, toast: false, via };
      switch (plan.type) {
        case 'command':
          onCommand({
            text: plan.text,
            ...(plan.selectedMailIds ? { selectedMailIds: plan.selectedMailIds } : {}),
            ...(item.taskIds.length ? { taskIds: item.taskIds } : {}),
            reminderKey: item.key,
          });
          return;
        case 'open_mail':
          openMail(plan.mailId);
          return;
        case 'open_waiting':
          void navigate('/mail/waiting', { state: { from: 'agent' } });
          return;
        case 'status':
          return guard(item.key, async () => {
            const r = plan.status === 'done' ? await actions.complete(plan.taskIds, taskOpts) : await actions.exclude(plan.taskIds, taskOpts);
            done(reminderResultText(plan.status, item), r.actionId);
          });
        case 'snooze': {
          const until = opts.untilMs;
          const taskId = opts.taskId ?? plan.taskIds[0];
          if (until === undefined || taskId === undefined) return;
          return guard(item.key, async () => {
            const r = await actions.snooze([taskId], until, taskOpts);
            done(reminderResultText('snoozed', item, until), r.actionId);
          });
        }
        case 'apply':
          return guard(item.key, async () => {
            const r = await apply.mutateAsync(item.key);
            done(reminderResultText('applied', item), r.actionId);
          });
        case 'dismiss':
          return guard(item.key, async () => {
            const r = await dismiss.mutateAsync({ key: item.key, reason: plan.reason });
            done(reminderResultText(plan.reason, item), r.actionId);
          });
      }
    },
    [onCommand, openMail, navigate, guard, actions, apply, dismiss, done],
  );

  const runMenu = useCallback<ReminderRunner['runMenu']>(
    async (item, kind) => {
      if (kind === 'not_mine' || kind === 'wrong_signal') {
        const reason: DismissReason = kind;
        return run(item, { type: 'dismiss', reason });
      }
      const notify = kind === 'unmute';
      return guard(item.key, async () => {
        await typeNotify.mutateAsync({ type: item.type, notify });
        const id = `reminder-mute-${item.type}`;
        toast.show({
          id,
          kind: notify ? 'info' : 'undo',
          title: reminderResultText(notify ? 'unmuted' : 'muted', item),
          ...(notify
            ? {}
            : {
                actionLabel: '실행 취소',
                onAction: () => {
                  toast.close(id);
                  void typeNotify.mutateAsync({ type: item.type, notify: true }).then(
                    () => toast.show({ kind: 'info', title: reminderResultText('unmuted', item) }),
                    () => toast.show({ kind: 'error', title: '되돌리지 못했어요' }),
                  );
                },
              }),
        });
      });
    },
    [run, guard, typeNotify, toast],
  );

  return { ctx, pending, run, runMenu };
}
