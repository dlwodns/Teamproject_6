// 메일 화면 S1 (components.md 4.3 · wireframe 13-7 · 13-5).
// 세 칸: 메일함(220px, Ctrl+B · ⌘B · [▥]로 열고 닫기) · 목록(380px) · 읽기 또는 답장 쓰기. 1024px 미만은 위아래로 쌓인다.
//
// 주소(components.md 4.1 · features/mail/routes.ts)
//   #/mail/<box>/<mailId>            메일을 고르면 새 항목을 쌓는다(뒤로 가기 · Alt+← 대상)
//   ?reply=1 · ?reply=1&draft=…      답장 쓰기(에이전트 초안은 draft로 내용 칸을 채운다). 열고 닫기는 같은 항목을 바꾼다(replace)
//   state { from: 'dashboard' }      맨 위 [← 대시보드](navigate(-1), Alt ←)
//
// 답장을 보낸 뒤: 남은 업무가 없으면 '답장을 보냈어요', '오늘 다시 보지 않음' 시각 전이면 바로 완료, 그 밖에는 완료 확인 시트.
//
// BE-7: 메일함에 보관함 · 지운 편지함(GET /api/mails/hidden), 읽기 화면 아래 [보관] · [삭제] / 숨긴 메일은 [받은 편지함으로 되돌리기].
//
// FE-5d(Outlook에서 가져온 메일 관리): 목록 묶음(고정됨 · 오늘 · 어제 …) · 줄 빠른 동작 · 읽음/안 읽음 · 고정 · 여러 통 고르기 · 단축키.
//   - 메일을 열면 읽음으로 바꾼다(Outlook 기본: 고르면 읽음). 읽음 · 고정은 서버가 칸을 보내고 요청을 받을 때만 보인다.
//   - 업무 완료가 2건 이상이면 같은 완료 확인 시트로 묻는다(D37). 여러 건은 useTaskActions의 미리보기 → 실행 길을 탄다.
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router';
import { NotAvailableError } from '../../api/errors.ts';
import { queryKeys, useAccountsQuery, useDashboardQuery, useHiddenMailsQuery, useMoveMail, usePatchSettings, useSettingsQuery } from '../../api/queries.ts';
import type { DashboardSource, Mail, MailId, Task, TaskId } from '../../api/types.ts';
import type { ComposeMode, MailFolder, MailPatch } from '../../api/contract.ts';
import { useAppOutlet } from '../../app/outlet.ts';
import { CompleteSheet } from '../../features/mail/CompleteSheet.tsx';
import { Compose } from '../../features/mail/Compose.tsx';
import {
  bulkPinTarget,
  EMPTY_SELECTION,
  flattenGroups,
  groupMails,
  isPinned,
  pruneSelection,
  selectedInOrder,
  stepMail,
  supportsPin,
  supportsRead,
  toggleSelect,
  type Selection,
} from '../../features/mail/listView.ts';
import { MailboxNav } from '../../features/mail/MailboxNav.tsx';
import { MailList, type BulkBar, type ListState, type RowActions } from '../../features/mail/MailList.tsx';
import {
  accountsOf,
  isOpenTask,
  isTaskMail,
  isUnread,
  mailboxSections,
  mailboxShortcutLabel,
  mailContext,
  resolveBox,
  byUrgency,
  tasksOf,
  type MailContext,
} from '../../features/mail/mailboxes.ts';
import { isInsideDialog, isReloadKey, mailShortcutOf } from '../../features/mail/mailShortcuts.ts';
import { ReadingPane } from '../../features/mail/ReadingPane.tsx';
import { dataNowMs, decideAfterSend, nextRemindAtMs } from '../../features/mail/replyConfirm.ts';
import { mailPath, parseMailId, readComposeParams, readFrom } from '../../features/mail/routes.ts';
import { useMailActions } from '../../features/mail/useMailActions.ts';
import { useTaskActions } from '../../features/tasks/useTaskActions.ts';
import { formatKstShort, snoozeOptions } from '../../lib/snooze.ts';
import { Button, Inbox, StateRow, useToast, type MenuItemSpec } from '../../ui/index.ts';
import styles from './MailPage.module.css';

