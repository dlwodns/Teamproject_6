// 가운데 메일 목록 (components.md 4.3 · wireframe 13-7 · FE-5d Outlook 메일 관리).
// 위 막대: [▥] · 메일함 이름 · 건수 · [단축키 ?]. 여러 통을 고르면 같은 자리가 묶음 동작 막대로 바뀐다.
// 묶음 머리: 고정됨 → 오늘 · 어제 · 이번 주 · 지난주 · 이전(listView.ts). 굴려도 묶음 이름이 위에 붙어 있다.
// 줄: [고르기 칸(안 읽음 점 · 마우스를 올리면 네모 상자)] 발신자 + 플래그 칩 · 시각(고정 핀) · 제목 · 라벨.
//     마우스를 올리거나 키보드 포커스가 들어오면 시각 자리 위에 빠른 동작(완료 · 나중에 · 고정 · 읽음)이 겹쳐 보인다(자리 밀림 없음).
// 키보드: 목록 안에서 ↑ ↓ · Home · End로 줄을 옮기고(포커스만, 한 줄만 Tab에 걸린다) Enter로 연다. 그 줄의 상자 · 빠른 동작은 Tab으로 이어 간다.
import { useEffect, useRef, useState, type KeyboardEvent, type MouseEvent, type ReactNode } from 'react';
import type { Awaiting, Mail, MailId } from '../../api/types.ts';
import { shouldIgnoreShortcut, TOGGLE_MAILBOX_KEYSHORTCUTS } from '../../lib/shortcuts.ts';
import type { SnoozeOption } from '../../lib/snooze.ts';
import {
  Building,
  Button,
  Checkbox,
  CircleCheck,
  Clock,
  DueLabel,
  FLAG_LABELS,
  FlagChips,
  IconButton,
  Keyboard,
  MailIcon,
  MailOpen,
  Menu,
  PanelLeft,
  SquarePen,
  Pin,
  PinOff,
  Popover,
  RankIcon,
  Star,
  StateRow,
  VisuallyHidden,
  X,
} from '../../ui/index.ts';
import type { MailGroup, Selection } from './listView.ts';
import { isPinned, supportsPin, supportsRead } from './listView.ts';
import { formatListTime, isOpenTask, isTaskMail, isUnread, mailFlags, rowStatus, senderName, tasksOf, type FlagKind, type MailContext } from './mailboxes.ts';
import { MAIL_SHORTCUT_HELP } from './mailShortcuts.ts';
import styles from './MailList.module.css';

type ListState =
  | { kind: 'loading' }
  | { kind: 'error'; onRetry: () => void }
  | { kind: 'mails'; groups: MailGroup[]; order: Mail[]; ctx: MailContext }
  | { kind: 'waiting'; awaiting: Awaiting[] };

/** 줄 하나의 빠른 동작. 서버가 칸을 보내지 않거나 요청이 없으면 canRead · canPin이 거짓 → 그 단추를 숨긴다 */
export interface RowActions {
  canRead: boolean;
  canPin: boolean;
  complete: (mail: Mail) => void;
  snoozeOptions: () => SnoozeOption[];
  snooze: (mail: Mail, untilMs: number) => void;
  togglePin: (mail: Mail) => void;
  toggleRead: (mail: Mail) => void;
}

/** 여러 통을 골랐을 때 막대의 동작 */
export interface BulkBar {
  selected: Mail[];
  /** 고른 메일의 끝나지 않은 업무 수 */
  openTasks: number;
  /** [고정]이 고정할지(참) 풀지(거짓) */
  pinTarget: boolean;
  canRead: boolean;
  canPin: boolean;
  selectAll: () => void;
  read: (read: boolean) => void;
  pin: () => void;
  complete: () => void;
  clear: () => void;
}

interface Props {
  boxLabel: string;
  state: ListState;
  selectedId: number | null;
  onOpen: (mail: Mail) => void;
  mailboxOpen: boolean;
  onToggleMailbox: () => void;
  /** FE-18 [새 메일] */
  onCompose?: () => void;
  mailboxId: string;
  shortcutLabel: string;
  selection: Selection;
  onSelect: (id: MailId, range: boolean) => void;
  rowActions: RowActions;
  bulk: BulkBar;
  helpOpen: boolean;
  onHelpOpenChange: (open: boolean) => void;
}

