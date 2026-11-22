// 오른쪽 메일 읽기 (components.md 4.3 · UX-D14 머리 순서).
// 제목 → 보낸 사람 줄(Avatar · 이름 · <주소> · 플래그 칩 · 받는 사람 · 오른쪽 날짜 시각) → 오른쪽 위 [답장] · ⋯ → 업무 N → 본문 → 본문 아래 동작.
// 본문은 메일 한 통 API(useMailQuery)에서만 온다. 없으면 '본문을 불러올 수 없음' — 본문을 지어내지 않는다.
// 근거 형광펜(FE-5b · UX-D16): 업무마다 붙은 근거 문장을 본문에서 찾아 <mark>로 칠하고, 업무 줄 순서를 형광펜 순서에 맞춘다.
// 업무 줄을 누르면 그 문장으로 옮겨 가 0.8초 진하게 보인다. 찾지 못하면 칠하지 않고 업무 줄에 '근거 문장 없음'(지어내지 않음).
// 요약(AI-32 · FE-5c): 분류 때 같이 만든 한국어 요지를 맨 위에 둔다 — 요약 → 업무 → 원문(제품 핵심 = 업무 + 요약).
// 요약이 없으면(분류 전 · 요약 못 함) 자리를 비운다. 지어내지 않는다.
// 번역(AI-32, 아웃룩 메시지 머리 […] → 번역 · 원본 보기): 누를 때만 서버에 한 번 묻고(서버가 저장), 본문을 번역문으로 바꿔 보인다.
// 번역문에는 근거 형광펜을 칠하지 않는다(근거는 원문 문장). 한국어로 알려진 메일에는 메뉴를 두지 않는다.
import { useEffect, useRef, useState, type ReactNode } from 'react';
import type { Mail, Task } from '../../api/types.ts';
import { useMailQuery, useTranslateMail } from '../../api/queries.ts';
import { reducedMotion } from '../../lib/motion.ts';
import { snoozeOptions, formatKstShort } from '../../lib/snooze.ts';
import { useTaskActions } from '../tasks/useTaskActions.ts';
import { MailAttachments } from './MailAttachments.tsx';
import { HtmlBody } from './HtmlBody.tsx';
import { Avatar, Button, Checkbox, Chip, ChevronDown, DueLabel, Ellipsis, FlagChips, IconButton, Menu, Reply, Spinner, StateRow, useToast, type MenuItemSpec } from '../../ui/index.ts';
import { locateEvidence, occurrenceOf, orderByEvidence, segmentParagraph, type EvidenceMark } from './evidence.ts';
import { accountLabel, byUrgency, isOpenTask, isTaskMail, mailFlags, senderName, taskDue, tasksOf, type MailContext } from './mailboxes.ts';
import styles from './ReadingPane.module.css';

interface Props {
  mail: Mail;
  ctx: MailContext;
  /** 데이터 기준 지금 시각(나중에 시각 계산) */
  now: () => number;
  onReply: () => void;
  /** FE-18 전체 답장 · 전달. 없으면 버튼을 숨긴다 */
  onReplyAll?: () => void;
  onForward?: () => void;
  /** ⋯ 메뉴 맨 위에 더하는 메일 동작(FE-5d: 안 읽음으로 표시 · 고정). 서버에 없으면 빈 목록 */
  mailMenu?: MenuItemSpec[];
  /** 본문 아래 동작 줄 끝에 더하는 버튼(BE-7: 보관 · 삭제 · 받은 편지함으로 되돌리기) */
  footerActions?: ReactNode;
}

const STATUS_TEXT: Partial<Record<Task['status'], string>> = { done: '완료', snoozed: '나중에', excluded: '제외' };

const ACTIVE_MS = 800; // 업무 줄을 눌러 옮겨 간 문장을 진하게 보이는 시간(design_system 형광펜)

interface TaskItemProps {
  task: Task;
  asOfMs: number;
  onComplete: (t: Task) => void;
  /** 근거 문장 자리. undefined = 본문을 아직 못 받음(아무것도 적지 않음), null = 찾지 못함(끝난 업무는 적지 않는다) */
  mark: EvidenceMark | null | undefined;
  onShowEvidence: () => void;
}

