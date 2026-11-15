// 캐치봇의 작은 판단(순수 함수, node --test 대상): 리마인더 버튼이 보내는 명령 문장 · 기록 메뉴.
// 11-15 패널을 없애며 제안 카드 탭 판단(버튼 → 행동 표 · 결과 줄 · 처음 탭)은 지웠다(reminders.md 12.8).
import type { HistoryItem } from '../../api/contract.ts';
import { formatKstShort } from '../../lib/snooze.ts';

/** 에이전트 명령으로 보내는 문장. 모의 규칙(agentPlanner)과 실제 명령 해석 규칙(rules_v1)이 같은 행동으로 읽는 문장 */
export const COMMAND_TEXT = {
  T01: '오늘 뭐 해야 돼?',
  T06: '답장 안 온 메일 있어?',
} as const;

/** 데이터 모드. 실제(http)에서는 backend에 실행 경로가 없는 행동을 화면 이동으로 바꾼다 */
export type PlanMode = 'mock' | 'http' | null;

/** backend 명령 실행기에 아직 없는 행동(registry ready=False). 준비되면 여기서 빼면 명령 경로로 돌아간다 */
export const HTTP_NOT_READY = new Set(['T06', 'T07']); // T01(하루 요약 · 회고)은 11-14 서버에 생겼다

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
