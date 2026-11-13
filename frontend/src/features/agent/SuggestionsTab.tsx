// 에이전트 패널 '제안' 탭 (suggestion_cards.md 3 · 4 · 5절, 계약 3.1). 카드는 서버(또는 모의)가 규칙으로 판정한 것을 그대로 보인다.
// - 카드: 한 줄 제목 + 둘째 줄(있으면) + 버튼 한 줄(보조 → 주 버튼 순, 오른쪽 정렬 — 확인 카드와 같은 순서) + ⋯(업무 아님 · 이 제안 숨기기)
// - 빨강 채움은 쓰지 않는다(UX-D18: 확정 동작이 아니다). 주 버튼은 테두리, 보조는 글자 버튼
// - [완료] · [나중에] · [업무 아님]은 useTaskActions에 카드 via를 실어 바로 실행하고, 카드 자리에 결과 한 줄 + [실행 취소]
// - [초안 보기] · [오늘 요약 보기] · [응답 대기 보기]는 기존 명령 경로(대화 탭)로, [메일 열기]는 메일 화면으로
// - 3장 넘으면 아래 '제안 N건 더 보기 ›' 한 곳
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../../api/client.ts';
import type { Suggestion } from '../../api/contract.ts';
import { queryKeys, useDashboardQuery, useSuggestionsQuery } from '../../api/queries.ts';
import type { MailId, TaskId } from '../../api/types.ts';
import { snoozeOptions } from '../../lib/snooze.ts';
import { Button, Check, ChevronDown, ChevronRight, Ellipsis, IconButton, Menu, StateRow, type MenuItemSpec } from '../../ui/index.ts';
import { useOpenMail } from '../tasks/useOpenMail.ts';
import { useTaskActions } from '../tasks/useTaskActions.ts';
import { FALLBACK_EXAMPLES } from './agentText.ts';
import { drawableButtons, planSuggestionButton, suggestionResultText, withResults, type SuggestionPlan } from './agentPanelPlan.ts';
import type { UndoState } from './agentSession.ts';
import { ExampleList } from './ExampleList.tsx';
import styles from './SuggestionsTab.module.css';

const COLLAPSED = 3;
const EXPANDED = 50;

interface ResultEntry {
  key: string;
  index: number;
  text: string;
  actionId: number | null;
  undo: UndoState;
}

interface Props {
  /** 명령이 진행 중(명령으로 가는 버튼 · 예시를 잠근다) */
  busy: boolean;
  /** 대화 탭으로 옮겨 명령을 보낸다 */
  onCommand: (text: string, selectedMailIds?: MailId[]) => void;
  /** 서버 시계(나중에 메뉴의 시각 계산) */
  now: () => number;
  /** 결과 · 실패를 role="status"로 알린다 */
  announce: (text: string) => void;
}

