// 더보기 사이드바(LP) 내용 (UX-D12). 앱 틀의 패널 자리에서 그려지므로 데이터를 직접 읽는다 —
// 사이드바 안에서 완료해도, 대시보드에서 완료해도 같은 캐시를 보므로 바로 갱신된다.
import { CHECK_LANES, moreTitle } from '../../features/tasks/aggregate.ts';
import { TaskRow, TaskRowList } from '../../features/tasks/TaskRow.tsx';
import { StateRow } from '../../ui/index.ts';
import { AwaitingList, CheckItemList } from './InfoRows.tsx';
import styles from './MoreContent.module.css';
import { isTypeKey, type MoreKey } from './more.ts';
import { useDashboardModel } from './useDashboardModel.ts';

export function MoreContent({ which }: { which: MoreKey }) {
  const state = useDashboardModel();
  if (state.kind === 'loading') return <StateRow state="loading" />;
  if (state.kind === 'error') return <StateRow state="error" onRetry={state.retry} />;
  const { model } = state;

  if (which === 'checks') {
    if (!model.checks) return <StateRow state="empty" />;
    const checks = model.checks;
    return (
      <div className={styles.body}>
        {CHECK_LANES.map((lane) => (
          <div key={lane}>
            <h3 className={styles.group}>{moreTitle(lane, checks[lane].length)}</h3>
            {checks[lane].length === 0 ? <StateRow state="empty" /> : <CheckItemList items={checks[lane]} />}
          </div>
        ))}
      </div>
    );
  }

  if (which === 'awaiting') {
    const list = model.awaiting ?? [];
    return <div className={styles.body}>{list.length === 0 ? <StateRow state="empty" /> : <AwaitingList items={list} />}</div>;
  }

  const rows = isTypeKey(which) ? model.types[which] : which === 'favorites' ? model.favorites : model.urgent;
  return (
    <div className={styles.body}>
      {rows.length === 0 ? (
        <StateRow state="empty" />
      ) : (
        <TaskRowList>
          {rows.map((r) => (
            <TaskRow key={r.id} row={r} showType />
          ))}
        </TaskRowList>
      )}
    </div>
  );
}
