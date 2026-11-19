// 결과물 칸 상태 (FE-15). 대화(agentSession)처럼 모듈에 하나만 둔다 — 토스트 [열기]를 어느 화면에서 눌러도
// 에이전트 화면이 그 결과를 열고, 화면을 옮겼다 돌아와도 연 결과 · 고쳐 쓴 초안이 남는다(새로고침하면 사라진다).
import { useSyncExternalStore } from 'react';
import type { MailId } from '../../api/types.ts';

export interface ViewerState {
  /** 결과물 칸에 연 run id. null = 빈 상태 */
  openRunId: number | null;
  /** 초안을 고쳐 쓴 글자(run id별). 다시 열어도 고친 글자가 남는다 */
  drafts: ReadonlyMap<number, string>;
  /** 결과 · 카드의 메일 줄을 눌러 결과물 칸에 연 메일(11-18: 메일 화면으로 넘어가지 않는다). runId = 그 메일을 보인 결과 */
  mail: { runId: number; mailId: MailId } | null;
}

let state: ViewerState = { openRunId: null, drafts: new Map(), mail: null };
const listeners = new Set<() => void>();

function set(next: ViewerState) {
  state = next;
  for (const l of listeners) l();
}

export const agentViewer = {
  getState: (): ViewerState => state,
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  open(runId: number) {
    if (state.openRunId !== runId || state.mail) set({ ...state, openRunId: runId, mail: null });
  },
  close() {
    if (state.openRunId !== null || state.mail) set({ ...state, openRunId: null, mail: null });
  },
  openMail(runId: number, mailId: MailId) {
    set({ ...state, openRunId: runId, mail: { runId, mailId } });
  },
  closeMail() {
    if (state.mail) set({ ...state, mail: null });
  },
  setDraft(runId: number, text: string) {
    const drafts = new Map(state.drafts);
    drafts.set(runId, text);
    set({ ...state, drafts });
  },
};

export function useAgentViewer(): ViewerState {
  return useSyncExternalStore(agentViewer.subscribe, agentViewer.getState);
}
