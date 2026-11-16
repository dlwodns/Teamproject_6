// 작은 달력 (11-15, 업무 요약 · 회고의 날짜 고르기). 날짜 글자를 누르면 팝오버로 열리고, 날을 고르면 닫힌다.
// 달 그리드는 캘린더 화면과 같은 함수(features/calendar/calendarModel)를 쓴다. 오늘 뒤 날은 고를 수 없다(‹ › 규칙과 같음).
import { useState, type ReactElement } from 'react';
import { monthGrid, monthTitle, shiftMonth, WEEKDAYS, type Month } from '../../features/calendar/calendarModel.ts';
import { ChevronLeft, ChevronRight, IconButton, Popover, cx } from '../../ui/index.ts';
import styles from './MiniCalendar.module.css';

const monthOfKey = (key: string): Month => ({ year: Number(key.slice(0, 4)), month: Number(key.slice(5, 7)) });
const monthIndex = (m: Month) => m.year * 12 + m.month;

interface Props {
  /** 여는 버튼(날짜 글자) */
  trigger: ReactElement;
  /** 고른 날 'YYYY-MM-DD' */
  value: string;
  /** 고를 수 있는 마지막 날(오늘) */
  max: string;
  onPick: (date: string) => void;
}

export function MiniCalendar({ trigger, value, max, onPick }: Props) {
  const [open, setOpen] = useState(false);
  const [shown, setShown] = useState<Month>(() => monthOfKey(value));
  const atMax = monthIndex(shown) >= monthIndex(monthOfKey(max));

  return (
    <Popover
      trigger={trigger}
      title={monthTitle(shown)}
      align="start"
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) setShown(monthOfKey(value)); // 열 때마다 고른 날의 달부터
      }}
      headerExtra={
        <span className={styles.nav}>
          <IconButton label="이전 달" icon={<ChevronLeft size={16} aria-hidden="true" />} onClick={() => setShown((m) => shiftMonth(m, -1))} />
          <IconButton
            label="다음 달"
            icon={<ChevronRight size={16} aria-hidden="true" />}
            aria-disabled={atMax || undefined}
            onClick={() => !atMax && setShown((m) => shiftMonth(m, 1))}
          />
        </span>
      }
    >
      <div className={styles.grid} role="group" aria-label={monthTitle(shown)}>
        {WEEKDAYS.map((w) => (
          <span key={w} className={styles.weekday} aria-hidden="true">
            {w}
          </span>
        ))}
        {monthGrid(shown).map((c) => {
          const future = c.key > max;
          return (
            <button
              key={c.key}
              type="button"
              className={cx(styles.day, !c.inMonth && styles.out)}
              disabled={future}
              aria-pressed={c.key === value}
              aria-current={c.key === max ? 'date' : undefined}
              aria-label={`${Number(c.key.slice(5, 7))}월 ${c.date}일 ${WEEKDAYS[c.weekday]}요일`}
              onClick={() => {
                onPick(c.key);
                setOpen(false);
              }}
            >
              {c.date}
            </button>
          );
        })}
      </div>
    </Popover>
  );
}
