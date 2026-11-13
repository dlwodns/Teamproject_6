// 리마인더 메뉴 (FE-16 · 명세 5절): 가운데 목록 · 오른쪽 상세. 고른 항목은 주소에 남아 뒤로 가기로 돌아온다.
// 좁은 화면(1024px 미만)은 목록과 상세를 한 칸씩 보이고, 상세 위 ‹ 뒤로가 목록으로 돌아간다.
import { useEffect, useId, useRef } from 'react';
import { useNavigate } from 'react-router';
import type { ReminderList } from '../../api/contract.ts';
import type { DashboardSource } from '../../api/types.ts';
import { reminderPath } from '../../features/agent/agentRoutes.ts';
import { ReminderDetail } from '../../features/reminders/ReminderDetail.tsx';
import { ReminderList as ReminderListView } from '../../features/reminders/ReminderList.tsx';
import { EMPTY_TEXT, GROUP_LABEL, inGroup, splitQuiet, visibleItems, type GroupFilter } from '../../features/reminders/reminderModel.ts';
import type { ReminderRunner } from '../../features/reminders/useReminderRunner.ts';
import { StateRow } from '../../ui/index.ts';
import styles from './AgentPage.module.css';

interface Props {
  group: GroupFilter;
  selectedKey: string | null;
  data: ReminderList | undefined;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
  runner: ReminderRunner;
  source: DashboardSource | undefined;
  busy: boolean;
}

export function RemindersView({ group, selectedKey, data, loading, error, onRetry, runner, source, busy }: Props) {
  const navigate = useNavigate();
  const headingId = useId();
  const detailHeadingId = useId();
  const detailRef = useRef<HTMLHeadingElement>(null);
  const all = data ? visibleItems(data.items) : [];
  const { active, quiet } = splitQuiet(inGroup(all, group));
  const selected = selectedKey === null ? null : (all.find((i) => i.key === selectedKey) ?? null);
  const muted = new Set(data?.mutedTypes ?? []);
  const now = () => data?.asOfMs ?? Date.now();

  // 항목을 고르면 상세 제목으로 포커스(좁은 화면에서는 칸이 바뀌므로 꼭 필요하다)
  const prevKey = useRef(selectedKey);
  useEffect(() => {
    if (prevKey.current === selectedKey) return;
    prevKey.current = selectedKey;
    if (selected) detailRef.current?.focus();
  }, [selectedKey, selected]);

  const onSelect = (key: string) => void navigate(reminderPath(group, key));
  const back = () => void navigate(reminderPath(group));

  return (
    <div className={styles.split} data-view={selected ? 'detail' : 'list'}>
      <section className={styles.listCol} aria-labelledby={headingId}>
        <div className={styles.colHead}>
          <h2 id={headingId} className={styles.colTitle} tabIndex={-1} data-agent-heading="">
            {GROUP_LABEL[group]}
          </h2>
          {data && <span className={styles.colCount}>{active.length + quiet.length}건</span>}
        </div>
        <div className={styles.scroll}>
          {loading ? (
            <div className={styles.pad}>
              <StateRow state="loading" />
            </div>
          ) : error ? (
            <div className={styles.pad}>
              <StateRow state="error" text="리마인더를 불러오지 못함" onRetry={onRetry} />
            </div>
          ) : (
            <ReminderListView
              label={`${GROUP_LABEL[group]} 리마인더`}
              items={active}
              quiet={quiet}
              selectedKey={selectedKey}
              onSelect={onSelect}
              empty={
                <div className={styles.empty}>
                  <p className={styles.emptyTitle}>{group === 'all' ? '지금 챙길 리마인더가 없어요' : `${GROUP_LABEL[group]} 리마인더가 없어요`}</p>
                  <p className={styles.emptyText}>{EMPTY_TEXT[group]}</p>
                  {group !== 'all' && all.length > 0 && (
                    <button type="button" className={styles.textLink} onClick={() => void navigate(reminderPath('all'))}>
                      {`전체 ${all.length}건 보기`}
                    </button>
                  )}
                </div>
              }
            />
          )}
        </div>
      </section>
      <section className={styles.detailCol} aria-label="리마인더 상세">
        {selected ? (
          <ReminderDetail
            ref={detailRef}
            key={selected.key}
            item={selected}
            runner={runner}
            source={source}
            now={now}
            muted={muted.has(selected.type)}
            busy={busy}
            onBack={back}
            headingId={detailHeadingId}
          />
        ) : (
          <div className={styles.detailEmpty}>
            <p className={styles.emptyTitle}>{selectedKey && data ? '이 리마인더는 끝났거나 사라졌어요' : '리마인더를 고르면 여기에 보여요'}</p>
            <p className={styles.emptyText}>왜 지금 챙겨야 하는지, 메일 속 근거 문장, 바로 할 수 있는 일을 함께 보여 줘요.</p>
          </div>
        )}
      </section>
    </div>
  );
}