function TaskItem({ task, asOfMs, onComplete, mark, onShowEvidence }: TaskItemProps) {
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
        {mark ? (
          <button type="button" className={styles.taskLink} aria-describedby={markDomId(mark)} onClick={onShowEvidence}>
            {task.text}
          </button>
        ) : (
          task.text
        )}
        {statusText && <small className={styles.taskStatus}>{statusText}</small>}
        {mark === null && !finished && <small className={styles.taskStatus}>근거 문장 없음</small>}
      </span>
      {!finished && <DueLabel kind={due.kind} text={due.text} srText={due.full ?? undefined} fullTime={due.full ?? undefined} />}
    </li>
  );
}

const markDomId = (m: EvidenceMark) => `mail-${m.id}`;

export function ReadingPane({ mail, ctx, now, onReply, onReplyAll, onForward, mailMenu = [], footerActions }: Props) {
  const detail = useMailQuery(mail.id);
  const actions = useTaskActions();
  const toast = useToast();
  const translate = useTranslateMail();
  const [translated, setTranslated] = useState<string | null>(null);
  const [translatedPart, setTranslatedPart] = useState(false); // 긴 본문이라 앞부분만 번역
  useEffect(() => setTranslated(null), [mail.id]);
  const headRef = useRef<HTMLHeadingElement>(null);

  // 1024px 미만(세 칸이 위아래로 쌓임)에서는 메일을 고르면 읽기 자리로 굴린다. 포커스는 옮기지 않는다(목록 키보드 이동 유지)
  useEffect(() => {
    if (typeof window !== 'undefined' && window.matchMedia('(width < 1024px)').matches) headRef.current?.scrollIntoView({ block: 'start' });
  }, [mail.id]);

  const contact = ctx.contactsByEmail.get(mail.sender);
  const name = senderName(ctx, mail);
  const body = detail.data?.body;
  const byUrgent = [...tasksOf(ctx, mail)].sort(byUrgency(ctx.asOfMs));
  const evidence = body ? locateEvidence(body, byUrgent) : null; // 업무 몇 건 · 문단 몇 개라 렌더마다 다시 찾아도 가볍다
  const tasks = evidence ? orderByEvidence(byUrgent, evidence) : byUrgent;
  const [active, setActive] = useState<readonly string[] | null>(null); // 강조 중인 근거 줄들(업무 하나의 근거 전부)
  useEffect(() => {
    if (!active) return;
    const id = window.setTimeout(() => setActive(null), ACTIVE_MS);
    return () => window.clearTimeout(id);
  }, [active]);
  useEffect(() => setActive(null), [mail.id]);
  const showEvidence = (taskId: Task['id']) => {
    const lines = evidence?.linesByTask.get(taskId);
    const m = lines?.[0];
    if (!lines || !m) return;
    const el = document.getElementById(markDomId(m));
    if (!el) return;
    el.scrollIntoView({ block: 'center', behavior: reducedMotion() ? 'auto' : 'smooth' });
    el.focus({ preventScroll: true });
    setActive(lines.map((x) => x.id));
  };
  const openIds = tasks.filter(isOpenTask).map((t) => t.id);
  const taskMail = isTaskMail(ctx, mail);
  const to = detail.data?.to ?? mail.to;
  const lang = detail.data?.lang ?? mail.lang ?? undefined;

  // 성공 · 실패 토스트는 useTaskActions(FE-4)가 띄운다. 여기서는 실패를 삼키기만 한다(안내가 두 번 뜨지 않게)
  const ignore = () => {};
  const complete = (t: Task) => void actions.complete([t.id], { source: 'button' }).catch(ignore);
  const snooze = (untilMs: number) => void actions.snooze(openIds, untilMs, { source: 'button' }).catch(ignore);
  const exclude = () => void actions.exclude(openIds, { source: 'button' }).catch(ignore);

  const snoozeItems = (prefix: string): MenuItemSpec[] =>
    snoozeOptions(now()).map((o) => ({ key: o.key, label: `${prefix}${o.label}`, detail: o.detail, onSelect: () => snooze(o.untilMs) }));
  const canAct = taskMail && openIds.length > 0;
  const taskItems: MenuItemSpec[] = canAct ? [...snoozeItems('나중에 · '), { key: 'exclude', label: '제외', onSelect: exclude, separatorBefore: true }] : [];
  const srcLang = detail.data?.summary?.lang ?? lang;
  const toggleTranslation = () => {
    if (translated !== null) return setTranslated(null);
    translate.mutate(mail.id, {
      onSuccess: (r) => {
        if (!r.text) return toast.show({ kind: 'info', title: '번역하지 않았습니다', description: r.fallback ?? undefined });
        setTranslated(r.text);
        setTranslatedPart(r.truncated);
      },
      onError: () => toast.show({ kind: 'error', title: '번역하지 못했습니다', description: '잠시 뒤 다시 시도해 주세요' }),
    });
  };
  const translateItems: MenuItemSpec[] =
    srcLang === 'ko' || !body ? [] : [{ key: 'translate', label: translated !== null ? '원본 보기' : '번역', onSelect: toggleTranslation }];
  const headItems = [...translateItems, ...mailMenu.map((it, i) => (i === 0 && translateItems.length > 0 ? { ...it, separatorBefore: true } : it))];
  const moreItems: MenuItemSpec[] = [
    ...headItems,
    ...taskItems.map((it, i) => (i === 0 && headItems.length > 0 ? { ...it, separatorBefore: true } : it)),
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
              <IconButton label="회신" icon={<Reply size={20} aria-hidden="true" />} onClick={onReply} />
              {moreItems.length > 0 && <Menu align="end" trigger={<IconButton label="더 보기" icon={<Ellipsis size={20} aria-hidden="true" />} />} items={moreItems} />}
            </div>
          </div>
        </div>
      </header>

      {detail.data?.summary && (
        <section className={styles.summary} aria-labelledby={`mail-summary-${mail.id}`}>
          <h3 id={`mail-summary-${mail.id}`} className={styles.eyebrow}>
            요약{detail.data.summary.lang !== 'ko' && ' · 원문은 외국어'}
          </h3>
          <p className={styles.gist}>{detail.data.summary.gist}</p>
        </section>
      )}

      {tasks.length > 0 ? (
        <section className={styles.found} aria-labelledby={`mail-tasks-${mail.id}`}>
          <h3 id={`mail-tasks-${mail.id}`} className={styles.eyebrow}>
            업무 {tasks.length}
          </h3>
          <ul className={styles.tasks}>
            {tasks.map((t) => (
              <TaskItem
                key={t.id}
                task={t}
                asOfMs={ctx.asOfMs}
                onComplete={complete}
                mark={evidence ? (evidence.byTask.get(t.id) ?? null) : undefined}
                onShowEvidence={() => showEvidence(t.id)}
              />
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

      {(translate.isPending || translated !== null) && (
        <div className={styles.translated} role="status">
          {translate.isPending ? (
            <>
              <Spinner /> 번역 중…
            </>
          ) : (
            <>
              {translatedPart ? '앞부분만 한국어로 번역됨(본문이 길어 뒷부분은 원본 보기에서)' : '한국어로 번역됨'}
              <Button variant="ghost" onClick={() => setTranslated(null)}>
                원본 보기
              </Button>
            </>
          )}
        </div>
      )}

      {translated !== null ? (
        <div className={styles.body} lang="ko">
          {translated.split('\n').map((p, i) => (
            <p key={i} className={styles.paragraph}>
              {p}
            </p>
          ))}
        </div>
      ) : (
        <div className={styles.body} lang={lang}>
          {detail.isPending && <StateRow state="loading" />}
          {detail.isNotAvailable && <p className={styles.quiet}>본문을 불러올 수 없음</p>}
          {detail.isError && !detail.isNotAvailable && <StateRow state="error" onRetry={() => void detail.refetch()} />}
          {detail.data?.bodyHtml ? (
            <HtmlBody
              html={detail.data.bodyHtml}
              active={active}
              marks={(evidence?.marks ?? []).map((m) => ({
                domId: markDomId(m),
                markId: m.id,
                text: (body?.[m.paragraph] ?? '').slice(m.start, m.end),
                nth: occurrenceOf(body ?? [], m),
              }))}
            />
          ) : body?.map((p, i) => (
            <p key={i} className={styles.paragraph} data-paragraph={i}>
              {segmentParagraph(p, i, evidence?.marks ?? []).map((seg, j) =>
                seg.mark ? (
                  <mark key={j} id={markDomId(seg.mark)} tabIndex={-1} className={styles.mark} data-active={active?.includes(seg.mark.id) || undefined}>
                    <span className="sr-only">업무 근거: </span>
                    {seg.text}
                  </mark>
                ) : (
                  seg.text
                ),
              )}
            </p>
          ))}
        </div>
      )}

      <MailAttachments mailId={mail.id} />

      <footer className={styles.foot}>
        <Button variant="primary" onClick={onReply}>
          회신
        </Button>
        {onReplyAll && <Button onClick={onReplyAll}>전체 회신</Button>}
        {onForward && <Button onClick={onForward}>전달</Button>}
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
        {footerActions}
      </footer>
    </article>
  );
}
