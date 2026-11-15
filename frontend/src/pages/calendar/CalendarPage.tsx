// 캘린더 화면 #/calendar (FE-12 · D56). 달력만 보고 언제 무엇을 해야 하는지 알 수 있게 한다.
// - 왼쪽: 달 보기(일요일 시작 6주). 칸마다 그날 항목을 시각 · 제목으로 세 줄까지, 넘치면 '+N'.
// - 오른쪽: 고른 날의 목록. 종류(일정 · 회의 · 기한 · 다시 알림)는 색이 아니라 글자로 구분한다(색 신호는 하나, design_system).
// - 회의(시각이 메일에 적힌 것만)는 [캘린더에 넣기], 넣은 일정은 [빼기]. 둘 다 토스트의 [실행 취소]로 돌린다(D50).
// - 메일에 시각이 없던 기한은 시각을 비운다(지어낸 18:00을 보이지 않는다, BE-D24).
// - 서버에 캘린더가 아직 없으면(BE-15 머지 전 실제 모드) '준비 중'만 보인다.
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { Link } from 'react-router';
import type { CalendarItem } from '../../api/contract.ts';
import { useCalendarQuery, useDashboardQuery } from '../../api/queries.ts';
import { ComingSoon } from '../../components/ComingSoon.tsx';
import {
  byDay,
  canAddMeeting,
  dayTitle,
  gridRange,
  KIND_LABEL,
  keyOfMs,
  monthGrid,
  monthOf,
  addRequestOf,
  monthTitle,
  shiftMonth,
  shortTime,
  timeRange,
  WEEKDAYS,
  type DayCell,
  type Month,
} from '../../features/calendar/calendarModel.ts';
import { useCalendarActions } from '../../features/calendar/useCalendarActions.ts';
import { mailPath } from '../../features/mail/routes.ts';
import { Button, ChevronLeft, ChevronRight, IconButton, StateRow, useToast } from '../../ui/index.ts';
import styles from './CalendarPage.module.css';

const IN_CELL = 3; // 칸 안에 보이는 줄 수

function AgendaRow({ item, onAdd, onRemove }: { item: CalendarItem; onAdd: (it: CalendarItem) => void; onRemove: (it: CalendarItem) => void }) {
  return (
    <li className={styles.row} data-kind={item.kind}>
      <span className={styles.rowTime} data-quiet={!item.timeStated || undefined}>
        {timeRange(item)}
      </span>
      <div className={styles.rowMain}>
        <span className={styles.rowKind}>{KIND_LABEL[item.kind]}</span>
        <span className={styles.rowTitle}>{item.title}</span>
        {item.mailId !== null && item.subject && (
          <Link className={styles.rowMail} to={mailPath('inbox', item.mailId)}>
            {item.subject}
          </Link>
        )}
      </div>
      {canAddMeeting(item) && (
        <Button size="sm" onClick={() => onAdd(item)}>
          캘린더에 넣기
        </Button>
      )}
      {item.kind === 'event' && item.eventId !== null && (
        <Button size="sm" onClick={() => onRemove(item)}>
          빼기
        </Button>
      )}
    </li>
  );
}

function DayButton({
  cell,
  items,
  today,
  selected,
  onSelect,
}: {
  cell: DayCell;
  items: CalendarItem[];
  today: boolean;
  selected: boolean;
  onSelect: (key: string) => void;
}) {
  const extra = items.length - IN_CELL;
  const label = `${dayTitle(cell)}${today ? ' 오늘' : ''}, ${items.length > 0 ? `${items.length}건` : '없음'}`;
  return (
    <button
      type="button"
      className={styles.cell}
      data-out={!cell.inMonth || undefined}
      data-today={today || undefined}
      data-selected={selected || undefined}
      data-sun={cell.weekday === 0 || undefined}
      aria-label={label}
      aria-pressed={selected}
      tabIndex={selected ? 0 : -1}
      data-key={cell.key}
      onClick={() => onSelect(cell.key)}
    >
      <span className={styles.date} aria-hidden="true">
        {cell.date}
      </span>
      <span className={styles.lines} aria-hidden="true">
        {items.slice(0, IN_CELL).map((it, i) => (
          <span key={i} className={styles.line} data-kind={it.kind}>
            {shortTime(it) && <span className={styles.lineTime}>{shortTime(it)}</span>}
            <span className={styles.lineTitle}>{it.title}</span>
          </span>
        ))}
        {extra > 0 && <span className={styles.more}>+{extra}</span>}
      </span>
    </button>
  );
}

