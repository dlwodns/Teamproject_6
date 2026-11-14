// 메일 화면 S1 (components.md 4.3 · wireframe 13-7 · 13-5).
// 세 칸: 메일함(220px, Ctrl+B · ⌘B · [▥]로 열고 닫기) · 목록(380px) · 읽기 또는 답장 쓰기. 1024px 미만은 위아래로 쌓인다.
//
// 주소(components.md 4.1 · features/mail/routes.ts)
//   #/mail/<box>/<mailId>            메일을 고르면 새 항목을 쌓는다(뒤로 가기 · Alt+← 대상)
//   ?reply=1 · ?reply=1&draft=…      답장 쓰기(에이전트 초안은 draft로 내용 칸을 채운다). 열고 닫기는 같은 항목을 바꾼다(replace)
//   state { from: 'dashboard' }      맨 위 [← 대시보드](navigate(-1), Alt ←)
//
// 답장을 보낸 뒤: 남은 업무가 없으면 '답장을 보냈어요', '오늘 다시 보지 않음' 시각 전이면 바로 완료, 그 밖에는 완료 확인 시트.
import { useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router';
import { queryKeys, useDashboardQuery, usePatchSettings, useSettingsQuery } from '../../api/queries.ts';
import type { DashboardSource, Mail, Task, TaskId } from '../../api/types.ts';
import { useAppOutlet } from '../../app/outlet.ts';
import { CompleteSheet } from '../../features/mail/CompleteSheet.tsx';
import { Compose } from '../../features/mail/Compose.tsx';
import { MailboxNav } from '../../features/mail/MailboxNav.tsx';
import { MailList, type ListState } from '../../features/mail/MailList.tsx';
import {
  accountsOf,
  isOpenTask,
  mailboxSections,
  mailboxShortcutLabel,
  mailContext,
  resolveBox,
  byUrgency,
} from '../../features/mail/mailboxes.ts';
import { ReadingPane } from '../../features/mail/ReadingPane.tsx';
import { dataNowMs, decideAfterSend, nextRemindAtMs } from '../../features/mail/replyConfirm.ts';
import { mailPath, parseMailId, readComposeParams, readFrom } from '../../features/mail/routes.ts';
import { useTaskActions } from '../../features/tasks/useTaskActions.ts';
import { formatKstShort } from '../../lib/snooze.ts';
import { Button, Inbox, StateRow, useToast } from '../../ui/index.ts';
import styles from './MailPage.module.css';

const MAILBOX_ID = 'mail-mailbox';
const shortcutLabel = mailboxShortcutLabel(typeof navigator === 'undefined' ? '' : navigator.platform);

interface SheetState {
  key: number;
  open: boolean;
  tasks: Task[];
  busy: boolean;
}

export function MailPage() {
  const params = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const { mailboxOpen, toggleMailbox } = useAppOutlet();
  const queryClient = useQueryClient();
  const dashboard = useDashboardQuery();
  const settings = useSettingsQuery();
  const patchSettings = usePatchSettings();
  const actions = useTaskActions();
  const toast = useToast();
  const [sheet, setSheet] = useState<SheetState>({ key: 0, open: false, tasks: [], busy: false });

  const source = dashboard.data;
  const ctx = useMemo(() => (source ? mailContext(source) : null), [source]);
  const sections = useMemo(() => (source && ctx ? mailboxSections(source, ctx) : null), [source, ctx]);
  const box = useMemo(() => (source && ctx ? resolveBox(source, params.box, ctx) : null), [source, ctx, params.box]);
  const boxSlug = box?.slug ?? params.box ?? 'inbox';
  const mailId = parseMailId(params.mailId);
  const mail = mailId !== null ? source?.mails.find((m) => m.id === mailId) : undefined;
  const compose = readComposeParams(search);
  const composing = compose.reply && mail !== undefined;
  const from = readFrom(location.state);

  /** 데이터 기준 지금(모의 모드는 시연 날짜 시계) */
  const now = () => (source ? dataNowMs(source.asOfMs, dashboard.dataUpdatedAt, Date.now()) : Date.now());

  const listState: ListState =
    dashboard.isError && !source
      ? { kind: 'error', onRetry: () => void dashboard.refetch() }
      : !source || !ctx || !box
        ? { kind: 'loading' }
        : box.kind === 'waiting'
          ? { kind: 'waiting', awaiting: source.awaiting ?? [] }
          : { kind: 'mails', mails: box.mails, ctx };

  const openMail = (m: Mail) => {
    if (m.id === mailId && !compose.reply) return;
    navigate(mailPath(boxSlug, m.id));
  };

  // 답장 쓰기 열고 닫기: 같은 주소 항목을 바꾼다(넘어온 화면 state는 그대로 둔다)
  const setComposing = (open: boolean) =>
    navigate({ pathname: location.pathname, search: open ? '?reply=1' : '' }, { replace: true, state: location.state });

  const afterSent = (sent: Mail) => {
    setComposing(false);
    // 방금 바뀐 업무 상태까지 보려고 캐시에서 다시 읽는다
    const latest = queryClient.getQueryData<DashboardSource>(queryKeys.dashboard) ?? source;
    const open = (latest?.tasks ?? []).filter((t) => t.mailId === sent.id && isOpenTask(t)).sort(byUrgency(latest?.asOfMs ?? 0));
    const decision = decideAfterSend(
      open.map((t) => t.id),
      settings.data?.replyConfirmSkipUntilMs,
      now(),
    );
    if (decision.kind === 'sent-only') {
      toast.show({ kind: 'info', title: '답장을 보냈어요' });
    } else if (decision.kind === 'auto-complete') {
      // D48 reply_auto: '오늘 다시 보지 않음'을 고른 뒤라 묻지 않고 완료한다(되돌리기는 완료 토스트 · 아침 알림)
      toast.show({ kind: 'info', title: '답장을 보냈어요', description: `${formatKstShort(decision.untilMs)}까지 확인 없이 완료` });
      void actions.complete(decision.taskIds, { source: 'sheet' }).catch(() => toast.show({ kind: 'error', title: '바꾸지 못함' }));
    } else {
      setSheet((s) => ({ key: s.key + 1, open: true, tasks: open, busy: false }));
    }
  };

  const closeSheet = () => setSheet((s) => ({ ...s, open: false, busy: false }));

  const sheetNo = () => {
    if (!sheet.open) return;
    closeSheet();
    toast.show({ kind: 'info', title: '리마인드 유지' });
  };

  const sheetYes = async (taskIds: TaskId[], skipToday: boolean) => {
    if (sheet.busy) return;
    if (taskIds.length === 0) {
      sheetNo();
      return;
    }
    setSheet((s) => ({ ...s, busy: true }));
    try {
      await actions.complete(taskIds, { source: 'sheet' });
    } catch {
      closeSheet();
      toast.show({ kind: 'error', title: '바꾸지 못함' });
      return;
    }
    if (skipToday && settings.data) {
      const until = nextRemindAtMs(now(), settings.data.remindTime);
      patchSettings.mutate({ replyConfirmSkipUntilMs: until }, { onError: () => toast.show({ kind: 'error', title: '오늘 다시 보지 않음을 저장하지 못함' }) });
    }
    closeSheet();
  };

  const me = (() => {
    const to = mail?.to;
    return to && to.length === 1 ? (to[0] ?? null) : null; // 받는 사람이 나 하나일 때만 내 이름으로 쓴다
  })();

  return (
    <div className={styles.page}>
      {from && (
        <div className={styles.top}>
          <Button variant="ghost" size="sm" aria-keyshortcuts="Alt+ArrowLeft" onClick={() => void navigate(-1)}>
            ← {from.label}
          </Button>
          <kbd className={styles.kbd} aria-hidden="true">
            Alt ←
          </kbd>
        </div>
      )}
      <div className={styles.grid} data-mailbox={mailboxOpen ? 'open' : 'closed'}>
        {mailboxOpen && <MailboxNav id={MAILBOX_ID} sections={sections} selected={boxSlug} />}
        <MailList
          boxLabel={box?.label ?? '받은편지함'}
          state={listState}
          selectedId={mailId}
          onOpen={openMail}
          mailboxOpen={mailboxOpen}
          onToggleMailbox={toggleMailbox}
          mailboxId={MAILBOX_ID}
          shortcutLabel={shortcutLabel}
        />
        <div className={styles.view}>
          {!source || !ctx ? (
            dashboard.isError ? null : <StateRow state="loading" />
          ) : mailId === null ? (
            <div className={styles.empty}>
              <Inbox size={32} strokeWidth={1.5} aria-hidden="true" />
              <p className={styles.emptyTitle}>메일을 고르면 여기에 보여요</p>
              <p className={styles.quiet}>목록에서 ↑↓로 옮기고 Enter로 열어요</p>
            </div>
          ) : !mail ? (
            <p className={styles.quiet}>메일을 찾을 수 없음</p>
          ) : composing ? (
            <Compose
              key={mail.id}
              mail={mail}
              ctx={ctx}
              accounts={accountsOf(source.mails)}
              templates={settings.data?.templates}
              me={me}
              initialContent={compose.draft}
              demo={source.origin.kind === 'mock'}
              onClose={() => setComposing(false)}
              onSent={() => afterSent(mail)}
            />
          ) : (
            <ReadingPane key={mail.id} mail={mail} ctx={ctx} now={now} onReply={() => setComposing(true)} />
          )}
        </div>
      </div>
      <CompleteSheet
        key={sheet.key}
        open={sheet.open}
        tasks={sheet.tasks}
        asOfMs={source?.asOfMs ?? 0}
        canSkip={settings.data?.replyConfirmSkipUntilMs !== undefined}
        busy={sheet.busy}
        onYes={(ids, skip) => void sheetYes(ids, skip)}
        onNo={sheetNo}
      />
    </div>
  );
}
