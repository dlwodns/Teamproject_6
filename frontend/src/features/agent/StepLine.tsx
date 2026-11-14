// 단계 줄 (components.md 4.4 StepLine · UX-D8). 진행 중엔 한 줄 + [중지], 끝나면 "N단계 완료 · M초"로 접힘,
// 실패하면 펼친 채 멈춘다. 단계 목록은 <ol>, 지금 단계에 aria-current="step". 글자는 agentSteps.ts가 정한다.
// 화면 읽기 프로그램에는 패널의 status 영역 하나가 단계 바뀜만 알린다 — 이 줄의 초 단위 글자는 알리지 않는다.
import { useEffect, useState } from 'react';
import { Button, Check, Collapsible, VisuallyHidden } from '../../ui/index.ts';
import type { Run } from './agentSession.ts';
import { elapsedSec, finalSec, finishedLine, runningLine, STEP_NAMES, type StepStatus } from './agentSteps.ts';
import styles from './StepLine.module.css';

const STATUS_TEXT: Record<StepStatus, string> = {
  pending: '대기',
  active: '진행 중',
  done: '완료',
  wait: '확인 대기',
  fail: '실패',
  skip: '건너뜀',
};

function StepDot({ status }: { status: StepStatus }) {
  return (
    <span className={styles.dot} data-status={status} aria-hidden="true">
      {status === 'done' && <Check size={14} strokeWidth={3} />}
      {status === 'fail' && '!'}
      {status === 'wait' && '?'}
    </span>
  );
}

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
  const [open, setOpen] = useState(run.phase === 'fail');
  // 실패하면 펼친 채 멈춘다. 완료 · 중지되면 접는다
  useEffect(() => {
    setOpen(run.phase === 'fail');
  }, [run.phase]);

  const line = running
    ? runningLine({ steps: run.steps, status: run.status, action: run.action, elapsed: elapsedSec(run.startedAtMs, now) })
    : finishedLine(run.phase as Exclude<Run['phase'], 'running'>, run.status, finalSec(run.startedAtMs, run.endedAtMs ?? now), run.unsure);
  const headStatus: StepStatus = running
    ? run.status.includes('wait')
      ? 'wait'
      : 'active'
    : run.phase === 'done'
      ? 'done'
      : run.phase === 'fail'
        ? 'fail'
        : 'skip';
  const execIdx = run.steps.indexOf('exec');
  const canStop = running && run.status[execIdx] === 'pending';
  const current = run.status.findIndex((s) => s === 'active' || s === 'wait' || s === 'fail');

  return (
    <div className={styles.line} data-phase={run.phase} data-stoppable={canStop || undefined}>
      <Collapsible
        open={open}
        onOpenChange={setOpen}
        label={
          <span className={styles.head}>
            <StepDot status={headStatus} />
            <span className={styles.label}>{line.label}</span>
            <span className={styles.meta}>{line.meta}</span>
            <VisuallyHidden>, 단계 보기</VisuallyHidden>
          </span>
        }
      >
        <ol className={styles.steps}>
          {run.steps.map((step, i) => {
            const status = run.status[i] ?? 'pending';
            const note = run.notes[step];
            return (
              <li key={step} className={styles.step} data-status={status} aria-current={i === current ? 'step' : undefined}>
                <StepDot status={status} />
                <span className={styles.stepText}>
                  {STEP_NAMES[step]}
                  {status === 'skip' ? ' · 건너뜀' : <VisuallyHidden> · {STATUS_TEXT[status]}</VisuallyHidden>}
                  {note && <small className={styles.note}>{note}</small>}
                </span>
              </li>
            );
          })}
        </ol>
      </Collapsible>
      {canStop && (
        <Button variant="ghost" size="sm" className={styles.stop} onClick={onStop}>
          중지
        </Button>
      )}
    </div>
  );
}
