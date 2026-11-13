// 리마인더 상세 (FE-16 · 명세 5절 오른쪽 칸): 제목 · 유형 · 이유 · 근거 문장 · 버튼 줄 · 원본 메일 · 이 항목 기록.
// - 근거 문장은 형광펜 모양(UX-D16)으로 보이고, 누르면 메일 화면의 그 메일로 간다(메일 화면이 그 문장을 칠한다)
// - 버튼 줄은 오른쪽 정렬, 보조 → 주. 빨강 채움 없음(확정 동작이 아님, UX-D18)
// - 기한 라벨은 대시보드와 같은 글자 · 색(UX-D10). 이 칸의 색 신호는 이것 하나다
import { forwardRef } from 'react';
import type { ReminderItem } from '../../api/contract.ts';
import type { DashboardSource, TaskId } from '../../api/types.ts';
import { formatKstShort } from '../../lib/snooze.ts';
import { ChevronLeft, ChevronRight, DueLabel } from '../../ui/index.ts';
import { senderLookup } from '../agent/agentText.ts';
import { taskDueBadge } from '../tasks/deadline.ts';
import { ReminderActions } from './ReminderActions.tsx';
import styles from './ReminderDetail.module.css';
import { counterpartText, historyLine, TYPE_LABEL, GROUP_LABEL } from './reminderModel.ts';
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

function SourceMail({ item, source }: { item: ReminderItem; source: DashboardSource | undefined }) {
  if (item.mailId === null || !source) return null;
  const mail = source.mails.find((m) => m.id === item.mailId);
  if (mail) {
    const who = senderLookup(source)(mail.id) ?? mail.sender;
    return (
      <dl className={styles.facts}>
        <dt>원본 메일</dt>
        <dd>
          <span className={styles.subject}>{mail.subject}</span>
          <span className={styles.meta}>{`${who} · ${formatKstShort(mail.receivedAtMs)}`}</span>
        </dd>
      </dl>
    );
  }
  const sent = source.awaiting?.find((a) => a.mailId === item.mailId);
  if (sent) {
    return (
      <dl className={styles.facts}>
        <dt>보낸 메일</dt>
        <dd>
          <span className={styles.subject}>{sent.subject}</span>
          <span className={styles.meta}>{`${sent.to}에게 · ${formatKstShort(sent.sentAtMs)}`}</span>
        </dd>
      </dl>
    );
  }
  return null;
}

export const ReminderDetail = forwardRef<HTMLHeadingElement, Props>(function ReminderDetail(
  { item, runner, source, now, muted, busy, onBack, headingId },
  ref,
) {
  const due = item.dueAtMs === null ? null : taskDueBadge(item.dueAtMs, null, source?.asOfMs ?? now());
  const who = counterpartText(item);
  const mailPlan = item.mailId === null ? null : runner.ctx.mailTarget(item.mailId);
  const taskText = (id: TaskId) => source?.tasks.find((t) => t.id === id)?.text ?? null;
  const openEvidence = () => {
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
        <p className={styles.kicker}>
          {GROUP_LABEL[item.group]} · {TYPE_LABEL[item.type]}
          {who && ` · ${who}`}
        </p>
        <h2 id={headingId} ref={ref} tabIndex={-1} className={styles.title}>
          {item.title}
        </h2>
        {due && (
          <div className={styles.due}>
            <DueLabel kind={due.kind} text={due.text} srText={due.srText ?? undefined} fullTime={due.fullTime ?? undefined} />
          </div>
        )}
      </header>

      <p className={styles.reason}>{item.reason}</p>

      {item.evidence && (
        <figure className={styles.evidence}>
          <figcaption className={styles.label}>근거 문장</figcaption>
          {mailPlan ? (
            <button type="button" className={styles.quote} onClick={openEvidence}>
              <mark className={styles.mark}>{item.evidence}</mark>
              <span className={styles.go}>
                메일에서 보기
                <ChevronRight size={16} aria-hidden="true" />
              </span>
            </button>
          ) : (
            <blockquote className={styles.quote}>
              <mark className={styles.mark}>{item.evidence}</mark>
            </blockquote>
          )}
        </figure>
      )}

      <ReminderActions item={item} runner={runner} now={now} muted={muted} busy={busy} taskText={taskText} className={styles.actions} />

      <div className={styles.more}>
        <SourceMail item={item} source={source} />
        <dl className={styles.facts}>
          <dt>이 항목 기록</dt>
          <dd>
            <span className={styles.meta}>{historyLine(item)}</span>
          </dd>
        </dl>
      </div>
    </article>
  );
});
