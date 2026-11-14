// 알림 센터 🔔 (FE-10 · FE-16 · 명세 6절 · UX-D19). FE-10은 이재운 님께 넘겨받아 문규남이 만들었다(리뷰 이재운).
// 팝업(400px)은 "지금 새로 온 것"만 보이고, 전체는 에이전트 화면 리마인더 메뉴가 맡는다(GitHub 🔔 → 알림 페이지와 같은 나눔).
// - 🔔 숫자 = 읽지 않은 리마인더 알림 수(10 이상 9+). 숫자는 버튼 이름으로도 읽힌다
// - 탭 [리마인더 N | 알림 N]: N은 읽지 않은 수. 알림 탭은 새 업무 · 에이전트 작업 완료 같은 리마인더가 아닌 것
// - 리마인더 탭: 건수가 있는 묶음 칩(넘치면 마지막 칩이 › 전체 보기) · 줄 최대 5개 · 맨 아래 '리마인더 전체 보기 (N) ›'
// - 줄을 누르면 읽음으로 바꾸고 에이전트 화면에서 그 항목을 연다. 줄 버튼은 최대 2개(상세와 같은 동작)
// - 리마인더 토스트는 흰 카드로 자동으로 사라지지 않는다(처음 받은 목록 뒤에 새로 온 것만, useReminderToasts)
// - 실제 서버 모드에서 알림 API가 없으면(NotAvailableError) 숫자 · 리마인더 탭을 숨기고 알림 탭만 둔다.
//   리마인더 API(BE-12)만 없을 때도 같다: 리마인더 줄이 열 에이전트 화면 항목이 없으므로 서버 알림을 모두 알림 탭에 둔다
// - 줄 버튼으로 처리하면 그 알림도 읽음으로 바꾼다(처리한 줄이 안 읽음으로 남아 숫자를 붙들지 않게)
// - [모두 읽음]은 한꺼번에 읽음 요청이 서버에 없으면 하나씩 읽음으로 바꾼다
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import type { AppNotification, ReminderItem } from '../../api/contract.ts';
import { usePatchNotification } from '../../api/queries.ts';
import { useRemindersQuery } from '../../api/reminders.ts';
import { agentSession } from '../agent/agentSession.ts';
import { agentViewer } from '../agent/agentViewer.ts';
import { formatKstShort } from '../../lib/snooze.ts';
import { reminderPath } from '../agent/agentRoutes.ts';
import { Bell, Button, ChevronRight, CountBadge, IconButton, Popover, Tabs, VisuallyHidden, cx } from '../../ui/index.ts';
import { ReminderActions } from '../reminders/ReminderActions.tsx';
import { GROUP_LABEL, secondLine, visibleItems } from '../reminders/reminderModel.ts';
import { useReminderRunner, type CommandRequest, type ReminderRunner } from '../reminders/useReminderRunner.ts';
import { localNotices, useLocalNotices, type LocalNotice } from './localNotices.ts';
import styles from './NotificationBell.module.css';
import { bellLabel, groupChips, notificationTarget, popoverRows, splitNotifications, unreadReminderCount, type ChipFilter } from './notificationModel.ts';
import { useNotificationFeed, useReadAllNotifications, useReminderToasts } from './useReminderToasts.ts';

type Tab = 'reminders' | 'others';

