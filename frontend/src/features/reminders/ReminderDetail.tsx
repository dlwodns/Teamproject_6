// 리마인더 상세 (FE-16 · 명세 5절 오른쪽 칸). 11-15: 목록 카드와 같은 순서로 읽힌다.
//   업무 유형 · 보낸 사람 · 업무(제목 h2) · 캐치봇 메시지 → 근거 문장 → 메일 열기 → 버튼 줄
// - 원본 메일 칸 · 이 항목 기록은 뺐다(보낸 사람 · 메일 열기와 겹치고 업무에 쓰지 않는다)
// - 근거 문장은 형광펜 모양(UX-D16). 메일로 가는 길은 [메일 열기] 하나
// - 버튼 줄은 오른쪽 정렬, 보조 → 주. 빨강 채움 없음(확정 동작이 아님, UX-D18)
import { forwardRef } from 'react';
import type { ReminderItem } from '../../api/contract.ts';
import type { DashboardSource, TaskId } from '../../api/types.ts';
import { ChevronLeft } from '../../ui/index.ts';
import { ReminderActions } from './ReminderActions.tsx';
import styles from './ReminderDetail.module.css';
import { MailLink, ReminderSummary, reminderWho } from './ReminderList.tsx';
import type { ReminderRunner } from './useReminderRunner.ts';

interface Props {
  item: ReminderItem;
  runner: ReminderRunner;
  source: DashboardSource | undefined;
  now: () => number;
  muted: boolean;
  busy: boolean;
  /** 좁은 화면: 목록으로 돌아가기 */
  onBack?: () => void;
  headingId: string;
}

export const ReminderDetail = forwardRef<HTMLHeadingElement, Props>(function ReminderDetail(
  { item, runner, source, now, muted, busy, onBack, headingId },
  ref,
) {
  const mailPlan = item.mailId === null ? null : runner.ctx.mailTarget(item.mailId);
  const taskText = (id: TaskId) => source?.tasks.find((t) => t.id === id)?.text ?? null;
  const openMail = () => {
    if (item.mailId === null) return;
    void runner.run(item, mailPlan === 'mail' ? { type: 'open_mail', mailId: item.mailId } : { type: 'open_waiting' });
  };

  return (
    <article className={styles.detail} aria-labelledby={headingId}>
      {onBack && (
        <button type="button" className={styles.back} onClick={onBack}>
          <ChevronLeft size={16} aria-hidden="true" />
          뒤로
        </button>
      )}
      <header className={styles.head}>
        <ReminderSummary
          block
          item={item}
          who={reminderWho(item, source)}
          title={
            <h2 id={headingId} ref={ref} tabIndex={-1} className={styles.title} data-agent-detail-heading="">
              {item.title}
            </h2>
          }
        />
      </header>

      {item.evidence && (
        <figure className={styles.evidence}>
          <figcaption className={styles.label}>근거 문장</figcaption>
          <blockquote className={styles.quote}>
            <mark className={styles.mark}>{item.evidence}</mark>
          </blockquote>
        </figure>
      )}

      {mailPlan && <MailLink onClick={openMail} title={item.title} />}

      <ReminderActions item={item} runner={runner} now={now} muted={muted} busy={busy} taskText={taskText} withoutMail className={styles.actions} />
    </article>
  );
});
