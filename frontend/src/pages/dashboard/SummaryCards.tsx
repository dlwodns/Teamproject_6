import type { DashboardView } from '../../features/tasks/aggregate.ts';
import { VisuallyHidden } from '../../ui/index.ts';
import styles from './SummaryCards.module.css';

function Donut({ percent }: { percent: number | null }) {
  const r = 40;
  const c = 2 * Math.PI * r;
  const p = percent ?? 0;
  return (
    <div className={styles.donut}>
      <svg width="96" height="96" viewBox="0 0 100 100" aria-hidden="true">
        <circle cx="50" cy="50" r={r} fill="none" stroke="var(--c-line)" strokeWidth="11" />
        {p > 0 && (
          <circle cx="50" cy="50" r={r} fill="none" stroke="var(--c-done-bar)" strokeWidth="11" strokeLinecap="round" strokeDasharray={`${(c * p) / 100} ${c}`} />
        )}
      </svg>
      <span className={styles.donutCenter}>{percent === null ? '–' : `${percent}%`}</span>
    </div>
  );
}

export function SummaryCards({ view }: { view: DashboardView }) {
  const { completion, status, due } = view;
  return (
    <section aria-labelledby="summary-title">
      <VisuallyHidden>
        <h2 id="summary-title">요약</h2>
      </VisuallyHidden>
      <div className={styles.summary}>
        <div className={`${styles.stat} ${styles.progress}`}>
          <Donut percent={completion.percent} />
          <div>
            <p className={styles.title}>처리 현황 · 완료율</p>
            <ul className={styles.legend}>
              <li>
                완료<b>{status.done}</b>
              </li>
              <li>
                미처리<b>{status.pending}</b>
              </li>
              {(status.snoozed > 0 || status.excluded > 0) && (
                <li className={styles.note}>
                  나중에 {status.snoozed} · 제외 {status.excluded}
                </li>
              )}
            </ul>
            <p className={styles.note}>완료율 = 완료 ÷ (미처리 + 나중에 + 완료) · 임시 기준</p>
          </div>
        </div>
        <div className={styles.stat}>
          <p className={styles.title}>업무</p>
          <p className={styles.num}>
            {view.taskCount}
            <small className={styles.unit}>개</small>
          </p>
          <p className={styles.note}>
            메일 {view.mailCount}통에서 추출 · 업무 없는 메일 {view.mailsWithoutTask}통
          </p>
        </div>
        <div className={styles.stat}>
          <p className={styles.title}>기한 임박 (오늘 · 내일)</p>
          <p className={styles.num}>
            {due.soon}
            <small className={styles.unit}>개</small>
          </p>
          <p className={styles.note}>
            오늘 마감 · 기한 남음 {due.todayRemaining} · 내일 {due.tomorrow}
          </p>
        </div>
        <div className={styles.stat}>
          <p className={styles.title}>
            <span aria-hidden="true">⚠</span> 기한 지남
          </p>
          <p className={styles.num}>
            {due.overdue}
            <small className={styles.unit}>개</small>
          </p>
          <p className={styles.note}>미처리 업무 중 기한이 기준 시각보다 앞선 것</p>
        </div>
      </div>
    </section>
  );
}