export function NotificationBell() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>('reminders');
  const [filter, setFilter] = useState<ChipFilter>('all');
  const feed = useNotificationFeed();
  const reminders = useRemindersQuery();
  const local = useLocalNotices();
  const patch = usePatchNotification();
  const readAll = useReadAllNotifications();

  const serverOk = Boolean(feed.data) && !feed.isNotAvailable;
  // 리마인더 탭 · 🔔 숫자는 알림 API와 리마인더 API가 모두 있을 때만
  const remindersOn = serverOk && !reminders.isNotAvailable;
  const list = useMemo(() => feed.data ?? [], [feed.data]);
  const { reminders: remRows, others } = useMemo(() => splitNotifications(list, remindersOn), [list, remindersOn]);
  const byKey = useMemo(() => new Map((reminders.data?.items ?? []).map((i) => [i.key, i])), [reminders.data]);
  const unread = serverOk ? unreadReminderCount(list, remindersOn) : 0;
  const unreadOthers = others.filter((n) => n.readAtMs === null).length + local.filter((n) => !n.read).length;
  const total = reminders.data ? visibleItems(reminders.data.items).length : null;

  const goto = (path: string) => {
    setOpen(false);
    void navigate(path);
  };
  const markRead = (n: AppNotification) => {
    if (n.readAtMs === null) patch.mutate({ id: n.id, patch: { read: true } });
  };
  const openReminder = (n: AppNotification) => {
    markRead(n);
    const t = notificationTarget(n);
    goto(t.kind === 'reminder' ? reminderPath('all', t.key) : t.kind === 'briefing' ? '/agent/briefing' : reminderPath());
  };

  // 줄 버튼의 초안 · 그날 업무는 에이전트 명령으로 보내고 대화 메뉴로 옮긴다(결과가 바로 보이게)
  const runCommand = (req: CommandRequest) => {
    const { text, ...opts } = req;
    if (agentSession.submit(text, { selectedMailIds: [], ...opts })) goto('/agent/chat');
  };
  const runner = useReminderRunner(runCommand);
  useReminderToasts(remindersOn ? feed.data : undefined, byKey, openReminder);

  const { chips, overflow } = groupChips(remRows);
  const shownFilter = filter !== 'all' && !chips.some((c) => c.group === filter) ? 'all' : filter;
  const { rows } = popoverRows(remRows, shownFilter);
  const now = () => reminders.data?.asOfMs ?? Date.now();

  const reminderTab = (
    <div className={styles.tab}>
      {chips.length > 0 && (
        <div className={styles.chips} role="group" aria-label="묶음으로 거르기">
          <button type="button" className={styles.chip} aria-pressed={shownFilter === 'all'} onClick={() => setFilter('all')}>
            전체
          </button>
          {chips.map((c) => (
            <button key={c.group} type="button" className={styles.chip} aria-pressed={shownFilter === c.group} onClick={() => setFilter(c.group)}>
              {GROUP_LABEL[c.group]}
              <span className={styles.chipCount}>{c.count}</span>
            </button>
          ))}
          {overflow && (
            <button type="button" className={styles.chip} onClick={() => goto(reminderPath())} aria-label="리마인더 전체 보기">
              <ChevronRight size={16} aria-hidden="true" />
            </button>
          )}
        </div>
      )}
      {rows.length === 0 ? (
        <div className={styles.empty}>
          <p className={styles.emptyTitle}>새로 알릴 리마인더가 없어요</p>
          <p className={styles.emptyText}>기한 · 답 기다림 · 약속을 알릴 때가 되면 여기에 먼저 보여요.</p>
        </div>
      ) : (
        <ul className={styles.rows} aria-label="리마인더 알림">
          {rows.map((n) => (
            <ReminderRow
              key={n.id}
              n={n}
              item={n.reminderKey ? byKey.get(n.reminderKey) : undefined}
              onOpen={() => openReminder(n)}
              onAct={() => markRead(n)}
              runner={runner}
              now={now}
            />
          ))}
        </ul>
      )}
      <button type="button" className={styles.footer} onClick={() => goto(reminderPath())}>
        {total === null ? '리마인더 전체 보기' : `리마인더 전체 보기 (${total})`}
        <ChevronRight size={16} aria-hidden="true" />
      </button>
    </div>
  );

  const otherRows: { key: string; title: string; body: string | null; atMs: number; unread: boolean; onOpen: () => void }[] = [
    ...others.map((n) => ({
      key: `s${n.id}`,
      title: n.title,
      body: n.body,
      atMs: n.createdAtMs,
      unread: n.readAtMs === null,
      onOpen: () => {
        markRead(n);
        goto(n.kind === 'new_tasks' ? '/mail/tasks' : '/dashboard');
      },
    })),
    ...local.map((n: LocalNotice) => ({
      key: n.id,
      title: n.title,
      body: n.body,
      atMs: n.atMs,
      unread: !n.read,
      onOpen: () => {
        localNotices.markRead(n.id);
        if (n.runId !== null) agentViewer.open(n.runId);
        goto('/agent/chat');
      },
    })),
  ].sort((a, b) => b.atMs - a.atMs);

  const othersTab = (
    <div className={styles.tab}>
      {otherRows.length === 0 ? (
        <div className={styles.empty}>
          <p className={styles.emptyTitle}>새 알림이 없어요</p>
          <p className={styles.emptyText}>새 업무가 들어오거나 에이전트 작업이 끝나면 여기에 남아요.</p>
        </div>
      ) : (
        <ul className={styles.rows} aria-label="알림">
          {otherRows.slice(0, 8).map((r) => (
            <li key={r.key} className={styles.row}>
              <button type="button" className={styles.open} onClick={r.onOpen}>
                <span className={cx(styles.dot, !r.unread && styles.dotRead)} aria-hidden="true" />
                <span className={styles.text}>
                  <span className={styles.title}>
                    {r.unread && <VisuallyHidden>읽지 않음 · </VisuallyHidden>}
                    {r.title}
                  </span>
                  <span className={styles.sub}>{[r.body, formatKstShort(r.atMs)].filter(Boolean).join(' · ')}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );

  const anyUnread = unread > 0 || unreadOthers > 0;
  const tabs = [
    ...(remindersOn ? [{ value: 'reminders' as const, label: '리마인더', count: unread || undefined, content: reminderTab }] : []),
    { value: 'others' as const, label: '알림', count: unreadOthers || undefined, content: othersTab },
  ];

  return (
    <Popover
      title="알림"
      open={open}
      onOpenChange={setOpen}
      headerExtra={
        <Button
          size="sm"
          variant="ghost"
          aria-disabled={!anyUnread || undefined}
          onClick={() => {
            if (!anyUnread) return;
            localNotices.markAllRead();
            if (serverOk) readAll.mutate(list);
          }}
        >
          모두 읽음
        </Button>
      }
      trigger={
        <IconButton
          size="lg"
          label={bellLabel(unread)}
          tooltip="알림 센터"
          icon={
            <>
              <Bell size={20} aria-hidden="true" />
              <CountBadge count={unread} placement="corner" />
            </>
          }
        />
      }
    >
      <Tabs<Tab> label="알림 종류" items={tabs} value={remindersOn ? tab : 'others'} onValueChange={setTab} className={styles.tabs} />
    </Popover>
  );
}

interface RowProps {
  n: AppNotification;
  item: ReminderItem | undefined;
  onOpen: () => void;
  /** 줄 버튼을 눌렀다(알림을 읽음으로) */
  onAct: () => void;
  runner: ReminderRunner;
  now: () => number;
}

function ReminderRow({ n, item, onOpen, onAct, runner, now }: RowProps) {
  const unread = n.readAtMs === null;
  // 줄 버튼은 같은 실행 길을 타되, 누르면 이 알림을 읽음으로 바꾼다
  const rowRunner = useMemo<ReminderRunner>(
    () => ({
      ...runner,
      run: (it, plan, opts) => {
        onAct();
        return runner.run(it, plan, opts);
      },
    }),
    [runner, onAct],
  );
  return (
    <li className={styles.row}>
      <button type="button" className={styles.open} onClick={onOpen}>
        <span className={cx(styles.dot, !unread && styles.dotRead)} aria-hidden="true" />
        <span className={styles.text}>
          <span className={styles.title}>
            {unread && <VisuallyHidden>읽지 않음 · </VisuallyHidden>}
            {item?.title ?? n.title}
          </span>
          <span className={styles.sub}>{item ? secondLine(item) : (n.body ?? '')}</span>
        </span>
      </button>
      {item && <ReminderActions item={item} runner={rowRunner} now={now} limit={2} withMenu={false} className={styles.rowActions} />}
    </li>
  );
}
