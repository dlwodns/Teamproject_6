// 가운데 메일 목록 (components.md 4.3 · wireframe 13-7).
// 위 막대: [▥] · 메일함 이름 · 건수 · 단축키 표시(--z-sticky). 줄: 발신자 + 플래그 칩 · 시각 · 제목 · 라벨.
// 키보드: 목록 안에서 ↑ ↓ · Home · End로 줄을 옮기고(포커스만, 한 줄만 Tab에 걸린다) Enter로 연다.
import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import type { Awaiting, Mail } from '../../api/types.ts';
import { shouldIgnoreShortcut, TOGGLE_MAILBOX_KEYSHORTCUTS } from '../../lib/shortcuts.ts';
import { Building, DueLabel, FLAG_LABELS, FlagChips, IconButton, PanelLeft, RankIcon, Star, StateRow, VisuallyHidden } from '../../ui/index.ts';
import { formatListTime, isUnread, mailFlags, rowStatus, senderName, type FlagKind, type MailContext } from './mailboxes.ts';
import styles from './MailList.module.css';

type ListState = { kind: 'loading' } | { kind: 'error'; onRetry: () => void } | { kind: 'mails'; mails: Mail[]; ctx: MailContext } | { kind: 'waiting'; awaiting: Awaiting[] };

interface Props {
  boxLabel: string;
  state: ListState;
  selectedId: number | null;
  onOpen: (mail: Mail) => void;
  mailboxOpen: boolean;
  onToggleMailbox: () => void;
  mailboxId: string;
  shortcutLabel: string;
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

function MailRows({ mails, ctx, selectedId, onOpen }: { mails: Mail[]; ctx: MailContext; selectedId: number | null; onOpen: (m: Mail) => void }) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const selectedIndex = mails.findIndex((m) => m.id === selectedId);
  const [focusIndex, setFocusIndex] = useState(Math.max(0, selectedIndex));
  const current = Math.min(focusIndex, mails.length - 1);

  // 다른 메일이 골라지면(대시보드에서 넘어옴 · 뒤로 가기) 그 줄이 Tab 자리가 되고 보이게 굴린다
  useEffect(() => {
    if (selectedIndex < 0) return;
    setFocusIndex(selectedIndex);
    refs.current[selectedIndex]?.scrollIntoView({ block: 'nearest' });
  }, [selectedIndex]);

  const onKeyDown = (e: KeyboardEvent<HTMLUListElement>) => {
    if (shouldIgnoreShortcut(e.nativeEvent) || e.altKey || e.ctrlKey || e.metaKey) return;
    const last = mails.length - 1;
    const next =
      e.key === 'ArrowDown' ? Math.min(current + 1, last) : e.key === 'ArrowUp' ? Math.max(current - 1, 0) : e.key === 'Home' ? 0 : e.key === 'End' ? last : null;
    if (next === null) return;
    e.preventDefault();
    setFocusIndex(next);
    refs.current[next]?.focus();
  };

  return (
    <ul className={styles.rows} onKeyDown={onKeyDown}>
      {mails.map((mail, i) => {
        const flags = mailFlags(ctx, mail);
        const unread = isUnread(mail);
        return (
          <li key={mail.id}>
            <button
              ref={(el) => {
                refs.current[i] = el;
              }}
              type="button"
              className={styles.row}
              tabIndex={i === current ? 0 : -1}
              aria-current={mail.id === selectedId ? 'true' : undefined}
              data-unread={unread ? '' : undefined}
              onFocus={() => setFocusIndex(i)}
              onClick={() => onOpen(mail)}
            >
              <span className={styles.from}>
                <span className={styles.sender}>{senderName(ctx, mail)}</span>
                <span className={styles.flagChips}>
                  <FlagChips flags={flags} />
                </span>
                <FlagIcons flags={flags} />
              </span>
              <span className={styles.time}>{formatListTime(mail.receivedAtMs, ctx.asOfMs)}</span>
              <span className={styles.subject} lang={mail.lang ?? undefined}>
                {unread && <VisuallyHidden>안 읽음 · </VisuallyHidden>}
                {mail.subject}
              </span>
              <RowLabels mail={mail} ctx={ctx} />
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function WaitingRows({ awaiting }: { awaiting: Awaiting[] }) {
  return (
    <ul className={styles.rows}>
      {awaiting.map((w) => (
        <li key={w.mailId} className={styles.row} data-static="">
          <span className={styles.from}>
            <span className={styles.sender}>{w.to}</span>
          </span>
          <span className={styles.time}>
            <DueLabel kind="none" text={`${w.days}일`} srText={`보낸 뒤 ${w.days}일`} />
          </span>
          <span className={styles.subject}>{w.subject}</span>
        </li>
      ))}
    </ul>
  );
}

export function MailList({ boxLabel, state, selectedId, onOpen, mailboxOpen, onToggleMailbox, mailboxId, shortcutLabel }: Props) {
  const count = state.kind === 'mails' ? state.mails.length : state.kind === 'waiting' ? state.awaiting.length : null;
  return (
    <section className={styles.list} aria-labelledby="page-title">
      <div className={styles.bar}>
        <IconButton
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
        <kbd className={styles.kbd} aria-hidden="true">
          {shortcutLabel}
        </kbd>
      </div>
      {state.kind === 'loading' && <StateRow state="loading" />}
      {state.kind === 'error' && <StateRow state="error" onRetry={state.onRetry} />}
      {count === 0 && <StateRow state="empty" />}
      {state.kind === 'mails' && state.mails.length > 0 && <MailRows mails={state.mails} ctx={state.ctx} selectedId={selectedId} onOpen={onOpen} />}
      {state.kind === 'waiting' && state.awaiting.length > 0 && <WaitingRows awaiting={state.awaiting} />}
    </section>
  );
}

export type { ListState };