export function CalendarPage() {
  const asOfMs = useDashboardQuery().data?.asOfMs;
  const [picked, setPicked] = useState<Month | null>(null);
  const month = picked ?? monthOf(asOfMs ?? Date.now());
  const { year, month: mon } = month;
  const cells = useMemo(() => monthGrid({ year, month: mon }), [year, mon]);
  const range = gridRange(cells);
  const q = useCalendarQuery(range.start, range.end);
  const actions = useCalendarActions();
  const toast = useToast();
  const gridRef = useRef<HTMLDivElement>(null);

  const todayKey = keyOfMs(q.data?.asOfMs ?? asOfMs ?? Date.now());
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const selected = cells.find((c) => c.key === selectedKey) ?? cells.find((c) => c.key === todayKey) ?? cells.find((c) => c.inMonth)!;
  const days = useMemo(() => byDay(q.data?.items ?? []), [q.data]);
  const agenda = days.get(selected.key) ?? [];

  // 키보드: 칸 사이를 화살표(하루 · 한 주)로 옮긴다. 달 밖으로 나가면 그 달로 넘긴다
  const [focusKey, setFocusKey] = useState<string | null>(null);
  useEffect(() => {
    if (!focusKey) return;
    gridRef.current?.querySelector<HTMLButtonElement>(`[data-key="${focusKey}"]`)?.focus();
    setFocusKey(null);
  }, [focusKey, cells]);
  const onGridKey = (e: KeyboardEvent) => {
    const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[e.key];
    if (step === undefined) return;
    e.preventDefault();
    const next = cells.find((c) => c.day === selected.day + step);
    const key = next?.key ?? keyOfMs(Date.parse(`${selected.key}T12:00:00+09:00`) + step * 86_400_000);
    if (!next || !next.inMonth) setPicked(monthOf(Date.parse(`${key}T12:00:00+09:00`)));
    setSelectedKey(key);
    setFocusKey(key);
  };

  const moveMonth = (by: number) => {
    const m = shiftMonth(month, by);
    setPicked(m);
    setSelectedKey(null);
  };
  const goToday = () => {
    setPicked(null);
    setSelectedKey(null);
  };

  const fail = (e: unknown) =>
    toast.show({ kind: 'error', title: (e as { status?: number }).status === 409 ? '이미 캘린더에 있어요' : '바꾸지 못했어요' });
  const undoToast = (title: string, actionId: number) =>
    toast.show({
      kind: 'undo',
      title,
      onAction: () => void actions.undo(actionId).catch(() => toast.show({ kind: 'error', title: '되돌리지 못했어요' })),
    });
  const add = (it: CalendarItem) =>
    void actions
      .add(addRequestOf(it))
      .then((r) => undoToast(`'${r.item.title}'을(를) 캘린더에 넣었어요`, r.actionId))
      .catch(fail);
  const remove = (it: CalendarItem) =>
    void actions
      .remove(it.eventId!)
      .then((r) => undoToast(`'${r.item.title}'을(를) 캘린더에서 뺐어요`, r.actionId))
      .catch(fail);

  if (q.isNotAvailable) {
    return (
      <ComingSoon title="캘린더">
        <p>서버에 캘린더가 아직 없어요. 기한 · 다시 알림 · 회의 · 넣은 일정을 날짜별로 보여 줄 자리예요.</p>
      </ComingSoon>
    );
  }

  return (
    <div className={styles.page}>
      <section className={styles.month} aria-labelledby="page-title">
        <div className={styles.head}>
          <h1 id="page-title" className={styles.title} tabIndex={-1}>
            캘린더
          </h1>
          <div className={styles.nav}>
            <IconButton label="지난달" icon={<ChevronLeft size={20} aria-hidden="true" />} onClick={() => moveMonth(-1)} />
            <span className={styles.monthTitle} aria-live="polite">
              {monthTitle(month)}
            </span>
            <IconButton label="다음 달" icon={<ChevronRight size={20} aria-hidden="true" />} onClick={() => moveMonth(1)} />
            <Button size="sm" onClick={goToday}>
              오늘
            </Button>
          </div>
        </div>
        {q.isError && !q.data ? (
          <StateRow state="error" onRetry={() => void q.refetch()} />
        ) : (
          <div className={styles.grid} ref={gridRef} onKeyDown={onGridKey} aria-busy={q.isPending || undefined}>
            {WEEKDAYS.map((w, i) => (
              <span key={w} className={styles.weekday} data-sun={i === 0 || undefined} aria-hidden="true">
                {w}
              </span>
            ))}
            {cells.map((c) => (
              <DayButton key={c.key} cell={c} items={days.get(c.key) ?? []} today={c.key === todayKey} selected={c.key === selected.key} onSelect={setSelectedKey} />
            ))}
          </div>
        )}
      </section>

      <section className={styles.day} aria-labelledby="calendar-day-title">
        <h2 id="calendar-day-title" className={styles.dayTitle}>
          {dayTitle(selected)}
          {selected.key === todayKey && <span className={styles.todayTag}>오늘</span>}
        </h2>
        {q.isPending ? (
          <StateRow state="loading" />
        ) : agenda.length === 0 ? (
          <StateRow state="empty" text="이날은 할 일이 없어요" />
        ) : (
          <ul className={styles.rows} aria-label={`${dayTitle(selected)} ${agenda.length}건`}>
            {agenda.map((it) => (
              <AgendaRow key={`${it.kind}-${it.eventId ?? it.taskId ?? it.mailId}-${it.startMs}`} item={it} onAdd={add} onRemove={remove} />
            ))}
          </ul>
        )}
        <p className={styles.legend}>
          일정 = 캘린더에 넣은 것 · 회의 = 메일 속 회의 · 기한 = 업무 마감 · 다시 알림 = 나중에로 미룬 업무
        </p>
      </section>
    </div>
  );
}