/** 아주 좁은 화면(480px 이하)의 줄에서는 칩 대신 아이콘만(이름은 숨은 글자로) */
function FlagIcons({ flags }: { flags: FlagKind[] }) {
  if (flags.length === 0) return null;
  return (
    <span className={styles.flagIcons}>
      {flags.map((f) => (
        <span key={f} className={styles.flagIcon}>
          {f === 'superior' ? <RankIcon size={16} /> : f === 'favorite' ? <Star size={14} fill="currentColor" aria-hidden="true" /> : <Building size={14} aria-hidden="true" />}
          <VisuallyHidden>{FLAG_LABELS[f]}</VisuallyHidden>
        </span>
      ))}
    </span>
  );
}

function RowLabels({ mail, ctx }: { mail: Mail; ctx: MailContext }) {
  // 한 줄에 색 신호는 기한 라벨 하나만. 분류 · 업무 수 · 확인 사유는 회색 글자로 잇는다(칩을 여러 개 늘어놓지 않는다)
  const status = rowStatus(ctx, mail);
  const words: string[] = [];
  if (mail.category) words.push(mail.category);
  if (status.kind === 'tasks') words.push(`업무 ${status.open}`);
  if (status.kind === 'reasons') words.push(...status.reasons);
  if (status.kind === 'reference') words.push('참고');
  return (
    <span className={styles.labels}>
      {words.length > 0 && <span className={styles.meta}>{words.join(' · ')}</span>}
      {status.kind === 'tasks' && status.due && <DueLabel kind={status.due.kind} text={status.due.text} srText={status.due.full ?? undefined} />}
      {status.kind === 'done' && <DueLabel kind="done" text="완료" />}
    </span>
  );
}

/** 끝나지 않은 업무(업무 메일만): 빠른 동작 [완료] · [나중에]를 보일지 정한다 */
const openTasksOf = (ctx: MailContext, mail: Mail) => (isTaskMail(ctx, mail) ? tasksOf(ctx, mail).filter(isOpenTask) : []);

function QuickActions({ mail, ctx, actions, tabIndex }: { mail: Mail; ctx: MailContext; actions: RowActions; tabIndex: number }) {
  const open = openTasksOf(ctx, mail).length;
  const pinned = isPinned(mail);
  const unread = isUnread(mail);
  const buttons: ReactNode[] = [];
  if (open > 0) {
    buttons.push(
      <IconButton
        key="done"
        className={styles.quick}
        tabIndex={tabIndex}
        label={open > 1 ? `업무 ${open}건 완료` : '업무 완료'}
        icon={<CircleCheck size={20} aria-hidden="true" />}
        onClick={() => actions.complete(mail)}
      />,
      <Menu
        key="snooze"
        align="end"
        trigger={<IconButton className={styles.quick} tabIndex={tabIndex} label="나중에" icon={<Clock size={20} aria-hidden="true" />} />}
        items={actions.snoozeOptions().map((o) => ({ key: o.key, label: o.label, detail: o.detail, onSelect: () => actions.snooze(mail, o.untilMs) }))}
      />,
    );
  }
  if (actions.canPin && supportsPin(mail)) {
    buttons.push(
      <IconButton
        key="pin"
        className={styles.quick}
        tabIndex={tabIndex}
        label={pinned ? '고정 해제' : '맨 위에 고정'}
        tooltip={pinned ? '고정 해제 (Insert)' : '맨 위에 고정 (Insert)'}
        icon={pinned ? <PinOff size={20} aria-hidden="true" /> : <Pin size={20} aria-hidden="true" />}
        onClick={() => actions.togglePin(mail)}
      />,
    );
  }
  if (actions.canRead && supportsRead(mail)) {
    buttons.push(
      <IconButton
        key="read"
        className={styles.quick}
        tabIndex={tabIndex}
        label={unread ? '읽음으로 표시' : '안 읽음으로 표시'}
        tooltip={unread ? '읽음으로 표시 (Ctrl Q)' : '안 읽음으로 표시 (Ctrl U)'}
        icon={unread ? <MailOpen size={20} aria-hidden="true" /> : <MailIcon size={20} aria-hidden="true" />}
        onClick={() => actions.toggleRead(mail)}
      />,
    );
  }
  if (buttons.length === 0) return null;
  return (
    <div className={styles.quickBar} role="group" aria-label={`${mail.subject} 빠른 동작`}>
      {buttons}
    </div>
  );
}