const MAILBOX_ID = 'mail-mailbox';
const shortcutLabel = mailboxShortcutLabel(typeof navigator === 'undefined' ? '' : navigator.platform);

interface SheetState {
  key: number;
  open: boolean;
  tasks: Task[];
  busy: boolean;
  /**
   * reply = 답장을 보낸 뒤(아니오면 '리마인드 유지'), manual = 줄 · 묶음 [업무 완료](아니오면 조용히 닫음),
   * exclude = 여러 통을 고른 Delete(D37: 2건 이상 상태 변경은 확인, 아니오면 조용히 닫음)
   */
  mode: 'reply' | 'manual' | 'exclude';
}

/** 끝나지 않은 업무(업무 메일만), 급한 차례 */
const openTasksOf = (ctx: MailContext, mails: readonly Mail[]): Task[] =>
  mails.flatMap((m) => (isTaskMail(ctx, m) ? tasksOf(ctx, m).filter(isOpenTask) : [])).sort(byUrgency(ctx.asOfMs));

export function MailPage() {
  const params = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const { mailboxOpen, toggleMailbox } = useAppOutlet();
  const queryClient = useQueryClient();
  const dashboard = useDashboardQuery();
  const hiddenMails = useHiddenMailsQuery(); // BE-7 보관함 · 지운 편지함. 받지 못하면 두 메일함을 숨긴다
  const moveMail = useMoveMail();
  const mailAccounts = useAccountsQuery(); // FE-18 새 메일의 보낸 사람. 받지 못하면 서버가 첫 계정으로 보낸다
  const settings = useSettingsQuery();
  const patchSettings = usePatchSettings();
  const actions = useTaskActions();
  const toast = useToast();
  const [sheet, setSheet] = useState<SheetState>({ key: 0, open: false, tasks: [], busy: false, mode: 'reply' });
  const [selection, setSelection] = useState<Selection>(EMPTY_SELECTION);
  const [helpOpen, setHelpOpen] = useState(false);

  const source = dashboard.data;
  const hidden = hiddenMails.data;
  const ctx = useMemo(() => (source ? mailContext(source) : null), [source]);
  const sections = useMemo(() => (source && ctx ? mailboxSections(source, ctx, hidden) : null), [source, ctx, hidden]);
  // 보관함 · 지운 편지함 주소로 들어왔으면 숨긴 메일을 받을 때까지 기다린다(그사이 받은편지함으로 보이지 않게)
  const waitHidden = (params.box === 'archive' || params.box === 'deleted') && hiddenMails.isPending;
  const box = useMemo(
    () => (source && ctx && !waitHidden ? resolveBox(source, params.box, ctx, hidden) : null),
    [source, ctx, params.box, hidden, waitHidden],
  );
  const groups = useMemo(() => (box && ctx && box.kind === 'mails' ? groupMails(box.mails, ctx.asOfMs) : []), [box, ctx]);
  const order = useMemo(() => flattenGroups(groups), [groups]);
  const boxSlug = box?.slug ?? params.box ?? 'inbox';
  const mailId = parseMailId(params.mailId);
  const mail = mailId !== null ? (source?.mails.find((m) => m.id === mailId) ?? hidden?.find((m) => m.id === mailId)) : undefined;
  const mailHidden = mail !== undefined && hidden?.some((m) => m.id === mail.id) === true;
  const compose = readComposeParams(search);
  // 새 메일은 고른 메일 없이도 쓴다. 답장 · 전체 답장 · 전달은 원 메일이 있어야 한다
  const composing = compose.mode === 'new' || (compose.mode !== null && mail !== undefined);
  const from = readFrom(location.state);

  /** 데이터 기준 지금(모의 모드는 시연 날짜 시계) */
  const now = () => (source ? dataNowMs(source.asOfMs, dashboard.dataUpdatedAt, Date.now()) : Date.now());
  const mailActions = useMailActions(now);

  // 읽음 · 고정은 서버가 칸을 보낼 때(한 통이라도)만, 그리고 요청이 없다고 확인되면 숨긴다
  const canRead = mailActions.available && (source?.mails.some(supportsRead) ?? false);
  const canPin = mailActions.available && (source?.mails.some(supportsPin) ?? false);

  // 메일함을 바꾸면 고른 것을 비운다. 목록에서 빠진 메일은 고른 것에서 뺀다
  useEffect(() => setSelection(EMPTY_SELECTION), [boxSlug]);
  useEffect(() => setSelection((s) => pruneSelection(s, order.map((m) => m.id))), [order]);
  const selected = useMemo(() => selectedInOrder(selection, order), [selection, order]);

  const listState: ListState =
    dashboard.isError && !source
      ? { kind: 'error', onRetry: () => void dashboard.refetch() }
      : !source || !ctx || !box
        ? { kind: 'loading' }
        : box.kind === 'waiting'
          ? { kind: 'waiting', awaiting: source.awaiting ?? [] }
          : { kind: 'mails', groups, order, ctx };

  const openMail = (m: Mail) => {
    if (selection.ids.size > 0) setSelection(EMPTY_SELECTION); // 그냥 누르면 여러 통 고르기를 끝내고 그 메일만 연다(Outlook)
    if (m.id === mailId && !compose.mode) return;
    navigate(mailPath(boxSlug, m.id));
  };

  // 답장 쓰기 열고 닫기: 같은 주소 항목을 바꾼다(넘어온 화면 state는 그대로 둔다)
  const setComposing = (mode: ComposeMode | null) =>
    navigate(
      { pathname: location.pathname, search: mode === null ? '' : mode === 'reply' ? '?reply=1' : `?compose=${mode}` },
      { replace: true, state: location.state },
    );

  // ── 읽음 · 고정 ──

  const fail = (e: unknown) =>
    toast.show(
      e instanceof NotAvailableError ? { kind: 'info', title: '서버에서 아직 지원하지 않는 기능이에요' } : { kind: 'error', title: '바꾸지 못함' },
    );

  const patchMails = (mails: readonly Mail[], patch: MailPatch) => {
    const ids = mails.filter((m) => (patch.read === undefined || supportsRead(m)) && (patch.pinned === undefined || supportsPin(m))).map((m) => m.id);
    if (ids.length === 0) return;
    void mailActions.patch(ids, patch).catch(fail);
  };

  // ── 메일함 옮기기(BE-7): 보관 · 삭제(지운 편지함, 영구 삭제 아님) · 받은 편지함으로 되돌리기 ──

  const MOVED: Record<MailFolder, string> = { archive: '보관함으로 옮겼어요', deleteditems: '지운 편지함으로 옮겼어요', inbox: '받은 편지함으로 되돌렸어요' };
  const move = (m: Mail, folder: MailFolder) =>
    void moveMail
      .mutateAsync({ id: m.id, folder })
      .then(() => {
        if (m.id === mailId) navigate(mailPath(boxSlug), { replace: true }); // 옮긴 메일은 지금 목록에서 빠진다
        toast.show(folder === 'inbox' ? { kind: 'info', title: MOVED.inbox } : { kind: 'undo', title: MOVED[folder], onAction: () => move(m, 'inbox') });
      })
      .catch(fail);

  const moveButtons =
    mail && mail.direction === 'received' ? (
      mailHidden ? (
        <Button disabled={moveMail.isPending} onClick={() => move(mail, 'inbox')}>
          받은 편지함으로 되돌리기
        </Button>
      ) : (
        <>
          <Button disabled={moveMail.isPending} onClick={() => move(mail, 'archive')}>
            보관
          </Button>
          <Button disabled={moveMail.isPending} aria-label="삭제(지운 편지함으로 옮기기)" onClick={() => move(mail, 'deleteditems')}>
            삭제
          </Button>
        </>
      )
    ) : null;

  // 메일을 열면 읽음으로(한 번만). 열어 둔 채 '안 읽음'으로 바꾸면 다른 메일로 옮길 때까지 그대로 둔다
  const autoRead = useRef<MailId | null>(null);
  useEffect(() => {
    if (!mail || autoRead.current === mail.id) return;
    autoRead.current = mail.id;
    if (canRead && isUnread(mail)) void mailActions.patch([mail.id], { read: true }).catch(() => undefined);
  }, [mail, canRead, mailActions]);

  // ── 업무 완료 · 나중에 · 제외 ──

  // 성공 · 실패 토스트는 useTaskActions(FE-4)가 띄운다. 여기서는 실패를 삼키기만 한다(안내가 두 번 뜨지 않게)
  const ignore = () => {};

  /** 1건은 바로, 2건 이상은 완료 확인 시트로 묻는다(D37) */
  const completeTasks = (tasks: Task[]) => {
    if (tasks.length === 0) return;
    if (tasks.length === 1) {
      void actions.complete([tasks[0]!.id], { source: 'button' }).catch(ignore);
      return;
    }
    setSheet((s) => ({ key: s.key + 1, open: true, tasks, busy: false, mode: 'manual' }));
  };

  /** 업무 제외. 성공하면 되돌리기 토스트('업무 N건을 제외했어요 [실행 취소]'), 실패하면 실패 토스트를 useTaskActions(FE-4)가 띄운다.
   *  확인 시트를 거쳤으면 끝날 때까지 기다린다(실패는 다시 던져 시트를 닫게 한다) */
  const excludeTasks = async (ids: TaskId[]): Promise<void> => {
    await actions.exclude(ids, { source: 'button' });
  };

  /** 메일 한 통은 바로 제외 + 되돌리기, 여러 통을 골랐으면 확인 시트를 거친다(#59 리뷰 · D37) */
  const excludeMails = (mails: readonly Mail[]) => {
    if (!ctx) return;
    const tasks = openTasksOf(ctx, mails);
    if (tasks.length === 0) return;
    if (mails.length >= 2) {
      setSheet((s) => ({ key: s.key + 1, open: true, tasks, busy: false, mode: 'exclude' }));
      return;
    }
    void excludeTasks(tasks.map((t) => t.id)).catch(ignore);
  };

  const rowActions: RowActions = {
    canRead,
    canPin,
    complete: (m) => ctx && completeTasks(openTasksOf(ctx, [m])),
    snoozeOptions: () => snoozeOptions(now()),
    snooze: (m, untilMs) => {
      if (!ctx) return;
      const ids = openTasksOf(ctx, [m]).map((t) => t.id);
      if (ids.length > 0) void actions.snooze(ids, untilMs, { source: 'button' }).catch(ignore);
    },
    togglePin: (m) => patchMails([m], { pinned: !isPinned(m) }),
    toggleRead: (m) => patchMails([m], { read: isUnread(m) }),
  };

  // ── 여러 통 고르기 ──

  const onSelect = (id: MailId, range: boolean) => setSelection((s) => toggleSelect(s, order.map((m) => m.id), id, { range }));
  const clearSelection = () => setSelection(EMPTY_SELECTION);
  const bulkTasks = ctx ? openTasksOf(ctx, selected) : [];
  const bulk: BulkBar = {
    selected,
    openTasks: bulkTasks.length,
    pinTarget: bulkPinTarget(selected),
    canRead,
    canPin,
    selectAll: () => setSelection({ ids: new Set(order.map((m) => m.id)), anchor: selection.anchor }),
    read: (read) => patchMails(selected, { read }),
    pin: () => patchMails(selected, { pinned: bulkPinTarget(selected) }),
    complete: () => completeTasks(bulkTasks),
    clear: clearSelection,
  };

  // ── 단축키(Outlook 호환, components.md 6절) ──

  /** 단축키가 다룰 메일: 여러 통을 골랐으면 그것들, 아니면 열린 메일 */
  const targets = (): Mail[] => (selected.length > 0 ? selected : mail ? [mail] : []);

  const onShortcut = (e: KeyboardEvent) => {
    const handled = e.defaultPrevented; // 다른 곳(목록 · 메뉴)이 이미 쓴 키
    // 메일 화면에서는 Ctrl+R(새로고침)을 늘 막는다 — 답장을 쓰는 중에 눌러도 쓰던 글이 사라지지 않게(#59 리뷰)
    if (isReloadKey(e)) e.preventDefault();
    // 확인 시트 · 도움말이 열려 있거나 대화상자 안에서 누른 키는 뒤 메일에 보내지 않는다(#59 리뷰)
    if (sheet.open || helpOpen || isInsideDialog(e.target)) return;
    const action = mailShortcutOf(e);
    if (action === null || handled) return;
    const go = (fn: () => void) => {
      e.preventDefault();
      fn();
    };
    switch (action) {
      case 'reply':
        if (mail && !composing) go(() => setComposing('reply'));
        return;
      case 'read':
      case 'unread':
        if (canRead) go(() => patchMails(targets(), { read: action === 'read' }));
        return;
      case 'pin': {
        const list = targets();
        if (canPin && list.length > 0) go(() => patchMails(list, { pinned: bulkPinTarget(list) }));
        return;
      }
      case 'exclude':
        if (ctx && openTasksOf(ctx, targets()).length > 0) go(() => excludeMails(targets()));
        return;
      case 'next':
      case 'prev': {
        const next = stepMail(order, mailId, action === 'next' ? 1 : -1);
        if (next) go(() => openMail(next));
        return;
      }
      case 'help':
        go(() => setHelpOpen(true));
        return;
      case 'clear':
        if (selection.ids.size > 0) go(clearSelection);
        return;
    }
  };
  const shortcutRef = useRef(onShortcut);
  shortcutRef.current = onShortcut;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => shortcutRef.current(e);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // 답장을 쓰는 중에는 F5 · Ctrl+Shift+R · 탭 닫기도 한 번 묻는다(쓰던 답장을 잃지 않게, #59 리뷰)
  useEffect(() => {
    if (!composing) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [composing]);

  // ── 답장 뒤 완료 확인 시트 ──

  const afterSent = (sent: Mail) => {
    setComposing(null);
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
      void actions.complete(decision.taskIds, { source: 'sheet' }).catch(ignore);
    } else {
      setSheet((s) => ({ key: s.key + 1, open: true, tasks: open, busy: false, mode: 'reply' }));
    }
  };

  const closeSheet = () => setSheet((s) => ({ ...s, open: false, busy: false }));

  const sheetNo = () => {
    if (!sheet.open) return;
    closeSheet();
    if (sheet.mode === 'reply') toast.show({ kind: 'info', title: '리마인드 유지' });
  };

  const sheetYes = async (taskIds: TaskId[], skipToday: boolean) => {
    if (sheet.busy) return;
    if (taskIds.length === 0) {
      sheetNo();
      return;
    }
    setSheet((s) => ({ ...s, busy: true }));
    try {
      if (sheet.mode === 'exclude') await excludeTasks(taskIds);
      else await actions.complete(taskIds, { source: sheet.mode === 'reply' ? 'sheet' : 'button' });
    } catch {
      closeSheet(); // 실패 안내는 useTaskActions(FE-4) 토스트
      return;
    }
    if (skipToday && settings.data) {
      const until = nextRemindAtMs(now(), settings.data.remindTime);
      patchSettings.mutate({ replyConfirmSkipUntilMs: until }, { onError: () => toast.show({ kind: 'error', title: '오늘 다시 보지 않음을 저장하지 못함' }) });
    }
    if (sheet.mode !== 'reply') clearSelection();
    closeSheet();
  };

  const me = (() => {
    const to = mail?.to;
    return to && to.length === 1 ? (to[0] ?? null) : null; // 받는 사람이 나 하나일 때만 내 이름으로 쓴다
  })();

  // 읽기 화면 ⋯ 메뉴: 안 읽음으로 표시 · 고정(서버가 받을 때만)
  const mailMenu: MenuItemSpec[] = [];
  if (mail && canRead && supportsRead(mail)) {
    const unread = isUnread(mail);
    mailMenu.push({ key: 'read', label: unread ? '읽음으로 표시' : '안 읽음으로 표시', detail: unread ? 'Ctrl Q' : 'Ctrl U', onSelect: () => rowActions.toggleRead(mail) });
  }
  if (mail && canPin && supportsPin(mail)) {
    mailMenu.push({ key: 'pin', label: isPinned(mail) ? '고정 해제' : '맨 위에 고정', detail: 'Insert', onSelect: () => rowActions.togglePin(mail) });
  }

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
          selection={selection}
          onSelect={onSelect}
          rowActions={rowActions}
          bulk={bulk}
          helpOpen={helpOpen}
          onHelpOpenChange={setHelpOpen}
          onCompose={() => setComposing('new')}
        />
        <div className={styles.view}>
          {!source || !ctx ? (
            dashboard.isError ? null : <StateRow state="loading" />
          ) : composing && compose.mode !== null ? (
            <Compose
              key={`${compose.mode}-${mail?.id ?? 'new'}`}
              mode={compose.mode}
              mail={compose.mode === 'new' ? undefined : mail}
              ctx={ctx}
              accounts={accountsOf(source.mails)}
              sendAccounts={(mailAccounts.data?.items ?? []).filter((a) => a.connected)}
              templates={settings.data?.templates}
              me={me}
              initialContent={compose.draft}
              demo={source.origin.kind === 'mock'}
              onClose={() => setComposing(null)}
              onSent={() => {
                const sentMode = compose.mode;
                if (mail && (sentMode === 'reply' || sentMode === 'replyAll')) afterSent(mail);
                else {
                  setComposing(null);
                  toast.show({ kind: 'info', title: sentMode === 'forward' ? '전달했어요' : '메일을 보냈어요' });
                }
              }}
            />
          ) : mailId === null ? (
            <div className={styles.empty}>
              <Inbox size={32} strokeWidth={1.5} aria-hidden="true" />
              <p className={styles.emptyTitle}>메일을 고르면 여기에 보여요</p>
              <p className={styles.quiet}>목록에서 ↑↓로 옮기고 Enter로 열어요 · 단축키는 ?</p>
            </div>
          ) : !mail ? (
            <p className={styles.quiet}>메일을 찾을 수 없음</p>
          ) : (
            <ReadingPane
              key={mail.id}
              mail={mail}
              ctx={ctx}
              now={now}
              onReply={() => setComposing('reply')}
              onReplyAll={mail.direction === 'received' ? () => setComposing('replyAll') : undefined}
              onForward={() => setComposing('forward')}
              mailMenu={mailMenu}
              footerActions={moveButtons}
            />
          )}
        </div>
      </div>
      <CompleteSheet
        key={sheet.key}
        open={sheet.open}
        tasks={sheet.tasks}
        asOfMs={source?.asOfMs ?? 0}
        title={sheet.mode === 'exclude' ? '제외할까요?' : undefined}
        canSkip={sheet.mode === 'reply' && settings.data?.replyConfirmSkipUntilMs !== undefined}
        busy={sheet.busy}
        onYes={(ids, skip) => void sheetYes(ids, skip)}
        onNo={sheetNo}
      />
    </div>
  );
}
