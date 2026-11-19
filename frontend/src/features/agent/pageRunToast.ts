// 에이전트 화면 아래 입력으로 보낸 명령의 결과를 '대화' 메뉴가 아닌 곳에서 어떻게 알릴지 (FE-16 · 명세 5절 '아래 입력').
// 결과는 대화에 쌓이고, 지금 화면에는 결과 한 줄 토스트만 띄운다. 순수 함수, node --test 대상.
// - 실행 결과(되돌릴 기록 있음) → [실행 취소]
// - 초안 → [열기](초안 메뉴), 확인 카드 → [열기](대화 메뉴의 그 카드), 그 밖의 결과 · 실패 → [열기](대화 메뉴)
// - 사용자가 스스로 취소한 일은 알리지 않는다
import type { Run } from './agentSession.ts';

export type PageRunAction = 'undo' | 'open_draft' | 'open_confirm' | 'open_chat';

export interface PageRunToast {
  kind: 'undo' | 'info' | 'error';
  title: string;
  action: PageRunAction | null;
  actionLabel: string | null;
}

/** 대화에서 봐야 하는 결과인가(묻기 · 확인 · 초안 · 실패 → '대화'로 넘어간다). 그 자리 1건 변경 · 바뀐 것 없는 한 줄은 토스트만 */
export const opensChat = (t: PageRunToast): boolean => t.action !== null && t.action !== 'undo';

/** 알릴 때가 됐나: 끝났거나(완료 · 실패) 확인을 기다리기 시작했다. 아직이면 null */
export function pageRunToast(run: Run): PageRunToast | null {
  const o = run.outcome;
  if (run.phase === 'running') {
    if (o?.type !== 'confirm') return null;
    return { kind: 'info', title: `확인이 필요합니다 · ${o.title}`, action: 'open_confirm', actionLabel: '열기' };
  }
  if (run.phase === 'cancelled' || run.phase === 'stopped') return null;
  if (run.phase === 'fail') return { kind: 'error', title: o?.title ?? '처리하지 못했습니다', action: 'open_chat', actionLabel: '열기' };
  if (!o) return { kind: 'info', title: '작업을 완료했습니다', action: 'open_chat', actionLabel: '열기' };
  if (o.type === 'result') {
    return o.actionId !== null
      ? { kind: 'undo', title: o.title, action: 'undo', actionLabel: '실행 취소' }
      : { kind: 'info', title: o.title, action: null, actionLabel: null };
  }
  if (o.type === 'draft') return { kind: 'info', title: o.title, action: 'open_draft', actionLabel: '열기' };
  return { kind: 'info', title: o.title, action: 'open_chat', actionLabel: '열기' };
}