interface RowsProps {
  groups: MailGroup[];
  order: Mail[];
  ctx: MailContext;
  selectedId: number | null;
  onOpen: (m: Mail) => void;
  selection: Selection;
  onSelect: (id: MailId, range: boolean) => void;
  actions: RowActions;
}

function MailRows({ groups, order, ctx, selectedId, onOpen, selection, onSelect, actions }: RowsProps) {
  const refs = useRef(new Map<MailId, HTMLButtonElement>());
  const selectedIndex = order.findIndex((m) => m.id === selectedId);
  const [focusIndex, setFocusIndex] = useState(Math.max(0, selectedIndex));
  const current = Math.min(focusIndex, order.length - 1);
  const currentId = order[current]?.id;
  /** 고르기 상자를 누를 때 Shift를 눌렀는지(Base UI 상자는 바뀐 값만 알려 준다) */
  const shiftRef = useRef(false);
  const selecting = selection.ids.size > 0;

  // 다른 메일이 골라지면(대시보드에서 넘어옴 · 뒤로 가기 · Ctrl+. ,) 그 줄이 Tab 자리가 되고 보이게 굴린다
  const selectedKey = order[selectedIndex]?.id;
  useEffect(() => {
    if (selectedKey === undefined) return;
    setFocusIndex(selectedIndex);
    refs.current.get(selectedKey)?.scrollIntoView({ block: 'nearest' });
  }, [selectedKey]);

  const focusAt = (i: number) => {
    setFocusIndex(i);
    const id = order[i]?.id;
    if (id !== undefined) refs.current.get(id)?.focus();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (shouldIgnoreShortcut(e.nativeEvent) || e.altKey || e.ctrlKey || e.metaKey) return;
    // 줄 이동은 줄 자체에 포커스가 있을 때만(빠른 동작 단추 · 메뉴 안의 화살표는 그대로)
    if (!(e.target instanceof HTMLElement) || !e.target.dataset['mailRow']) return;
    const last = order.length - 1;
    const next =
      e.key === 'ArrowDown' ? Math.min(current + 1, last) : e.key === 'ArrowUp' ? Math.max(current - 1, 0) : e.key === 'Home' ? 0 : e.key === 'End' ? last : null;
    if (next === null) return;
    e.preventDefault();
    focusAt(next);
  };

  const onRowClick = (e: MouseEvent<HTMLButtonElement>, mail: Mail) => {
    if (e.shiftKey || e.ctrlKey || e.metaKey) {
      onSelect(mail.id, e.shiftKey);
      return;
    }
    onOpen(mail);
  };

  return (
    <div className={styles.rows} onKeyDown={onKeyDown} data-selecting={selecting ? '' : undefined}>
      {groups.map((group) => (
        <section key={group.key} className={styles.group} aria-labelledby={`mail-group-${group.key}`}>
          <h2 id={`mail-group-${group.key}`} className={styles.groupHead}>
            {group.key === 'pinned' && <Pin size={12} aria-hidden="true" />}
            {group.label}
          </h2>
          <ul className={styles.list}>
            {group.mails.map((mail) => {
              const flags = mailFlags(ctx, mail);
              const unread = isUnread(mail);
              const checked = selection.ids.has(mail.id);
              const tab = mail.id === currentId ? 0 : -1;
              return (
                <li
                  key={mail.id}
                  className={styles.row}
                  data-current={mail.id === selectedId ? '' : undefined}
                  data-unread={unread ? '' : undefined}
                  data-checked={checked ? '' : undefined}
                >
                  <button
                    ref={(el) => {
                      if (el) refs.current.set(mail.id, el);
                      else refs.current.delete(mail.id);
                    }}
                    type="button"
                    className={styles.open}
                    data-mail-row="1"
                    tabIndex={tab}
                    aria-current={mail.id === selectedId ? 'true' : undefined}
                    onFocus={() => setFocusIndex(order.indexOf(mail))}
                    onMouseDown={(e) => {
                      if (e.shiftKey) e.preventDefault(); // Shift 클릭으로 글자가 칠해지지 않게
                    }}
                    onClick={(e) => onRowClick(e, mail)}
                  >
                    <span className={styles.from}>
                      <span className={styles.sender}>{senderName(ctx, mail)}</span>
                      <span className={styles.flagChips}>
                        <FlagChips flags={flags} />
                      </span>
                      <FlagIcons flags={flags} />
                    </span>
                    <span className={styles.time}>
                      {isPinned(mail) && (
                        <span className={styles.pinMark}>
                          <Pin size={12} aria-hidden="true" />
                          <VisuallyHidden>고정됨 · </VisuallyHidden>
                        </span>
                      )}
                      {formatListTime(mail.receivedAtMs, ctx.asOfMs)}
                    </span>
                    <span className={styles.subject} lang={mail.lang ?? undefined}>
                      {unread && <VisuallyHidden>안 읽음 · </VisuallyHidden>}
                      {mail.subject}
                    </span>
                    <RowLabels mail={mail} ctx={ctx} />
                  </button>
                  {/* 고르기 칸: 평소엔 안 읽음 점, 마우스를 올리거나 하나라도 고르면 네모 상자 */}
                  <span
                    className={styles.gutter}
                    onPointerDownCapture={(e) => {
                      shiftRef.current = e.shiftKey;
                    }}
                    onKeyDownCapture={() => {
                      shiftRef.current = false;
                    }}
                  >
                    {unread && <span className={styles.dot} aria-hidden="true" />}
                    <Checkbox
                      className={styles.check}
                      tabIndex={tab}
                      checked={checked}
                      aria-label={`${mail.subject} 고르기`}
                      onCheckedChange={() => onSelect(mail.id, shiftRef.current)}
                    />
                  </span>
                  <QuickActions mail={mail} ctx={ctx} actions={actions} tabIndex={tab} />
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}

function WaitingRows({ awaiting }: { awaiting: Awaiting[] }) {
  return (
    <ul className={styles.list}>
      {awaiting.map((w) => (
        <li key={w.mailId} className={styles.row} data-static="">
          <span className={styles.open}>
            <span className={styles.from}>
              <span className={styles.sender}>{w.to}</span>
            </span>
            <span className={styles.time}>
              <DueLabel kind="none" text={`${w.days}일`} srText={`보낸 뒤 ${w.days}일`} />
            </span>
            <span className={styles.subject}>{w.subject}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function ShortcutHelp({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Popover
      title="메일 단축키"
      open={open}
      onOpenChange={onOpenChange}
      trigger={<IconButton label="단축키 보기" tooltip="단축키 (?)" icon={<Keyboard size={20} aria-hidden="true" />} />}
    >
      <dl className={styles.help}>
        {MAIL_SHORTCUT_HELP.map((row) => (
          <div key={row.label} className={styles.helpRow}>
            <dt className={styles.helpKeys}>
              {row.keys.map((k) => (
                <kbd key={k} className={styles.kbd}>
                  {k}
                </kbd>
              ))}
            </dt>
            <dd className={styles.helpLabel}>{row.label}</dd>
          </div>
        ))}
      </dl>
      <p className={styles.helpNote}>글을 쓰는 중에는 동작하지 않아요. Outlook과 같은 키를 쓰되, 플래그 키(Insert)는 고정에 맞췄어요.</p>
    </Popover>
  );
}

function SelectionBar({ bulk, total }: { bulk: BulkBar; total: number }) {
  const n = bulk.selected.length;
  const all = n === total && total > 0;
  return (
    <div className={styles.bar} data-mode="select" role="toolbar" aria-label="고른 메일 동작">
      <span className={styles.barCheck}>
        <Checkbox
          checked={all}
          indeterminate={!all}
          aria-label={all ? '모두 고르기 해제' : '모두 고르기'}
          onCheckedChange={() => (all ? bulk.clear() : bulk.selectAll())}
        />
      </span>
      <span className={styles.selCount} aria-live="polite">
        {n}통 선택
      </span>
      <span className={styles.barEnd}>
        {bulk.canRead && (
          <>
            <IconButton label="읽음으로 표시" tooltip="읽음으로 표시 (Ctrl Q)" icon={<MailOpen size={20} aria-hidden="true" />} onClick={() => bulk.read(true)} />
            <IconButton label="안 읽음으로 표시" tooltip="안 읽음으로 표시 (Ctrl U)" icon={<MailIcon size={20} aria-hidden="true" />} onClick={() => bulk.read(false)} />
          </>
        )}
        {bulk.canPin && (
          <IconButton
            label={bulk.pinTarget ? '맨 위에 고정' : '고정 해제'}
            tooltip={bulk.pinTarget ? '맨 위에 고정 (Insert)' : '고정 해제 (Insert)'}
            icon={bulk.pinTarget ? <Pin size={20} aria-hidden="true" /> : <PinOff size={20} aria-hidden="true" />}
            onClick={bulk.pin}
          />
        )}
        {bulk.openTasks > 0 && (
          <Button size="sm" onClick={bulk.complete}>
            업무 완료 {bulk.openTasks}건
          </Button>
        )}
        <IconButton label="선택 해제" tooltip="선택 해제 (Esc)" icon={<X size={20} aria-hidden="true" />} onClick={bulk.clear} />
      </span>
    </div>
  );
}

export function MailList(props: Props) {
  const { boxLabel, state, selectedId, onOpen, mailboxOpen, onToggleMailbox, mailboxId, shortcutLabel, selection, onSelect, rowActions, bulk } = props;
  const count = state.kind === 'mails' ? state.order.length : state.kind === 'waiting' ? state.awaiting.length : null;
  const selecting = state.kind === 'mails' && bulk.selected.length > 0;
  return (
    <section className={styles.listPane} aria-labelledby="page-title">
      {selecting ? (
        <>
          {/* 막대가 바뀌어도 화면 제목은 남겨 둔다(제목 포커스 · 영역 이름표) */}
          <h1 id="page-title" className={styles.hiddenTitle} tabIndex={-1}>
            {boxLabel}
          </h1>
          <SelectionBar bulk={bulk} total={count ?? 0} />
        </>
      ) : (
        <div className={styles.bar}>
          <IconButton
            className={styles.barToggle}
            label={mailboxOpen ? '메일함 닫기' : '메일함 열기'}
            tooltip={`${mailboxOpen ? '메일함 닫기' : '메일함 열기'} (${shortcutLabel})`}
            icon={<PanelLeft size={20} aria-hidden="true" />}
            aria-expanded={mailboxOpen}
            aria-controls={mailboxOpen ? mailboxId : undefined}
            aria-keyshortcuts={TOGGLE_MAILBOX_KEYSHORTCUTS}
            onClick={onToggleMailbox}
          />
          <h1 id="page-title" className={styles.boxName} tabIndex={-1}>
            {boxLabel}
          </h1>
          <span className={styles.count}>
            {count ?? '–'}
            <VisuallyHidden>통</VisuallyHidden>
          </span>
          <span className={styles.barEnd}>
            {props.onCompose && <IconButton label="새 메일" icon={<SquarePen size={20} aria-hidden="true" />} onClick={props.onCompose} />}
            {state.kind === 'mails' && <ShortcutHelp open={props.helpOpen} onOpenChange={props.onHelpOpenChange} />}
          </span>
        </div>
      )}
      <div className={styles.scroll}>
        {state.kind === 'loading' && <StateRow state="loading" />}
        {state.kind === 'error' && <StateRow state="error" onRetry={state.onRetry} />}
        {count === 0 && <StateRow state="empty" />}
        {state.kind === 'mails' && state.order.length > 0 && (
          <MailRows
            groups={state.groups}
            order={state.order}
            ctx={state.ctx}
            selectedId={selectedId}
            onOpen={onOpen}
            selection={selection}
            onSelect={onSelect}
            actions={rowActions}
          />
        )}
        {state.kind === 'waiting' && state.awaiting.length > 0 && <WaitingRows awaiting={state.awaiting} />}
      </div>
    </section>
  );
}

export type { ListState };
