// 리마인더 메뉴 (FE-16 · 명세 5절): 가운데 목록 · 오른쪽 상세. 고른 항목은 주소에 남아 뒤로 가기로 돌아온다.
// 좁은 화면(1024px 미만)은 목록과 상세를 한 칸씩 보이고, 상세 위 ‹ 뒤로가 목록으로 돌아간다.
// 포커스: 항목을 고르면 상세 제목으로, 고른 것을 풀면(‹ 뒤로 · 뒤로 가기) 그 줄로, 처리해서 항목이 사라지면 그 자리의 다음 줄로
// (없으면 목록 제목으로) 옮긴다. 누른 버튼이 화면에서 사라져 포커스가 문서 맨 앞으로 떨어지지 않게 하기 위해서다.
import { useEffect, useId, useRef } from 'react';
import { useNavigate } from 'react-router';
import type { ReminderItem, ReminderList } from '../../api/contract.ts';
import type { DashboardSource } from '../../api/types.ts';
import { reminderPath } from '../../features/agent/agentRoutes.ts';
import { ReminderDetail } from '../../features/reminders/ReminderDetail.tsx';
import { ReminderList as ReminderListView, reminderOptionId, reminderWho } from '../../features/reminders/ReminderList.tsx';
import { CHANNEL_LABEL, channelItems, EMPTY_TEXT, inChannel, splitQuiet, type Channel } from '../../features/reminders/reminderModel.ts';
import type { ReminderRunner } from '../../features/reminders/useReminderRunner.ts';
import { StateRow } from '../../ui/index.ts';
import styles from './AgentPage.module.css';

interface Props {
  group: Channel;
  selectedKey: string | null;
  data: ReminderList | undefined;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
  runner: ReminderRunner;
  source: DashboardSource | undefined;
}

export function RemindersView({ group, selectedKey, data, loading, error, onRetry, runner, source }: Props) {
  const navigate = useNavigate();
  const headingId = useId();
  const detailHeadingId = useId();
  const detailRef = useRef<HTMLHeadingElement>(null);
  const listHeadingRef = useRef<HTMLHeadingElement>(null);
  const all = data ? channelItems(data.items) : [];
  const { active, quiet } = splitQuiet(inChannel(all, group));
  const selected = selectedKey === null ? null : (all.find((i) => i.key === selectedKey) ?? null);
  const muted = new Set(data?.mutedTypes ?? []);
  const now = () => data?.asOfMs ?? Date.now();

  // 항목을 고르면 상세 제목으로 포커스(좁은 화면에서는 칸이 바뀌므로 꼭 필요하다). 고른 것을 풀면 그 줄로
  const prevKey = useRef(selectedKey);
  useEffect(() => {
    if (prevKey.current === selectedKey) return;
    const before = prevKey.current;
    prevKey.current = selectedKey;
    if (selected) detailRef.current?.focus();
    else if (selectedKey === null && before !== null) (document.getElementById(reminderOptionId(before)) ?? listHeadingRef.current)?.focus();
  }, [selectedKey, selected]);

  // 보이던 항목이 처리되어 목록에서 빠지면(완료 · 숨김 · 적용 뒤 다시 부름) 그 자리의 다음 줄로. 상세 칸은 '끝났거나 사라졌어요'를 보인다
  const shown = useRef<{ key: string; index: number } | null>(null);
  const index = selected ? active.findIndex((i) => i.key === selected.key) : -1;
  useEffect(() => {
    if (selected) {
      shown.current = { key: selected.key, index };
      return;
    }
    const was = shown.current;
    shown.current = null;
    if (!was || was.key !== selectedKey || !data) return;
    const next = active[Math.min(was.index, active.length - 1)];
    (next ? document.getElementById(reminderOptionId(next.key)) : listHeadingRef.current)?.focus();
    // active는 매번 새 배열이라 의존에서 뺀다(항목이 사라진 그 순간 한 번만 본다)
  }, [selected, selectedKey, index, data]);

  const onSelect = (key: string) => void navigate(reminderPath(group, key));
  const back = () => void navigate(reminderPath(group));
  const whoOf = (it: ReminderItem) => reminderWho(it, source);
  const openMailOf = (it: ReminderItem) => {
    const mailId = it.mailId;
    if (mailId === null || runner.ctx.mailTarget(mailId) !== 'mail') return null;
    return () => void runner.run(it, { type: 'open_mail', mailId });
  };

  return (
    <div className={styles.split} data-view={selected ? 'detail' : 'list'}>
      <section className={styles.listCol} aria-labelledby={headingId}>
        <div className={styles.colHead}>
          <h2 id={headingId} ref={listHeadingRef} className={styles.colTitle} tabIndex={-1} data-agent-heading="">
            {CHANNEL_LABEL[group]}
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
              label={`${CHANNEL_LABEL[group]} 리마인더`}
              items={active}
              quiet={quiet}
              selectedKey={selectedKey}
              onSelect={onSelect}
              whoOf={whoOf}
              openMailOf={openMailOf}
              empty={
                <div className={styles.empty}>
                  <p className={styles.emptyTitle}>{`${CHANNEL_LABEL[group]} 알림이 없습니다`}</p>
                  <p className={styles.emptyText}>{EMPTY_TEXT[group]}</p>
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
            onBack={back}
            headingId={detailHeadingId}
          />
        ) : (
          <div className={styles.detailEmpty}>
            <p className={styles.emptyTitle}>{selectedKey && data ? '처리가 완료되었거나 삭제된 알림입니다' : '알림을 선택하면 상세 내용이 표시됩니다'}</p>
            <p className={styles.emptyText}>알림 사유, 메일 내 근거 문장, 바로 처리할 수 있는 작업을 함께 표시합니다.</p>
          </div>
        )}
      </section>
    </div>
  );
}
