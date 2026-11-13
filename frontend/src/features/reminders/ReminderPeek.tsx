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
import { secondLine, splitQuiet, visibleItems } from './reminderModel.ts';
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

  const all = visibleItems(query.data.items);
  const { active } = splitQuiet(all);
  const muted = new Set(query.data.mutedTypes ?? []);
  const shown = active.slice(0, PEEK_COUNT);

  if (shown.length === 0) {
    return (
      <div className={styles.empty}>
        <p className={styles.emptyTitle}>지금 챙길 리마인더가 없어요</p>
        <p className={styles.emptyHint}>기한 · 답 기다림 · 약속이 생기면 여기에 먼저 보여요. 이렇게 말해 볼 수도 있어요.</p>
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
              <span className={styles.title}>{it.title}</span>
              <span className={styles.sub}>{secondLine(it)}</span>
            </button>
            <ReminderActions item={it} runner={runner} now={now} muted={muted.has(it.type)} busy={busy} taskText={taskText} />
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
