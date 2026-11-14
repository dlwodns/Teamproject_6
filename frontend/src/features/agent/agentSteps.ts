// 단계 줄 글자 (components.md 4.4 StepLine · wireframe 13-4 · UX-D8). 순수 함수, node --test 대상.
// 명령 이해 → 대상 찾기 → (확인) → 실행. 명령 이해 · 대상 찾기는 요청 하나(POST /api/agent/command)가 함께 한다.
// 진행 중엔 한 줄 "…하는 중 · n/전체 · 경과 N초(3초부터)", 끝나면 "N단계 완료 · M초"로 접고, 실패하면 펼친 채 멈춘다.
// 남은 시간은 추정하지 않는다. 행동 ID(T03 등)는 서버가 준 글자 그대로 받는다.

export type StepKey = 'understand' | 'target' | 'confirm' | 'exec';
/** 대기 ○ · 진행 ◌ · 완료 ✓ · 확인 대기 ? · 실패 ! · 건너뜀 */
export type StepStatus = 'pending' | 'active' | 'done' | 'wait' | 'fail' | 'skip';
export type RunPhase = 'running' | 'done' | 'fail' | 'stopped' | 'cancelled';

export const STEP_NAMES: Record<StepKey, string> = { understand: '명령 이해', target: '대상 찾기', confirm: '확인', exec: '실행' };

/** 경과 초를 보이기 시작하는 때(초) */
export const SHOW_ELAPSED_FROM_SEC = 3;
/**
 * 엑사원 경로 최대 대기(초). 넘으면 멈추고 실패로 둔다.
 * HTTP 제한(`SLOW_REQUEST_TIMEOUT_MS` 140초)과 같게 둔다(#63 리뷰): backend는 ai를 130초까지 기다리고 화면이 끊어도 끝까지 실행하므로,
 * 30초에 먼저 끊으면 엑사원 API가 조금만 늦어도 화면은 실패인데 실제로는 처리된 일이 생긴다
 */
export const MODEL_TIMEOUT_SEC = 140;

/** 확인 단계를 둘 수 있는 행동(상태 변경). 대상 1건이면 확인을 건너뛴 것으로 표시한다(D37) */
export const CONFIRMABLE: readonly string[] = ['T03', 'T05', 'T10'];

/** 명령을 이해한 뒤 정하는 단계 목록. 상태를 바꾸는 행동만 확인 단계를 둔다 */
export function stepsFor(action: string | null, confirmable: readonly string[] = CONFIRMABLE): StepKey[] {
  return action !== null && confirmable.includes(action) ? ['understand', 'target', 'confirm', 'exec'] : ['understand', 'target', 'exec'];
}

/** 명령 이해 단계 아래 한 줄: 'T03 일괄_완료 · 규칙'. 경로(규칙 · 엑사원)는 응답이 온 뒤에야 안다 */
export function understandNote(action: string | null, actionName: string | null, source: 'agent_rule' | 'agent_model' | null): string | null {
  const how = source === 'agent_rule' ? '규칙' : source === 'agent_model' ? '엑사원' : null;
  const what = [action, actionName].filter(Boolean).join(' ');
  const parts = [what, how].filter((x): x is string => Boolean(x));
  return parts.length ? parts.join(' · ') : null;
}

/** 진행 중 단계 이름(진행형) */
export function activeLabel(step: StepKey, action: string | null): string {
  switch (step) {
    case 'understand':
      return '명령을 이해하는 중…';
    case 'target':
      if (action === 'T04') return '되돌릴 행동을 찾는 중…';
      if (action === 'T06') return '답장이 없는 메일을 찾는 중…';
      if (action === 'T07') return '고른 메일을 확인하는 중…';
      if (action === 'T01') return '오늘 업무를 모으는 중…';
      if (action === 'T02') return '미처리 업무를 찾는 중…';
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
  action: string | null;
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

/** 중지했지만 서버가 이미 처리했을 수 있을 때(요청을 보낸 뒤 중지) */
export const STOPPED_UNSURE_TEXT = '중지했어요. 처리됐는지는 업무 목록에서 확인해 주세요';

/**
 * 끝난 줄: 완료 "N단계 완료" · 실패 "처리하지 못했어요" · 중지 · 취소. meta는 "M초".
 * unsure: 요청이 서버에 간 뒤 중지했다 → '바뀐 것은 없어요'를 약속하지 않는다
 */
export function finishedLine(
  phase: Exclude<RunPhase, 'running'>,
  status: readonly StepStatus[],
  sec: number,
  unsure = false,
): { label: string; meta: string } {
  const meta = `${sec}초`;
  if (phase === 'done') return { label: `${status.filter((s) => s === 'done').length}단계 완료`, meta };
  if (phase === 'fail') return { label: '처리하지 못했어요', meta };
  if (phase === 'cancelled') return { label: '취소했어요. 바뀐 것은 없어요', meta };
  return { label: unsure ? STOPPED_UNSURE_TEXT : '중지했어요. 바뀐 것은 없어요', meta };
}

/** 화면 읽기 프로그램에 알릴 단계 문구(말줄임표 없이). 단계가 바뀔 때만 바꾼다 */
export function announceText(text: string): string {
  return text.replace(/…/g, '').trim();
}
