// 업무 요약 · 회고 메뉴 (FE-16 · 명세 4.3 · 5절). 가운데: 날짜(누르면 작은 달력) + 일일 요약 · 일일 회고 · 주간(세로 탭), 오른쪽: 본문.
// 본문은 무엇이 있는지만 알린다(AI-D18). 숫자와 목록은 서버가 세고, 문장이 없으면 목록만 보인다.
// 퇴근 회고 '미처리 업무' 줄마다 [내일 아침으로 미루기](대시보드와 같은 미루기 함수).
import { useId, useRef, useState, type KeyboardEvent } from 'react';
import { useNavigate } from 'react-router';
import { BRIEFING_KINDS, type BriefingItem, type BriefingKind, type ReminderItem } from '../../api/contract.ts';
import { useSettingsQuery } from '../../api/queries.ts';
import { useBriefingQuery } from '../../api/reminders.ts';
import type { DashboardSource } from '../../api/types.ts';
import { reminderPath } from '../../features/agent/agentRoutes.ts';
import { BRIEFING_LABEL, briefingEmptyText, briefingWhen, canSnoozeToMorning, dateLabel, stepBriefingDate, weekRange } from '../../features/reminders/briefingModel.ts';
import { useOpenMail } from '../../features/tasks/useOpenMail.ts';
import { taskDueBadge } from '../../features/tasks/deadline.ts';
import { useTaskActions } from '../../features/tasks/useTaskActions.ts';
import { formatKstShort, snoozeOptions } from '../../lib/snooze.ts';
import { Button, ChevronLeft, ChevronRight, DueLabel, IconButton, StateRow, useToast } from '../../ui/index.ts';
import styles from './AgentPage.module.css';
import { MiniCalendar } from './MiniCalendar.tsx';

interface Props {
  /** 서버 시각의 한국 날짜. 서버 시각을 아직 모르면 null(시연 시계와 브라우저 날짜가 달라 엉뚱한 날을 먼저 부르지 않게 기다린다) */
  today: string | null;
  nowMs: number;
  source: DashboardSource | undefined;
  reminders: readonly ReminderItem[];
}

export function BriefingView({ today, nowMs, source, reminders }: Props) {
  const [kind, setKind] = useState<BriefingKind>('morning');
  const settings = useSettingsQuery();
  // 고른 날짜. 고르기 전에는 늘 서버의 오늘을 따른다(처음 열 때 서버 시각이 늦게 와도 오늘로 맞는다)
  const [picked, setPicked] = useState<string | null>(null);
  const date = today === null ? null : picked !== null && picked < today ? picked : today;
  const step = (dir: -1 | 1) => {
    if (date === null || today === null) return;
    const next = stepBriefingDate(date, kind, dir, today);
    setPicked(next === today ? null : next);
  };
  const headingId = useId();
  const panelId = useId();
  const tabsRef = useRef<HTMLDivElement>(null);

  const onTabKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const i = BRIEFING_KINDS.indexOf(kind);
    const next = e.key === 'ArrowDown' ? i + 1 : e.key === 'ArrowUp' ? i - 1 : e.key === 'Home' ? 0 : e.key === 'End' ? BRIEFING_KINDS.length - 1 : null;
    if (next === null) return;
    e.preventDefault();
    const k = BRIEFING_KINDS[(next + BRIEFING_KINDS.length) % BRIEFING_KINDS.length]!;
    setKind(k);
    tabsRef.current?.querySelector<HTMLElement>(`[data-kind="${k}"]`)?.focus();
  };

  return (
    <div className={styles.split} data-view="both">
      <section className={styles.listCol} aria-labelledby={headingId}>
        <div className={styles.colHead}>
          <h2 id={headingId} className={styles.colTitle} tabIndex={-1} data-agent-heading="">
            업무 요약 · 회고
          </h2>
        </div>
        <div className={styles.scroll}>
          <div className={styles.dateRow}>
            <IconButton label={kind === 'weekly' ? '전 주' : '전날'} icon={<ChevronLeft size={16} aria-hidden="true" />} aria-disabled={date === null || undefined} onClick={() => step(-1)} />
            {date !== null && today !== null && (
              <MiniCalendar
                value={date}
                max={today}
                onPick={(d) => setPicked(d === today ? null : d)}
                trigger={
                  <button type="button" className={styles.dateText} aria-live="polite" aria-haspopup="dialog">
                    {kind === 'weekly' ? weekRange(date) : dateLabel(date)}
                  </button>
                }
              />
            )}
            <IconButton
              label={kind === 'weekly' ? '다음 주' : '다음 날'}
              icon={<ChevronRight size={16} aria-hidden="true" />}
              aria-disabled={date === null || date === today || undefined}
              onClick={() => step(1)}
            />
            {date !== today && (
              <Button size="sm" variant="ghost" onClick={() => setPicked(null)}>
                오늘
              </Button>
            )}
          </div>
          <div ref={tabsRef} role="tablist" aria-orientation="vertical" aria-label="브리핑 종류" className={styles.vtabs} onKeyDown={onTabKey}>
            {BRIEFING_KINDS.map((k) => (
              <button
                key={k}
                type="button"
                role="tab"
                data-kind={k}
                aria-selected={k === kind}
                aria-controls={panelId}
                tabIndex={k === kind ? 0 : -1}
                className={styles.vtab}
                onClick={() => setKind(k)}
              >
                <span className={styles.vtabTitle}>{BRIEFING_LABEL[k]}</span>
                <span className={styles.vtabSub}>{briefingWhen(k, settings.data)}</span>
              </button>
            ))}
          </div>
        </div>
      </section>
      <section id={panelId} role="tabpanel" aria-label={`${BRIEFING_LABEL[kind]} 본문`} className={styles.detailCol}>
        {date === null ? (
          <div className={styles.reading}>
            <StateRow state="loading" />
          </div>
        ) : (
          <BriefingBody kind={kind} date={date} nowMs={nowMs} source={source} reminders={reminders} />
        )}
      </section>
    </div>
  );
}

