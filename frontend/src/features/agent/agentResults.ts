// 결과물 칸 (FE-15 · FE-D20). 에이전트 화면(#/agent) 오른쪽에 길거나 다시 볼 결과를 크게 연다. 순수 함수, node --test 대상.
// 대화에는 '초안 1건 · 열기' 같은 짧은 카드만 두고, 누르면 오른쪽에 연다. 지난 결과도 그 카드로 다시 연다.
// 결과물로 여는 것: 회신 초안(T07) · 오늘 요약(T01) · 업무 목록(T02) · 답장 없는 메일(T06).
// 실행 결과(실행 취소가 있는 카드) · 확인 카드 · 알림 · 실패는 짧고 그 자리에서 눌러야 하므로 대화에 그대로 둔다.
import type { Entry, Outcome, Run } from './agentSession.ts';

export type ViewerKind = 'draft' | 'summary' | 'query' | 'awaiting';

export interface ViewerItem {
  runId: number;
  kind: ViewerKind;
  /** 짧은 카드의 이름: '초안 1건' · '요약' · '업무 3건' · '메일 2건' */
  label: string;
  /** 서버가 준 결과 제목(예: '긴급 5건이에요') */
  title: string;
}

/** 이 결과를 결과물 칸에 열 수 있으면 그 항목. 내용이 없는 결과(0건)는 대화 카드로 충분해 열지 않는다 */
export function viewerItemOf(run: Run): ViewerItem | null {
  const o: Outcome | null = run.outcome;
  if (o === null || run.phase !== 'done') return null;
  const base = { runId: run.id, title: o.title };
  switch (o.type) {
    case 'draft':
      return { ...base, kind: 'draft', label: '초안 1건' };
    case 'summary':
      return o.summary.items.length > 0 || Boolean(o.summary.text) ? { ...base, kind: 'summary', label: '요약' } : null;
    case 'query':
      return o.targets.length > 0 ? { ...base, kind: 'query', label: `업무 ${o.targets.length}건` } : null;
    case 'awaiting':
      return o.items.length > 0 ? { ...base, kind: 'awaiting', label: `메일 ${o.items.length}건` } : null;
    default:
      return null;
  }
}

/** 대화에서 열 수 있는 결과 전부(오래된 것부터) */
export function viewerItems(entries: readonly Entry[]): ViewerItem[] {
  const out: ViewerItem[] = [];
  for (const e of entries) {
    if (e.kind !== 'run') continue;
    const item = viewerItemOf(e);
    if (item) out.push(item);
  }
  return out;
}

/**
 * 결과물 칸에 지금 보일 run. 연 결과가 대화에 없거나(대화를 새로 시작함) 열 수 없는 결과면 null(빈 상태).
 * 아무것도 열지 않았으면 null — 처음에는 빈 상태로 두고 사용자가 고른 것만 연다
 */
export function openedRun(entries: readonly Entry[], openRunId: number | null): Run | null {
  if (openRunId === null) return null;
  const run = entries.find((e): e is Run => e.kind === 'run' && e.id === openRunId);
  return run && viewerItemOf(run) ? run : null;
}
