// 에이전트 패널 '기록' 탭 (agent_pickle_plan.md 5.1 · 계약 3.2). 최근 7일 동안 에이전트 · 화면이 한 일과 확인을 기다리는 일.
// - 확인 기다림은 맨 위 묶음에 고정(잊으면 그것이 누락이다). 그 아래 '최근 7일'은 서버 순서(최근 것부터) 그대로
// - 한 줄: 한 일(문장) / 상태 · 경로(via_label) · 때(상대 시각) · '자동' 표시. 오른쪽 끝에 버튼 하나
// - 버튼: 완료이고 되돌릴 수 있으면 [실행 취소], 되돌림이면 [다시 하기], 확인 기다림이면 [이어서 보기]
//   ([이어서 보기]는 그 확인 카드가 지금 대화에 열려 있을 때만 그린다. 미리보기 내용을 다시 받는 API가 없어 다른 곳에서는 열 수 없다)
import { useState } from 'react';
import type { HistoryItem } from '../../api/contract.ts';
import { useHistoryQuery } from '../../api/queries.ts';
import { Button, StateRow } from '../../ui/index.ts';
import { useTaskActions } from '../tasks/useTaskActions.ts';
import { HISTORY_STATE_LABEL, historyAction, relativeTime, splitHistory } from './agentPanelPlan.ts';
import { UNDO_BLOCKED_TEXT, undoFailState } from './agentText.ts';
import styles from './HistoryTab.module.css';

const DAYS = 7;

interface Props {
  now: () => number;
  canResume: (previewId: string) => boolean;
  onResume: (previewId: string) => void;
  announce: (text: string) => void;
}

export function HistoryTab({ now, canResume, onResume, announce }: Props) {
  const query = useHistoryQuery(DAYS);
  const actions = useTaskActions();
  const [pending, setPending] = useState<string | null>(null);
  /** 실패한 줄과 종류. blocked(409)는 다시 눌러도 같으므로 버튼을 거둔다(#60 리뷰) */
  const [failed, setFailed] = useState<{ id: string; kind: 'blocked' | 'error' } | null>(null);

  if (query.isPending) return <StateRow state="loading" />;
  if (query.isError && !query.data) return <StateRow state="error" text="기록을 불러오지 못함" onRetry={() => void query.refetch()} />;

  const { waiting, rest } = splitHistory(query.data.items);
  const nowMs = now();

  async function act(item: HistoryItem, actionId: number, done: string) {
    if (pending) return;
    setPending(item.id);
    setFailed(null);
    try {
      await actions.undo(actionId, { source: 'button', toast: false });
      announce(done);
    } catch (e) {
      const kind = undoFailState(e);
      setFailed({ id: item.id, kind });
      announce(kind === 'blocked' ? UNDO_BLOCKED_TEXT : '처리하지 못했어요');
    } finally {
      setPending(null);
    }
  }

  const row = (item: HistoryItem) => {
    const a = historyAction(item, canResume);
    const busy = pending === item.id;
    const fail = failed?.id === item.id ? failed.kind : null;
    return (
      <li key={item.id} className={styles.row} data-state={item.state}>
        <div className={styles.main}>
          <p className={styles.text}>{item.text}</p>
          <p className={styles.meta}>
            {item.state !== 'waiting' && <span className={styles.state}>{HISTORY_STATE_LABEL[item.state]}</span>}
            <span className={styles.via}>{item.viaLabel}</span>
            <span className={styles.time}>{relativeTime(item.atMs, nowMs)}</span>
            {item.auto && <span className={styles.auto}>자동</span>}
          </p>
          {fail === 'error' && <p className={styles.fail}>처리하지 못했어요. 다시 눌러 주세요.</p>}
          {fail === 'blocked' && <p className={styles.fail}>{UNDO_BLOCKED_TEXT}</p>}
        </div>
        {a?.kind === 'undo' && fail !== 'blocked' && (
          <Button size="sm" variant="ghost" className={styles.trailing} aria-disabled={busy || undefined} onClick={() => void act(item, a.actionId, '되돌렸어요')}>
            {busy ? '되돌리는 중' : '실행 취소'}
          </Button>
        )}
        {a?.kind === 'redo' && fail !== 'blocked' && (
          <Button size="sm" variant="ghost" className={styles.trailing} aria-disabled={busy || undefined} onClick={() => void act(item, a.actionId, '다시 했어요')}>
            {busy ? '하는 중' : '다시 하기'}
          </Button>
        )}
        {a?.kind === 'resume' && (
          <Button size="sm" className={styles.action} onClick={() => onResume(a.previewId)}>
            이어서 보기
          </Button>
        )}
      </li>
    );
  };

  if (waiting.length === 0 && rest.length === 0) {
    return <p className={styles.empty}>최근 {DAYS}일 동안 에이전트가 한 일이 없어요.</p>;
  }

  return (
    <div className={styles.root}>
      {waiting.length > 0 && (
        <section className={styles.section} aria-labelledby="history-waiting">
          <h3 id="history-waiting" className={styles.heading}>
            확인 기다림 <span className={styles.count}>{waiting.length}</span>
          </h3>
          <ul className={styles.list} data-kind="waiting">
            {waiting.map(row)}
          </ul>
        </section>
      )}
      {rest.length > 0 && (
        <section className={styles.section} aria-labelledby="history-recent">
          <h3 id="history-recent" className={styles.heading}>
            최근 {DAYS}일
          </h3>
          <ul className={styles.list}>{rest.map(row)}</ul>
        </section>
      )}
    </div>
  );
}
