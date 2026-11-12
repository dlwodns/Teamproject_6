// N1 업무 수 (UX-D2 · wireframe 13-1): 메일을 받은 날 기준 전체 · 처리 · 미처리 건수만.
// 기간 [오늘 | 이번 주 | 날짜]를 바꿔도 2열 칸은 그대로다(2열은 항상 '지금 남은 업무'). 막대는 처리 비율(장식).
import { useState } from 'react';
import {
  countReceived,
  defaultPickedDay,
  doneRatioPercent,
  PERIOD_OPTIONS,
  periodLabel,
  periodRange,
  stepDay,
  type DashboardModel,
  type Period,
} from '../../features/tasks/aggregate.ts';
import { formatKstDay } from '../../features/tasks/deadline.ts';
import { ChevronLeft, ChevronRight, IconButton, SegmentedControl, StateRow } from '../../ui/index.ts';
import styles from './CountCard.module.css';
import { DashCard } from './DashCard.tsx';
import type { LoadStatus } from './TaskColumn.tsx';

interface Props {
  status: LoadStatus;
  model: DashboardModel | null;
}

export function CountCard({ status, model }: Props) {
  const [period, setPeriod] = useState<Period>('today');
  const [picked, setPicked] = useState<number | null>(null);

  const today = model?.today ?? null;
  const pickedDay = picked ?? (today === null ? 0 : defaultPickedDay(today));
  const range = today === null ? null : periodRange(period, today, pickedDay);
  const counts = model && range ? countReceived(model, range) : null;

  const segment = (
    <SegmentedControl
      label="받은 날 기간"
      options={PERIOD_OPTIONS}
      value={period}
      onValueChange={(p) => {
        setPeriod(p);
        if (p === 'day' && picked === null && today !== null) setPicked(defaultPickedDay(today));
      }}
    />
  );

  return (
    <DashCard title="업무 수" tools={segment}>
      {period === 'day' && today !== null && (
        <div className={styles.stepper}>
          <IconButton label="전날" icon={<ChevronLeft size={20} aria-hidden="true" />} onClick={() => setPicked(stepDay(pickedDay, -1, today))} />
          <span className={styles.stepDate}>{formatKstDay(pickedDay)}</span>
          <IconButton
            label="다음 날"
            icon={<ChevronRight size={20} aria-hidden="true" />}
            disabled={pickedDay >= today}
            onClick={() => setPicked(stepDay(pickedDay, 1, today))}
          />
        </div>
      )}
      {status.kind === 'loading' && <StateRow state="loading" />}
      {status.kind === 'error' && <StateRow state="error" onRetry={status.retry} />}
      {status.kind === 'ready' && counts && range && (
        <div className={styles.totals}>
          <p className={styles.eyebrow}>받은 날 · {periodLabel(period, range)}</p>
          <p className={styles.big}>
            <strong className={styles.bigNum}>{counts.total}</strong>
            <span className={styles.unit}>건</span>
          </p>
          <dl className={styles.split}>
            <div className={styles.cell}>
              <dt className={styles.cellName}>처리</dt>
              <dd className={styles.cellNum}>{counts.done}</dd>
            </div>
            <div className={styles.cell}>
              <dt className={styles.cellName}>미처리</dt>
              <dd className={styles.cellNum}>{counts.open}</dd>
            </div>
          </dl>
          <div className={styles.bar} aria-hidden="true">
            <i className={styles.barFill} style={{ width: `${doneRatioPercent(counts)}%` }} />
          </div>
        </div>
      )}
      {status.kind === 'ready' && model && model.unclassifiedMails > 0 && (
        <StateRow state="pending">분류 대기 {model.unclassifiedMails}건 · 분석이 끝나면 반영</StateRow>
      )}
    </DashCard>
  );
}
