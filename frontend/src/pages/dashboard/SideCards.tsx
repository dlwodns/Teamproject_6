// 1열 아래 카드: W1 응답 대기 · I1 확인사항 (UX-D1 · UX-D2). 서버가 그 칸을 보내지 않으면 부르는 쪽이 카드를 숨긴다.
import { useState } from 'react';
import type { Awaiting } from '../../api/types.ts';
import { CHECK_LANES, CHECK_LIMIT, type CheckItem, type CheckLane } from '../../features/tasks/aggregate.ts';
import { StateRow, Tabs } from '../../ui/index.ts';
import { DashCard, ExpandButton } from './DashCard.tsx';

const WAITING_LIMIT = 3;
import { AwaitingList, CheckItemList } from './InfoRows.tsx';
import styles from './SideCards.module.css';

// '더보기'는 숨긴 건수와 함께 목록 아래 한 곳에만 둔다(카드 머리 링크와 겹치지 않게 · Geist show more)
export function WaitingCard({ items, onMore }: { items: readonly Awaiting[]; onMore: () => void }) {
  const hidden = items.length - WAITING_LIMIT;
  return (
    <DashCard title="응답 대기" count={items.length}>
      {items.length === 0 ? (
        <StateRow state="empty" />
      ) : (
        <>
          <AwaitingList items={items.slice(0, WAITING_LIMIT)} />
          {hidden > 0 && <ExpandButton name="응답 대기" hidden={hidden} onClick={onMore} />}
        </>
      )}
    </DashCard>
  );
}

export function CheckItemsCard({ checks, onMore }: { checks: Record<CheckLane, CheckItem[]>; onMore: () => void }) {
  const [tab, setTab] = useState<CheckLane>('확인');
  const total = checks.확인.length + checks.참고.length;
  return (
    <DashCard title="확인사항" count={total}>
      <Tabs<CheckLane>
        className={styles.tabs}
        label="확인사항 종류"
        value={tab}
        onValueChange={setTab}
        items={CHECK_LANES.map((lane) => {
          const list = checks[lane];
          const hidden = list.length - CHECK_LIMIT;
          return {
            value: lane,
            label: lane,
            count: list.length,
            content:
              list.length === 0 ? (
                <StateRow state="empty" />
              ) : (
                <>
                  <CheckItemList items={list.slice(0, CHECK_LIMIT)} />
                  {hidden > 0 && <ExpandButton name={`확인사항 ${lane}`} hidden={hidden} onClick={onMore} />}
                </>
              ),
          };
        })}
      />
    </DashCard>
  );
}
