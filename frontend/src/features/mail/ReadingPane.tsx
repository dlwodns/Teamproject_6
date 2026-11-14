// 오른쪽 메일 읽기 (components.md 4.3 · UX-D14 머리 순서).
// 제목 → 보낸 사람 줄(Avatar · 이름 · <주소> · 플래그 칩 · 받는 사람 · 오른쪽 날짜 시각) → 오른쪽 위 [답장] · ⋯ → 업무 N → 본문 → 본문 아래 동작.
// 본문은 메일 한 통 API(useMailQuery)에서만 온다. 없으면 '본문을 불러올 수 없음' — 본문을 지어내지 않는다.
// [메일 요약](FE-5c) · 근거 형광펜(FE-5b)은 아직 그리지 않는다. 본문 문단은 data-paragraph로 표시해 둔다.
import { useEffect, useRef } from 'react';
import type { Mail, Task } from '../../api/types.ts';
import { useMailQuery } from '../../api/queries.ts';
import { snoozeOptions, formatKstShort } from '../../lib/snooze.ts';
import { useTaskActions } from '../tasks/useTaskActions.ts';
import { Avatar, Button, Checkbox, Chip, ChevronDown, DueLabel, Ellipsis, FlagChips, IconButton, Menu, Reply, StateRow, useToast, type MenuItemSpec } from '../../ui/index.ts';
import { accountLabel, byUrgency, isOpenTask, isTaskMail, mailFlags, senderName, taskDue, tasksOf, type MailContext } from './mailboxes.ts';
import styles from './ReadingPane.module.css';

interface Props {
  mail: Mail;
  ctx: MailContext;
  /** 데이터 기준 지금 시각(나중에 시각 계산) */
  now: () => number;
  onReply: () => void;
  /** ⋯ 메뉴 맨 위에 더하는 메일 동작(FE-5d: 안 읽음으로 표시 · 고정). 서버에 없으면 빈 목록 */
  mailMenu?: MenuItemSpec[];
}

const STATUS_TEXT: Partial<Record<Task['status'], string>> = { done: '완료', snoozed: '나중에', excluded: '제외' };

function TaskItem({ task, asOfMs, onComplete }: { task: Task; asOfMs: number; onComplete: (t: Task) => void }) {
  const due = taskDue(task, asOfMs);
  const finished = task.status === 'done' || task.status === 'excluded';
  const statusText = STATUS_TEXT[task.status];
  return (
    <li className={styles.task} data-status={task.status}>
      <Checkbox
        shape="circle"
        checked={task.status === 'done'}
        disabled={finished}
        aria-label={statusText ? `${task.text} · ${statusText}` : task.text}
        onCheckedChange={(checked) => {
          if (checked) onComplete(task);
        }}
      />
      <span className={styles.taskText}>
        {task.text}
        {statusText && <small className={styles.taskStatus}>{statusText}</small>}
      </span>
      {!finished && <DueLabel kind={due.kind} text={due.text} srText={due.full ?? undefined} fullTime={due.full ?? undefined} />}
    </li>
  );
}

