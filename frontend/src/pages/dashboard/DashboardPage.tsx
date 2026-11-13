// 대시보드 v3.1 (wireframe 13-1 · components.md 4.2 · UX-D1 ~ UX-D3 · UX-D11 · UX-D12).
// 1열: N1 업무 수 → W1 응답 대기 → I1 확인사항. 2열: U1 긴급 → Y1~Y4 유형 칸. 1024px 미만은 이 순서로 한 열.
// 화면 제목 줄 · 설명 줄은 없다(UX-D11). 제목은 화면 읽기용으로만 두고 메뉴 이동 때 포커스를 받는다.
import { useCallback, useEffect, useState } from 'react';
import { dashboardDataMode } from '../../api/client.ts';
import { usePanel } from '../../app/panel.tsx';
import { TYPE_COLUMNS, TYPE_LIMIT, URGENT_LIMIT } from '../../features/tasks/aggregate.ts';
import { CountCard } from './CountCard.tsx';
import styles from './DashboardPage.module.css';
import { MoreContent } from './MoreContent.tsx';
import { moreTitleOf, type MoreKey } from './more.ts';
import { CheckItemsCard, WaitingCard } from './SideCards.tsx';
import { TaskColumn, type LoadStatus } from './TaskColumn.tsx';
import { useDashboardModel } from './useDashboardModel.ts';

export function DashboardPage() {
  const state = useDashboardModel();
  const model = state.kind === 'ready' ? state.model : null;
  const status: LoadStatus =
    state.kind === 'ready' ? { kind: 'ready' } : state.kind === 'loading' ? { kind: 'loading' } : { kind: 'error', retry: state.retry };
  const isMock = state.kind === 'ready' ? state.origin.kind === 'mock' : dashboardDataMode === 'mock';

  // 더보기 사이드바: 어느 칸을 열었는지 기억해 완료 · 다시 불러오기 뒤 제목의 건수를 맞춘다
  const { kind: panelKind, payload, open } = usePanel();
  const [moreKey, setMoreKey] = useState<MoreKey | null>(null);

  const openMore = useCallback(
    (key: MoreKey) => {
      open('more', { title: moreTitleOf(key, model), content: <MoreContent which={key} /> });
      setMoreKey(key);
    },
    [open, model],
  );

  useEffect(() => {
    if (panelKind !== 'more') {
      if (moreKey !== null) setMoreKey(null);
      return;
    }
    if (moreKey === null || !payload) return;
    const title = moreTitleOf(moreKey, model);
    // 같은 패널 부품에 제목만 바꿔 넘긴다(다시 열지 않으므로 포커스가 옮겨지지 않는다)
    if (title !== payload.title) open('more', { title, content: payload.content });
  }, [panelKind, payload, moreKey, model, open]);

  return (
    <>
      <h1 id="page-title" className="sr-only" tabIndex={-1}>
        대시보드
      </h1>
      {isMock && (
        <p className={styles.origin}>
          <span className={styles.mockChip} title={state.kind === 'ready' && state.origin.kind === 'mock' ? `${state.origin.dataset} · ${state.origin.version}` : undefined}>
            모의 데이터
          </span>
        </p>
      )}
      <div className={styles.dash}>
        <div className={styles.col}>
          <CountCard status={status} model={model} />
          {model?.awaiting && <WaitingCard items={model.awaiting} onMore={() => openMore('awaiting')} />}
          {model?.checks && <CheckItemsCard checks={model.checks} onMore={() => openMore('checks')} />}
        </div>
        <div className={styles.col}>
          <TaskColumn name="긴급" urgent status={status} rows={model?.urgent ?? []} limit={URGENT_LIMIT} onMore={() => openMore('urgent')} />
          <div className={styles.types}>
            {TYPE_COLUMNS.map((key) => (
              <TaskColumn key={key} name={key} status={status} rows={model?.types[key] ?? []} limit={TYPE_LIMIT} onMore={() => openMore(key)} />
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
