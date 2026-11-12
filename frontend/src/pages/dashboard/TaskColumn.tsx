// U1 긴급 · Y1~Y4 유형 칸 (components.md 4.2). 기본 줄 수만 보이고 나머지는 '+N건 더보기' → 오른쪽 사이드바.
import type { TaskRowModel } from '../../features/tasks/aggregate.ts';
import { TaskRow, TaskRowList } from '../../features/tasks/TaskRow.tsx';
import { StateRow } from '../../ui/index.ts';
import { DashCard, ExpandButton, MoreButton } from './DashCard.tsx';

export type LoadStatus = { kind: 'loading' } | { kind: 'error'; retry: () => void } | { kind: 'ready' };

interface Props {
  name: string;
  status: LoadStatus;
  rows: readonly TaskRowModel[];
  limit: number;
  /** 긴급 칸: 제목 앞 점 + 둘째 줄에 유형 */
  urgent?: boolean;
  onMore: () => void;
}

export function TaskColumn({ name, status, rows, limit, urgent = false, onMore }: Props) {
  const ready = status.kind === 'ready';
  const hidden = rows.length - limit;
  return (
    <DashCard
      title={name}
      dot={urgent}
      count={ready ? rows.length : null}
      tools={ready && rows.length > 0 ? <MoreButton name={name} onClick={onMore} /> : undefined}
    >
      {status.kind === 'loading' && <StateRow state="loading" />}
      {status.kind === 'error' && <StateRow state="error" onRetry={status.retry} />}
      {ready && rows.length === 0 && <StateRow state="empty" />}
      {ready && rows.length > 0 && (
        <>
          <TaskRowList>
            {rows.slice(0, limit).map((r) => (
              <TaskRow key={r.id} row={r} showType={urgent} />
            ))}
          </TaskRowList>
          {hidden > 0 && <ExpandButton name={name} hidden={hidden} onClick={onMore} />}
        </>
      )}
    </DashCard>
  );
}
