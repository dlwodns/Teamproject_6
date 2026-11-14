// 에이전트 패널 '리마인더' 탭 (FE-16 · 명세 2절: 예전 '제안' 탭). 리마인더 목록(같은 캐시)의 앞쪽 3건을 제안 카드 모양으로 보인다.
// 제안 카드와 리마인더를 따로 두면 같은 일을 두 번 알리게 되므로 하나로 합쳤다. 전체는 에이전트 화면 리마인더 메뉴(전체 보기 ›).
// 실제 서버에 리마인더 API(BE-12)가 아직 없으면 부르는 쪽(AgentWorkspace)이 지금처럼 제안 카드(SuggestionsTab)를 보인다.
import { useNavigate } from 'react-router';
import { useDashboardQuery } from '../../api/queries.ts';
import { useRemindersQuery } from '../../api/reminders.ts';
import type { TaskId } from '../../api/types.ts';
import { ChevronRight, StateRow } from '../../ui/index.ts';
import { reminderPath } from '../agent/agentRoutes.ts';
import { ExampleList } from '../agent/ExampleList.tsx';
import { FALLBACK_EXAMPLES } from '../agent/agentText.ts';
import { ReminderActions } from './ReminderActions.tsx';
import styles from './ReminderPeek.module.css';
import { MailLink, ReminderSummary, reminderWho } from './ReminderList.tsx';
import { channelItems, splitQuiet } from './reminderModel.ts';
import { useReminderRunner, type CommandRequest } from './useReminderRunner.ts';

export const PEEK_COUNT = 3;

interface Props {
  busy: boolean;
  onCommand: (req: CommandRequest) => void;
  now: () => number;
}

export function ReminderPeek({ busy, onCommand, now }: Props) {
  const query = useRemindersQuery();
  const dashboard = useDashboardQuery();
  const runner = useReminderRunner(onCommand);
  const navigate = useNavigate();
  const taskText = (id: TaskId) => dashboard.data?.tasks.find((t) => t.id === id)?.text ?? null;

  if (query.isPending) return <StateRow state="loading" />;
  if (query.isError && !query.data) return <StateRow state="error" text="리마인더를 불러오지 못함" onRetry={() => void query.refetch()} />;

  const all = channelItems(query.data.items);
  const { active } = splitQuiet(all);
  const muted = new Set(query.data.mutedTypes ?? []);
  const shown = active.slice(0, PEEK_COUNT);

  if (shown.length === 0) {
    return (
      <div className={styles.empty}>
        <p className={styles.emptyTitle}>지금 챙길 리마인더가 없어요</p>
        <p className={styles.emptyHint}>마감 · 참석 업무가 다가오면 이곳에 먼저 표시됩니다. 아래와 같이 요청하실 수도 있습니다.</p>
        <ExampleList examples={FALLBACK_EXAMPLES} busy={busy} onRun={(t) => onCommand({ text: t })} label="예시 명령" />
      </div>
    );
  }

  return (
    <div className={styles.root}>
      <ul className={styles.list} aria-label="리마인더">
        {shown.map((it) => (
          <li key={it.key} className={styles.card} aria-busy={runner.pending.has(it.key) || undefined}>
            <button type="button" className={styles.open} onClick={() => void navigate(reminderPath('all', it.key))}>
              <ReminderSummary item={it} who={reminderWho(it, dashboard.data)} />
            </button>
            {it.mailId !== null && runner.ctx.mailTarget(it.mailId) === 'mail' && (
              <MailLink onClick={() => void runner.run(it, { type: 'open_mail', mailId: it.mailId! })} title={it.title} />
            )}
            <ReminderActions item={it} runner={runner} now={now} muted={muted.has(it.type)} busy={busy} taskText={taskText} withoutMail />
          </li>
        ))}
      </ul>
      <button type="button" className={styles.all} onClick={() => void navigate(reminderPath())}>
        {`리마인더 전체 보기 (${all.length})`}
        <ChevronRight size={16} aria-hidden="true" />
      </button>
    </div>
  );
}
