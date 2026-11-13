// 에이전트 패널 제안 · 기록 탭의 작은 판단(순수 함수, node --test 대상).
// 제안 카드 버튼 → 무엇을 부를지(계약 3.1 표 '버튼을 행동으로 바꾸는 표', 프런트엔드 몫):
//   T03 완료 · T10 업무 아님 → useTaskActions(complete · exclude) + 카드 via
//   T05 나중에              → 시각 메뉴(lib/snooze)에서 고른 뒤 useTaskActions.snooze + 카드 via
//   T07 · T01 · T06          → 기존 에이전트 명령 경로(POST /api/agent/command)에 문장을 보낸다. T07은 카드의 메일을 고른 메일로
//   open_mail(navigate)      → 메일 화면의 그 메일
//   hide                     → POST /api/suggestions/{key}/hide
// 모르는 행동(T13 등 아직 화면에 실행 경로가 없는 것)은 null → 버튼을 그리지 않는다(죽은 버튼 금지).
import type { HistoryItem, Suggestion, SuggestionButton } from '../../api/contract.ts';
import type { MailId, TaskId } from '../../api/types.ts';
import { formatKstShort } from '../../lib/snooze.ts';

/** 에이전트 명령으로 보내는 문장. 모의 규칙(agentPlanner)과 실제 명령 해석 규칙(rules_v1)이 같은 행동으로 읽는 문장 */
export const COMMAND_TEXT = {
  T01: '오늘 뭐 해야 돼?',
  T06: '답장 안 온 메일 있어?',
  T07: '이 메일 회신 초안 써 줘',
} as const;

export type SuggestionPlan =
  | { type: 'status'; status: 'done' | 'excluded'; taskId: TaskId; via: string }
  | { type: 'snooze'; taskId: TaskId; via: string; untilMs: number | null }
  | { type: 'command'; text: string; selectedMailIds?: MailId[] }
  | { type: 'open_mail'; mailId: MailId }
  | { type: 'hide'; key: string };

/** 버튼 하나를 실행 계획으로. 실행할 길이 없으면 null(그리지 않는다) */
export function planSuggestionButton(card: Pick<Suggestion, 'key' | 'via'>, button: SuggestionButton): SuggestionPlan | null {
  const taskId = button.target.taskIds[0];
  const mailId = button.target.mailIds[0];
  if (button.kind === 'hide') return { type: 'hide', key: card.key };
  if (button.kind === 'navigate') return button.action === 'open_mail' && mailId !== undefined ? { type: 'open_mail', mailId } : null;
  switch (button.action) {
    case 'T03':
    case 'T10':
      return taskId === undefined ? null : { type: 'status', status: button.action === 'T03' ? 'done' : 'excluded', taskId, via: card.via };
    case 'T05': {
      if (taskId === undefined) return null;
      const until = button.params['until'];
      const untilMs = typeof until === 'string' ? Date.parse(until) : NaN;
      return { type: 'snooze', taskId, via: card.via, untilMs: Number.isNaN(untilMs) ? null : untilMs };
    }
    case 'T07':
      return mailId === undefined ? null : { type: 'command', text: COMMAND_TEXT.T07, selectedMailIds: [mailId] };
    case 'T01':
      return { type: 'command', text: COMMAND_TEXT.T01 };
    case 'T06':
      return { type: 'command', text: COMMAND_TEXT.T06 };
    default:
      return null;
  }
}

/** 카드 버튼 중 그릴 것(실행 경로가 있는 것)만, 주 버튼은 맨 뒤(오른쪽, 확인 카드와 같은 순서) */
export function drawableButtons(card: Suggestion): { button: SuggestionButton; plan: SuggestionPlan }[] {
  const out = card.buttons.flatMap((button) => {
    const plan = planSuggestionButton(card, button);
    return plan ? [{ button, plan }] : [];
  });
  return [...out.filter((b) => !b.button.primary), ...out.filter((b) => b.button.primary)];
}

