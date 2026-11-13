// 단계 줄 글자 (components.md 4.4 StepLine · wireframe 13-4 · UX-D8). 순수 함수, node --test 대상.
// 명령 이해 → 대상 찾기 → (확인) → 실행. 진행 중엔 한 줄 "…하는 중 · n/전체 · 경과 N초(3초부터)",
// 끝나면 "N단계 완료 · M초"로 접고, 실패하면 펼친 채 멈춘다. 남은 시간은 추정하지 않는다.
import type { ActionId } from './agentMock.ts';

export type StepKey = 'understand' | 'target' | 'confirm' | 'exec';
/** 대기 ○ · 진행 ◌ · 완료 ✓ · 확인 대기 ? · 실패 ! · 건너뜀 */
export type StepStatus = 'pending' | 'active' | 'done' | 'wait' | 'fail' | 'skip';
export type RunPhase = 'running' | 'done' | 'fail' | 'stopped' | 'cancelled';

export const STEP_NAMES: Record<StepKey, string> = { understand: '명령 이해', target: '대상 찾기', confirm: '확인', exec: '실행' };

/** 경과 초를 보이기 시작하는 때(초) */
export const SHOW_ELAPSED_FROM_SEC = 3;
/** 엑사원 경로 최대 대기(초). 넘으면 멈추고 실패로 둔다 */
export const MODEL_TIMEOUT_SEC = 30;

/** 명령을 이해한 뒤 정하는 단계 목록. 상태를 바꾸는 행동(T03 · T05)만 확인 단계를 둔다(대상 1건이면 건너뜀) */
export function stepsFor(action: ActionId | null, confirmable: readonly ActionId[]): StepKey[] {
  return action !== null && confirmable.includes(action) ? ['understand', 'target', 'confirm', 'exec'] : ['understand', 'target', 'exec'];
}

/** 진행 중 단계 이름(진행형) */
export function activeLabel(step: StepKey, action: ActionId | null): string {
  switch (step) {
    case 'understand':
      return '명령을 이해하는 중…';
    case 'target':
      if (action === 'T04') return '되돌릴 행동을 찾는 중…';
      if (action === 'T06') return '답장이 없는 메일을 찾는 중…';
      if (action === 'T07') return '고른 메일을 확인하는 중…';
      if (action === 'T01') return '오늘 업무를 모으는 중…';
      return '대상 업무를 찾는 중…';
    case 'confirm':
      return '확인을 기다리고 있어요';
    case 'exec':
      if (action === 'T03') return '완료로 바꾸는 중…';
      if (action === 'T05') return '미루는 중…';
      if (action === 'T04') return '되돌리는 중…';
      if (action === 'T07') return '초안을 만드는 중…';
      return '결과를 정리하는 중…';
  }
}

/** 경과 초. 3초 전에는 null(보이지 않음) */
export function elapsedSec(startedAtMs: number, nowMs: number): number {
  return Math.max(0, Math.floor((nowMs - startedAtMs) / 1000));
}

/** 끝난 뒤 걸린 시간(초). 1초 미만도 '1초'로 보인다 */
export function finalSec(startedAtMs: number, endedAtMs: number): number {
  return Math.max(1, Math.round((endedAtMs - startedAtMs) / 1000));
}

export interface RunningLineInput {
  steps: readonly StepKey[];
  status: readonly StepStatus[];
  action: ActionId | null;
  elapsed: number;
}

/**
 * 진행 중 한 줄: { label, meta }. 예: { '대상 업무를 찾는 중…', '2/4 · 3초' }.
 * 명령 이해가 3초를 넘으면 엑사원 경로다(규칙 경로는 1초 안에 끝난다). 응답이 오기 전에는 경로를 알 수 없으므로 시간으로 가른다.
 */
export function runningLine({ steps, status, action, elapsed }: RunningLineInput): { label: string; meta: string } {
  let idx = status.findIndex((s) => s === 'active' || s === 'wait');
  if (idx < 0) idx = Math.max(0, status.findIndex((s) => s === 'pending'));
  const step = steps[idx] ?? 'understand';
  const label =
    step === 'understand' && elapsed >= SHOW_ELAPSED_FROM_SEC
      ? `엑사원이 명령을 해석하는 중… (최대 ${MODEL_TIMEOUT_SEC}초)`
      : activeLabel(step, action);
  const meta = `${idx + 1}/${steps.length}${elapsed >= SHOW_ELAPSED_FROM_SEC ? ` · ${elapsed}초` : ''}`;
  return { label, meta };
}

/** 끝난 줄: 완료 "N단계 완료" · 실패 "처리하지 못했어요" · 중지 · 취소. meta는 "M초" */
export function finishedLine(phase: Exclude<RunPhase, 'running'>, status: readonly StepStatus[], sec: number): { label: string; meta: string } {
  const meta = `${sec}초`;
  if (phase === 'done') return { label: `${status.filter((s) => s === 'done').length}단계 완료`, meta };
  if (phase === 'fail') return { label: '처리하지 못했어요', meta };
  if (phase === 'cancelled') return { label: '취소했어요. 바뀐 것은 없어요', meta };
  return { label: '중지했어요. 바뀐 것은 없어요', meta };
}

/** 화면 읽기 프로그램에 알릴 단계 문구(말줄임표 없이). 단계가 바뀔 때만 바꾼다 */
export function announceText(text: string): string {
  return text.replace(/…/g, '').trim();
}
