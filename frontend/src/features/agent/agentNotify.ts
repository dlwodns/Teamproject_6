// 작업이 끝났을 때 알릴지 정한다 (FE-15 · FE-D22, 피클 '작업 카드 · 끝나면 알림'). 순수 함수, node --test 대상.
// 사용자가 그 작업을 보고 있으면(패널이 열려 있거나 에이전트 화면이고, 탭이 보이는 중) 알리지 않는다 — 카드가 이미 눈앞에 있다.
// 보고 있지 않으면 ① 앱 안 토스트 하나(누르면 #/agent에서 그 결과를 연다), ② 탭이 가려져 있고 사용자가 브라우저 알림을
// 직접 켰고 브라우저가 허락했으면 브라우저 알림. ③ 알림 센터(FE-10)는 넣을 자리가 생기면 잇는다(agentCompletion 주석).
// 사용자가 스스로 취소한 일(취소됨)은 알리지 않는다. 확인 카드를 기다리기 시작한 순간도 같은 기준으로 알린다(사람이 눌러야 다음으로 간다).
import type { Entry, Run } from './agentSession.ts';
import { viewerItemOf } from './agentResults.ts';

export type BrowserPermission = 'granted' | 'denied' | 'default' | 'unsupported';

export interface NotifyContext {
  /** 에이전트 패널이 열려 있다 */
  panelOpen: boolean;
  /** 에이전트 화면(#/agent)에 있다 */
  onAgentPage: boolean;
  /** 탭이 가려져 있다(document.hidden) */
  hidden: boolean;
  /** 에이전트 화면에서 '작업이 끝나면 브라우저 알림 받기'를 켰다 */
  browserOptIn: boolean;
  permission: BrowserPermission;
}

export interface NotifyDecision {
  toast: boolean;
  /** 토스트가 저절로 닫히기까지(ms). 0 = 닫지 않음(가려진 동안 끝났으면 돌아와서 보게) */
  toastTimeout: number;
  browser: boolean;
  /** 에이전트 화면에 있으면 결과물 칸에 바로 연다 */
  openInViewer: boolean;
}

/** 보고 있을 때 끝난 토스트 시간과 같게: 결과로 가는 버튼이 있어 정보 토스트보다 조금 길게 둔다 */
export const COMPLETION_TOAST_MS = 8000;

export function notifyDecision(run: Run, ctx: NotifyContext): NotifyDecision {
  const none: NotifyDecision = { toast: false, toastTimeout: 0, browser: false, openInViewer: false };
  if (run.phase !== 'done' && run.phase !== 'fail' && !awaitingConfirm(run)) return none;
  const openInViewer = ctx.onAgentPage && viewerItemOf(run) !== null;
  const looking = !ctx.hidden && (ctx.panelOpen || ctx.onAgentPage);
  if (looking) return { ...none, openInViewer };
  return {
    toast: true,
    toastTimeout: ctx.hidden ? 0 : COMPLETION_TOAST_MS,
    browser: ctx.hidden && ctx.browserOptIn && ctx.permission === 'granted',
    openInViewer,
  };
}

/** 확인 카드를 기다리는 중(진행 중이지만 사람이 눌러야 다음으로 간다) */
const awaitingConfirm = (run: Run) => run.phase === 'running' && run.outcome?.type === 'confirm';

/** 진행 중인 run id. 확인 카드를 기다리는 run은 이미 알렸으므로 넣지 않는다 */
export function runningIds(entries: readonly Entry[]): Set<number> {
  const ids = new Set<number>();
  for (const e of entries) if (e.kind === 'run' && e.phase === 'running' && !awaitingConfirm(e)) ids.add(e.id);
  return ids;
}

/** 지난번에 진행 중이던 run 가운데 이제 끝났거나 확인 카드를 기다리기 시작한 것 */
export function finishedSince(prevRunning: ReadonlySet<number>, entries: readonly Entry[]): Run[] {
  return entries.filter((e): e is Run => e.kind === 'run' && prevRunning.has(e.id) && (e.phase !== 'running' || awaitingConfirm(e)));
}

const MAX_COMMAND_CHARS = 40;

/** 토스트 · 브라우저 알림 글자. 제목은 서버 결과 제목, 설명은 내가 시킨 말(길면 줄임) */
export function completionText(run: Run): { title: string; body: string } {
  const said = run.text.length > MAX_COMMAND_CHARS ? `${run.text.slice(0, MAX_COMMAND_CHARS - 1)}…` : run.text;
  const fallback = run.phase === 'fail' ? '처리하지 못했어요' : '작업을 마쳤어요';
  return { title: run.outcome?.title ?? fallback, body: `'${said}'` };
}