export function ReadingPane({ mail, ctx, now, onReply, mailMenu = [] }: Props) {
  const detail = useMailQuery(mail.id);
  const actions = useTaskActions();
  const toast = useToast();
  const headRef = useRef<HTMLHeadingElement>(null);

  // 1024px 미만(세 칸이 위아래로 쌓임)에서는 메일을 고르면 읽기 자리로 굴린다. 포커스는 옮기지 않는다(목록 키보드 이동 유지)
  useEffect(() => {
    if (typeof window !== 'undefined' && window.matchMedia('(width < 1024px)').matches) headRef.current?.scrollIntoView({ block: 'start' });
  }, [mail.id]);

  const contact = ctx.contactsByEmail.get(mail.sender);
  const name = senderName(ctx, mail);
  const tasks = [...tasksOf(ctx, mail)].sort(byUrgency(ctx.asOfMs));
  const openIds = tasks.filter(isOpenTask).map((t) => t.id);
  const taskMail = isTaskMail(ctx, mail);
  const to = detail.data?.to ?? mail.to;
  const lang = detail.data?.lang ?? mail.lang ?? undefined;

  const fail = () => toast.show({ kind: 'error', title: '바꾸지 못함' });
  const complete = (t: Task) => void actions.complete([t.id], { source: 'button' }).catch(fail);
  const snooze = (untilMs: number) => void actions.snooze(openIds, untilMs, { source: 'button' }).catch(fail);
  const exclude = () => void actions.exclude(openIds, { source: 'button' }).catch(fail);

  const snoozeItems = (prefix: string): MenuItemSpec[] =>
    snoozeOptions(now()).map((o) => ({ key: o.key, label: `${prefix}${o.label}`, detail: o.detail, onSelect: () => snooze(o.untilMs) }));
  const canAct = taskMail && openIds.length > 0;
  const taskItems: MenuItemSpec[] = canAct ? [...snoozeItems('나중에 · '), { key: 'exclude', label: '제외', onSelect: exclude, separatorBefore: true }] : [];
  const moreItems: MenuItemSpec[] = [
    ...mailMenu,
    ...taskItems.map((it, i) => (i === 0 && mailMenu.length > 0 ? { ...it, separatorBefore: true } : it)),
  ];

  const meta = [to && to.length > 0 ? `받는 사람: ${to.join(', ')}` : null, mail.account ? accountLabel(mail.account) : null, mail.category].filter(Boolean);

  return (
    <article className={styles.pane} aria-labelledby={`mail-subject-${mail.id}`}>
      <header className={styles.head}>
        <h2 ref={headRef} id={`mail-subject-${mail.id}`} className={styles.subject} lang={lang}>
          {mail.subject}
        </h2>
        <div className={styles.from}>
          <Avatar name={name} />
          <div className={styles.who}>
            <div className={styles.name}>
              <b>{name}</b>
              <span className={styles.addr}>&lt;{mail.sender}&gt;</span>
              {contact?.position && <span className={styles.addr}>{contact.position}</span>}
              {/* 플래그는 보낸 사람 이름 줄에 붙인다(따로 한 줄을 차지하면 떠 보인다) */}
              <FlagChips flags={mailFlags(ctx, mail)} />
            </div>
            {meta.length > 0 && <div className={styles.meta}>{meta.join(' · ')}</div>}
          </div>
          <div className={styles.side}>
            <time className={styles.time} dateTime={new Date(mail.receivedAtMs).toISOString()}>
              {formatKstShort(mail.receivedAtMs)}
            </time>
            <div className={styles.acts}>
              {/* 위에는 조용한 아이콘만, 주 동작(답장 · 나중에 · 제외)은 본문 아래 한 곳에 모은다(Gmail · Outlook 관례) */}
              <IconButton label="답장" icon={<Reply size={20} aria-hidden="true" />} onClick={onReply} />
              {moreItems.length > 0 && <Menu align="end" trigger={<IconButton label="더 보기" icon={<Ellipsis size={20} aria-hidden="true" />} />} items={moreItems} />}
            </div>
          </div>
        </div>
      </header>

      {tasks.length > 0 ? (
        <section className={styles.found} aria-labelledby={`mail-tasks-${mail.id}`}>
          <h3 id={`mail-tasks-${mail.id}`} className={styles.eyebrow}>
            업무 {tasks.length}
          </h3>
          <ul className={styles.tasks}>
            {tasks.map((t) => (
              <TaskItem key={t.id} task={t} asOfMs={ctx.asOfMs} onComplete={complete} />
            ))}
          </ul>
        </section>
      ) : (
        (mail.lane === '확인' || mail.lane === '참고') && (
          <div className={styles.found} data-reason="">
            {mail.lane === '참고' ? (
              <Chip kind="category">참고</Chip>
            ) : (
              (mail.reasons && mail.reasons.length > 0 ? mail.reasons : ['확인']).map((r) => (
                <Chip key={r} kind="reason">
                  {r}
                </Chip>
              ))
            )}
          </div>
        )
      )}

      <div className={styles.body} lang={lang}>
        {detail.isPending && <StateRow state="loading" />}
        {detail.isNotAvailable && <p className={styles.quiet}>본문을 불러올 수 없음</p>}
        {detail.isError && !detail.isNotAvailable && <StateRow state="error" onRetry={() => void detail.refetch()} />}
        {detail.data?.body.map((p, i) => (
          <p key={i} className={styles.paragraph} data-paragraph={i}>
            {p}
          </p>
        ))}
      </div>

      <footer className={styles.foot}>
        <Button variant="primary" onClick={onReply}>
          답장
        </Button>
        {taskMail && (
          <>
            {canAct ? (
              <Menu
                trigger={
                  <Button>
                    나중에 <ChevronDown size={16} aria-hidden="true" />
                  </Button>
                }
                items={snoozeItems('')}
              />
            ) : (
              <Button disabled>
                나중에 <ChevronDown size={16} aria-hidden="true" />
              </Button>
            )}
            <Button disabled={!canAct} onClick={exclude}>
              제외
            </Button>
          </>
        )}
      </footer>
    </article>
  );
}