/** 카드 자리에 남기는 결과 한 줄 */
export function suggestionResultText(kind: 'done' | 'excluded' | 'snoozed' | 'hidden', taskText: string | null, untilMs: number | null): string {
  const what = taskText ? `'${taskText.length > 20 ? `${taskText.slice(0, 19)}…` : taskText}'` : '업무';
  if (kind === 'done') return `${what} 완료했어요`;
  if (kind === 'excluded') return `${what} 업무에서 뺐어요`;
  if (kind === 'snoozed') return untilMs === null ? `${what} 미뤘어요` : `${what} ${formatKstShort(untilMs)}까지 미뤘어요`;
  return untilMs === null ? '이 제안을 숨겼어요' : `${formatKstShort(untilMs)}까지 이 제안을 숨겼어요`;
}

/**
 * 카드 목록에 결과 줄을 끼운다. 결과가 난 카드는 서버에서 다시 받으면 빠지므로, 처음 보인 자리(index)에 결과 줄을 남긴다.
 * 아직 목록에 그 카드가 있으면 그 자리를 결과 줄로 바꾼다
 */
export function withResults<R extends { key: string; index: number }>(
  cards: readonly Suggestion[],
  results: readonly R[],
): ({ type: 'card'; card: Suggestion } | { type: 'result'; result: R })[] {
  const byKey = new Map(results.map((r) => [r.key, r]));
  const rows: ({ type: 'card'; card: Suggestion } | { type: 'result'; result: R })[] = cards.map((card) => {
    const r = byKey.get(card.key);
    return r ? { type: 'result', result: r } : { type: 'card', card };
  });
  const shown = new Set(cards.map((c) => c.key));
  for (const r of [...results].sort((a, b) => a.index - b.index)) {
    if (!shown.has(r.key)) rows.splice(Math.min(r.index, rows.length), 0, { type: 'result', result: r });
  }
  return rows;
}

// ── 기록 탭 ──

export const HISTORY_STATE_LABEL: Record<HistoryItem['state'], string> = {
  waiting: '확인 기다림',
  done: '완료',
  undone: '되돌림',
};

/** '방금 전' · '10분 전' · '3시간 전', 하루가 넘으면 '11/5(목) 14:00'. 시계가 조금 어긋나 미래면 '방금 전' */
export function relativeTime(atMs: number, nowMs: number): string {
  const sec = Math.floor((nowMs - atMs) / 1000);
  if (sec < 60) return '방금 전';
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}분 전`;
  const hour = Math.floor(min / 60);
  if (hour < 24) return `${hour}시간 전`;
  return formatKstShort(atMs);
}

/** 확인 기다림(맨 위 고정)과 나머지로 나눈다. 서버 순서는 그대로 둔다 */
export function splitHistory(items: readonly HistoryItem[]): { waiting: HistoryItem[]; rest: HistoryItem[] } {
  return { waiting: items.filter((i) => i.state === 'waiting'), rest: items.filter((i) => i.state !== 'waiting') };
}

/** 줄의 버튼: 실행 취소 · 다시 하기 · 이어서 보기(그 확인 카드가 대화에 열려 있을 때만) */
export function historyAction(
  item: HistoryItem,
  canResume: (previewId: string) => boolean,
): { kind: 'undo'; actionId: number } | { kind: 'redo'; actionId: number } | { kind: 'resume'; previewId: string } | null {
  if (item.state === 'done' && item.canUndo && item.actionId !== null) return { kind: 'undo', actionId: item.actionId };
  if (item.state === 'undone' && item.redoActionId !== null) return { kind: 'redo', actionId: item.redoActionId };
  if (item.state === 'waiting' && item.previewId !== null && canResume(item.previewId)) return { kind: 'resume', previewId: item.previewId };
  return null;
}

/** 패널을 열 때 처음 볼 탭: 제안이 있으면 제안, 없거나 못 받으면 대화. 아직 모르면 null */
export function landingTab(total: number | undefined, failed: boolean): 'suggest' | 'chat' | null {
  if (failed) return 'chat';
  if (total === undefined) return null;
  return total > 0 ? 'suggest' : 'chat';
}
