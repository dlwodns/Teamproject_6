// U1 긴급 · F1 즐겨찾기 · Y1~Y4 유형 칸 (components.md 4.2). 5줄 높이로 보이고 안에서 스크롤한다. 오른쪽 위 더보기 → 오른쪽 사이드바. 칸 머리 숫자 = 보이는 줄 수(UX-D20).
import type { TaskRowModel } from '../../features/tasks/aggregate.ts';
import { TaskRow, TaskRowList } from '../../features/tasks/TaskRow.tsx';
import { StateRow } from '../../ui/index.ts';
import { DashCard, MoreButton, ScrollArea } from './DashCard.tsx';

export type LoadStatus = { kind: 'loading' } | { kind: 'error'; retry: () => void } | { kind: 'ready' };

interface Props {
  name: string;
  status: LoadStatus;
  rows: readonly TaskRowModel[];
  /** 긴급 칸: 제목 앞 점 */
  urgent?: boolean;
  /** 둘째 줄에 유형을 덧붙인다(긴급 · 즐겨찾기 칸) */
  showType?: boolean;
  /** 빈 칸 문구(기본 '없음') */
  emptyText?: string;
  onMore: () => void;
}

export function TaskColumn({ name, status, rows, urgent = false, showType = urgent, emptyText, onMore }: Props) {
  const ready = status.kind === 'ready';
  return (
    <DashCard
      title={name}
      dot={urgent}
      count={ready ? rows.length : null}
      tools={ready && rows.length > 0 ? <MoreButton name={name} onClick={onMore} /> : undefined}
    >
      {status.kind === 'loading' && <StateRow state="loading" />}
      {status.kind === 'error' && <StateRow state="error" onRetry={status.retry} />}
      {ready && rows.length === 0 && <StateRow state="empty" text={emptyText} />}
      {ready && rows.length > 0 && (
        <ScrollArea>
          <TaskRowList>
            {rows.map((r) => (
              <TaskRow key={r.id} row={r} showType={showType} />
            ))}
          </TaskRowList>
        </ScrollArea>
      )}
    </DashCard>
  );
}