export function SuggestionsTab({ busy, onCommand, now, announce }: Props) {
  const [expanded, setExpanded] = useState(false);
  const query = useSuggestionsQuery(expanded ? EXPANDED : COLLAPSED);
  const dashboard = useDashboardQuery();
  const actions = useTaskActions();
  const openMail = useOpenMail();
  const client = useQueryClient();
  const [results, setResults] = useState<ResultEntry[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<string | null>(null);

  const taskText = (id: TaskId) => dashboard.data?.tasks.find((t) => t.id === id)?.text ?? null;

  const addResult = (card: Suggestion, index: number, text: string, actionId: number | null) => {
    setResults((prev) => [...prev.filter((r) => r.key !== card.key), { key: card.key, index, text, actionId, undo: 'idle' }]);
    announce(text);
  };

  async function run(card: Suggestion, index: number, plan: SuggestionPlan, untilMs?: number) {
    if (plan.type === 'command') {
      if (!busy) onCommand(plan.text, plan.selectedMailIds);
      return;
    }
    if (plan.type === 'open_mail') {
      openMail(plan.mailId);
      return;
    }
    if (pending) return;
    setPending(card.key);
    setErrors(({ [card.key]: _drop, ...rest }) => rest);
    try {
      if (plan.type === 'hide') {
        const r = await api.hideSuggestion(plan.key);
        addResult(card, index, suggestionResultText('hidden', null, r.hiddenUntilMs), null);
        void client.invalidateQueries({ queryKey: queryKeys.agent });
      } else if (plan.type === 'status') {
        const opts = { source: 'button' as const, toast: false, via: plan.via };
        const r = plan.status === 'done' ? await actions.complete([plan.taskId], opts) : await actions.exclude([plan.taskId], opts);
        addResult(card, index, suggestionResultText(plan.status, taskText(plan.taskId), null), r.actionId);
      } else {
        const until = untilMs ?? plan.untilMs;
        if (until === null) return;
        const r = await actions.snooze([plan.taskId], until, { source: 'button', toast: false, via: plan.via });
        addResult(card, index, suggestionResultText('snoozed', taskText(plan.taskId), until), r.actionId);
      }
    } catch {
      setErrors((prev) => ({ ...prev, [card.key]: '처리하지 못했어요. 다시 눌러 주세요.' }));
      announce('처리하지 못했어요');
    } finally {
      setPending(null);
    }
  }

  async function undoResult(entry: ResultEntry) {
    if (entry.actionId === null || entry.undo === 'pending' || entry.undo === 'done') return;
    const set = (undo: UndoState) => setResults((prev) => prev.map((r) => (r.key === entry.key ? { ...r, undo } : r)));
    set('pending');
    try {
      await actions.undo(entry.actionId, { source: 'button', toast: false });
      // 카드가 다시 계산돼 돌아온 뒤 결과 줄을 걷는다(빈자리가 깜빡이지 않게)
      await client.invalidateQueries({ queryKey: queryKeys.agent });
      setResults((prev) => prev.filter((r) => r.key !== entry.key));
      announce('되돌렸어요');
    } catch {
      set('error');
      announce('되돌리지 못했어요');
    }
  }

  if (query.isPending) return <StateRow state="loading" />;
  if (query.isError && !query.data) return <StateRow state="error" text="제안을 불러오지 못함" onRetry={() => void query.refetch()} />;

  const data = query.data;
  const rows = withResults(data.suggestions, results);

  if (rows.length === 0) {
    return (
      <div className={styles.empty}>
        <p className={styles.emptyTitle}>지금은 챙길 제안이 없어요</p>
        <p className={styles.emptyHint}>이렇게 말해 볼 수 있어요.</p>
        <ExampleList examples={FALLBACK_EXAMPLES} busy={busy} onRun={(t) => onCommand(t)} label="예시 명령" />
      </div>
    );
  }

  return (
    <div className={styles.root}>
      <ul className={styles.list} aria-label="제안">
        {rows.map((row, index) =>
          row.type === 'result' ? (
            <li key={`r:${row.result.key}`} className={styles.result}>
              <Check size={16} aria-hidden="true" className={styles.resultIcon} />
              <span className={styles.resultText}>{row.result.undo === 'done' ? '되돌렸어요' : row.result.text}</span>
              {row.result.actionId !== null && (
                <Button
                  size="sm"
                  variant="ghost"
                  className={styles.trailing}
                  aria-disabled={row.result.undo === 'pending' || undefined}
                  onClick={() => void undoResult(row.result)}
                >
                  {row.result.undo === 'pending' ? '되돌리는 중' : row.result.undo === 'error' ? '다시 되돌리기' : '실행 취소'}
                </Button>
              )}
            </li>
          ) : (
            <SuggestionCard
              key={row.card.key}
              card={row.card}
              busy={busy}
              locked={pending === row.card.key}
              error={errors[row.card.key] ?? null}
              now={now}
              onRun={(plan, until) => void run(row.card, index, plan, until)}
            />
          ),
        )}
      </ul>
      {!expanded && data.more > 0 && (
        <button type="button" className={styles.expand} onClick={() => setExpanded(true)}>
          {`제안 ${data.more}건 더 보기`}
          <ChevronRight size={16} aria-hidden="true" />
        </button>
      )}
    </div>
  );
}

interface CardProps {
  card: Suggestion;
  busy: boolean;
  locked: boolean;
  error: string | null;
  now: () => number;
  onRun: (plan: SuggestionPlan, untilMs?: number) => void;
}

function SuggestionCard({ card, busy, locked, error, now, onRun }: CardProps) {
  const buttons = drawableButtons(card);
  const menu: MenuItemSpec[] = card.menu.flatMap((b, i) => {
    const plan = planSuggestionButton(card, b);
    return plan ? [{ key: `${b.action}:${i}`, label: b.label, onSelect: () => onRun(plan) }] : [];
  });
  return (
    <li className={styles.card} aria-busy={locked || undefined}>
      <div className={styles.head}>
        <h3 className={styles.title}>{card.title}</h3>
        {menu.length > 0 && (
          <Menu
            align="end"
            trigger={<IconButton className={styles.more} label="이 제안 메뉴" icon={<Ellipsis size={16} aria-hidden="true" />} />}
            items={menu}
          />
        )}
      </div>
      {card.detail.length > 0 && (
        <ul className={styles.detail}>
          {card.detail.map((d) => (
            <li key={d} className={styles.detailItem}>
              {d}
            </li>
          ))}
        </ul>
      )}
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      {buttons.length > 0 && (
        <div className={styles.actions}>
          {buttons.map(({ button, plan }) => {
            const variant = button.primary ? 'secondary' : 'ghost';
            const disabled = locked || (plan.type === 'command' && busy);
            if (plan.type === 'snooze' && plan.untilMs === null) {
              return (
                <Menu
                  key={button.action}
                  align="end"
                  trigger={
                    <Button size="sm" variant={variant} aria-disabled={disabled || undefined}>
                      {button.label}
                      <ChevronDown size={16} aria-hidden="true" />
                    </Button>
                  }
                  items={snoozeOptions(now()).map((o) => ({
                    key: o.key,
                    label: o.label,
                    detail: o.detail,
                    disabled,
                    onSelect: () => onRun(plan, o.untilMs),
                  }))}
                />
              );
            }
            return (
              <Button
                key={button.action}
                size="sm"
                variant={variant}
                aria-disabled={disabled || undefined}
                onClick={() => !disabled && onRun(plan)}
              >
                {button.label}
              </Button>
            );
          })}
        </div>
      )}
    </li>
  );
}