function BriefingBody({ kind, date, nowMs, source, reminders }: { kind: BriefingKind; date: string; nowMs: number; source: DashboardSource | undefined; reminders: readonly ReminderItem[] }) {
  const query = useBriefingQuery(kind, date);
  const navigate = useNavigate();
  const openMail = useOpenMail('agent');
  const actions = useTaskActions();
  const toast = useToast();
  const [busy, setBusy] = useState<number | null>(null);

  if (query.isPending) {
    return (
      <div className={styles.reading}>
        <StateRow state="loading" />
      </div>
    );
  }
  if (query.isError && !query.data) {
    return (
      <div className={styles.reading}>
        {query.isNotAvailable ? (
          <p className={styles.emptyText}>업무 요약은 서버에 아직 준비 중입니다.</p>
        ) : (
          <StateRow state="error" text="브리핑을 불러오지 못함" onRetry={() => void query.refetch()} />
        )}
      </div>
    );
  }

  const b = query.data;
  const empty = briefingEmptyText(b, nowMs);
  const keys = new Set(reminders.map((r) => r.key));
  const received = new Set(source?.mails.map((m) => m.id) ?? []);
  const statusOf = (id: number) => source?.tasks.find((t) => t.id === id)?.status;
  const asOf = source?.asOfMs ?? nowMs;

  const open = (it: BriefingItem) => {
    if (it.reminderKey && keys.has(it.reminderKey)) void navigate(reminderPath('all', it.reminderKey));
    else if (it.mailId !== null && received.has(it.mailId)) openMail(it.mailId);
  };
  const canOpen = (it: BriefingItem) => Boolean((it.reminderKey && keys.has(it.reminderKey)) || (it.mailId !== null && received.has(it.mailId)));

  const snooze = async (it: BriefingItem) => {
    if (it.taskId === null || busy !== null) return;
    const until = snoozeOptions(nowMs).find((o) => o.key === 'tomorrow-0830')!.untilMs;
    setBusy(it.taskId);
    try {
      const r = await actions.snooze([it.taskId], until, { source: 'button', toast: false, via: 'reminder:evening' });
      const id = `briefing-snooze-${it.taskId}`;
      toast.show({
        id,
        kind: r.actionId === null ? 'info' : 'undo',
        title: `'${it.title}' ${formatKstShort(until)}까지 연기했습니다`,
        ...(r.actionId === null
          ? {}
          : {
              actionLabel: '실행 취소',
              onAction: () => {
                toast.close(id);
                void actions.undo(r.actionId!, { source: 'button', toast: false }).then(
                  () => toast.show({ kind: 'info', title: '취소했습니다' }),
                  () => toast.show({ kind: 'error', title: '취소하지 못했습니다' }),
                );
              },
            }),
      });
    } catch {
      toast.show({ kind: 'error', title: '연기하지 못했습니다. 다시 시도해 주십시오' });
    } finally {
      setBusy(null);
    }
  };

  return (
    <article className={styles.reading} aria-busy={query.isFetching || undefined}>
      <header className={styles.readingHead}>
        <p className={styles.kicker}>{kind === 'weekly' ? weekRange(b.date) : dateLabel(b.date)}</p>
        <h3 className={styles.readingTitle}>{BRIEFING_LABEL[kind]}</h3>
        {!empty && b.generatedAtMs !== null && <p className={styles.kicker}>{`${formatKstShort(b.generatedAtMs)} 작성`}</p>}
      </header>
      {empty ? (
        <p className={styles.emptyText}>{empty}</p>
      ) : (
        <>
          {b.headline && (
            <div className={styles.headline}>
              <p className={styles.lead}>{b.headline}</p>
              {b.headlineAtMs !== null && <p className={styles.kicker}>{`${formatKstShort(b.headlineAtMs)} 기준 요약 · 아래 목록은 지금 기준`}</p>}
            </div>
          )}
          {b.text && <p className={styles.lead}>{b.text}</p>}
          {b.sections.map((sec) => (
            <section key={sec.id} className={styles.bsection} aria-labelledby={`bs-${sec.id}`}>
              <h4 id={`bs-${sec.id}`} className={styles.bsectionTitle}>
                {sec.title} <span className={styles.colCount}>{sec.count}</span>
              </h4>
              <ul className={styles.blist}>
                {sec.items.map((it, i) => {
                  const due = it.dueAtMs === null ? null : taskDueBadge(it.dueAtMs, null, asOf);
                  const snoozable = it.taskId !== null && canSnoozeToMorning(sec.id, statusOf(it.taskId));
                  const text = (
                    <>
                      <span className={styles.browTitle}>{it.title}</span>
                      {it.detail && <span className={styles.browSub}>{it.detail}</span>}
                    </>
                  );
                  return (
                    <li key={`${sec.id}-${i}`} className={styles.brow}>
                      {canOpen(it) ? (
                        <button type="button" className={styles.browOpen} onClick={() => open(it)}>
                          {text}
                        </button>
                      ) : (
                        <span className={styles.browOpen}>{text}</span>
                      )}
                      {due && <DueLabel kind={due.kind} text={due.text} srText={due.srText ?? undefined} />}
                      {snoozable && (
                        <Button size="sm" variant="ghost" aria-disabled={busy !== null || undefined} onClick={() => void snooze(it)}>
                          내일 아침으로 미루기
                        </Button>
                      )}
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </>
      )}
    </article>
  );
}
