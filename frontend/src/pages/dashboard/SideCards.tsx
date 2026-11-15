// 1열 아래 카드: W1 응답 대기 · I1 확인사항 (UX-D1 · UX-D2). 서버가 그 칸을 보내지 않으면 부르는 쪽이 카드를 숨긴다.
// 목록은 5줄 높이로 보이고 안에서 스크롤한다. 더보기는 카드 오른쪽 위 한 곳.
import { useState } from 'react';
import type { Awaiting } from '../../api/types.ts';
import { CHECK_LANES, type CheckItem, type CheckLane } from '../../features/tasks/aggregate.ts';
import { StateRow, Tabs } from '../../ui/index.ts';
import { DashCard, MoreButton, ScrollArea } from './DashCard.tsx';
import { AwaitingList, CheckItemList } from './InfoRows.tsx';
import styles from './SideCards.module.css';

export function WaitingCard({ items, onMore }: { items: readonly Awaiting[]; onMore: () => void }) {
  return (
    <DashCard title="응답 대기" count={items.length} tools={items.length > 0 ? <MoreButton name="응답 대기" onClick={onMore} /> : undefined}>
      {items.length === 0 ? (
        <StateRow state="empty" />
      ) : (
        <ScrollArea>
          <AwaitingList items={items} />
        </ScrollArea>
      )}
    </DashCard>
  );
}

export function CheckItemsCard({ checks, onMore }: { checks: Record<CheckLane, CheckItem[]>; onMore: () => void }) {
  const [tab, setTab] = useState<CheckLane>('확인');
  const total = checks.확인.length + checks.참고.length;
  return (
    <DashCard title="확인사항" count={total} tools={total > 0 ? <MoreButton name="확인사항" onClick={onMore} /> : undefined}>
      <Tabs<CheckLane>
        className={styles.tabs}
        label="확인사항 종류"
        value={tab}
        onValueChange={setTab}
        items={CHECK_LANES.map((lane) => {
          const list = checks[lane];
          return {
            value: lane,
            label: lane,
            count: list.length,
            content:
              list.length === 0 ? (
                <StateRow state="empty" />
              ) : (
                <ScrollArea check>
                  <CheckItemList items={list} />
                </ScrollArea>
              ),
          };
        })}
      />
    </DashCard>
  );
}
