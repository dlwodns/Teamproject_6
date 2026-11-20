// 단계 줄 = 작업 카드 (components.md 4.4 StepLine · UX-D8 · FE-15). 11-20 사용자 피드백으로 바꿈:
// - 펼치기(토글) 없이 늘 보인다. 진행 중 · 실패에는 단계 칸(명령 이해 → 대상 찾기 → (확인) → 실행)이 이어진 막대로 순서대로 찬다.
// - 다 끝나면 칸들이 하나로 합쳐져 완료 체크 하나("N단계 완료 · M초")만 남는다. 실패하면 칸을 둔 채 멈춰 어디서 멈췄는지 보인다.
// [취소]는 요청이 서버에 가 있는 동안만 보인다(확인을 기다리는 동안은 확인 카드의 [취소]가 같은 일을 한다).
// 단계 목록은 <ol>, 지금 단계에 aria-current="step". 글자는 agentSteps.ts가 정한다. 화면 읽기에는 패널 status 영역이 단계 바뀜만 알린다.
import { useEffect, useState } from 'react';
import { Button, Check, VisuallyHidden } from '../../ui/index.ts';
import type { Run } from './agentSession.ts';
import { elapsedSec, finalSec, finishedLine, JOB_STATE_TEXT, jobState, runningLine, STEP_NAMES, type StepStatus } from './agentSteps.ts';
import styles from './StepLine.module.css';

const STATUS_TEXT: Record<StepStatus, string> = {
  pending: '대기',
  active: '진행 중',
  done: '완료',
  wait: '확인 대기',
  fail: '실패',
  skip: '건너뜀',
};

/** 진행 중에만 1초마다 다시 그린다(경과 초) */
function useNow(running: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [running]);
  return now;
}

interface Props {
  run: Run;
  onStop: () => void;
}

export function StepLine({ run, onStop }: Props) {
  const running = run.phase === 'running';
  const now = useNow(running);
  const line = running
    ? runningLine({ steps: run.steps, status: run.status, action: run.action, elapsed: elapsedSec(run.startedAtMs, now) })
    : finishedLine(run.phase as Exclude<Run['phase'], 'running'>, run.status, finalSec(run.startedAtMs, run.endedAtMs ?? now), run.unsure);
  const execIdx = run.steps.indexOf('exec');
  const canStop = running && run.status[execIdx] === 'pending' && !run.status.includes('wait');
  const job = jobState(run.phase);
  const current = run.status.findIndex((s) => s === 'active' || s === 'wait' || s === 'fail');
  const showTrack = running || run.phase === 'fail';

  return (
    <div className={styles.line} data-phase={run.phase}>
      <div className={styles.head}>
        {run.phase === 'done' && (
          <span className={styles.check} aria-hidden="true">
            <Check size={14} strokeWidth={3} />
          </span>
        )}
        <span className={styles.label}>{line.label}</span>
        {/* 끝난 상태는 줄 글자가 이미 말하므로 화면 읽기용으로만 둔다 */}
        {job === 'running' ? <span className={styles.state}>{JOB_STATE_TEXT[job]}</span> : <VisuallyHidden>, {JOB_STATE_TEXT[job]}</VisuallyHidden>}
        <span className={styles.meta}>{line.meta}</span>
        {canStop && (
          <Button variant="ghost" size="sm" onClick={onStop}>
            취소
          </Button>
        )}
      </div>
      {showTrack && (
        <ol className={styles.track} style={{ gridTemplateColumns: `repeat(${run.steps.length}, minmax(0, 1fr))` }}>
          {run.steps.map((step, i) => {
            const status = run.status[i] ?? 'pending';
            const note = run.notes[step];
            return (
              <li key={step} className={styles.seg} data-status={status} aria-current={i === current ? 'step' : undefined}>
                <span className={styles.bar} aria-hidden="true">
                  <span className={styles.fill} />
                </span>
                <span className={styles.name}>
                  {STEP_NAMES[step]}
                  <VisuallyHidden> · {STATUS_TEXT[status]}</VisuallyHidden>
                </span>
                {note && <small className={styles.note}>{note}</small>}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
