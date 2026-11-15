// 답장 후 완료 확인 아래 시트 BS (wireframe 13-5 · UX-D5 · UX-D6 · UX-D11).
// 제목 "완료로 처리할까요?" · 그 메일의 끝나지 않은 업무(기본 체크, 풀면 남김) · ☐ 오늘 다시 보지 않음 · [아니오] [예].
// 다른 설명 문구는 두지 않는다. 아니오 · Esc · 바깥 · 쓸어내리기는 모두 onNo(ui Sheet가 모은다), 열리면 [예]에 포커스.
import { useState } from 'react';
import type { Task, TaskId } from '../../api/types.ts';
import { Checkbox, DueLabel, Sheet } from '../../ui/index.ts';
import styles from './CompleteSheet.module.css';
import { taskDue } from './mailboxes.ts';

interface Props {
  open: boolean;
  tasks: Task[];
  asOfMs: number;
  /** '오늘 다시 보지 않음'을 저장할 수 있는가(설정에 그 칸이 있을 때만 보인다) */
  canSkip: boolean;
  busy: boolean;
  onYes: (taskIds: TaskId[], skipToday: boolean) => void;
  onNo: () => void;
  /** 확인 문구. 기본은 완료, 여러 통을 고른 Delete는 '제외'(#59 리뷰 · D37) */
  title?: string;
}

export function CompleteSheet({ open, tasks, asOfMs, canSkip, busy, onYes, onNo, title = '완료로 처리할까요?' }: Props) {
  // 시트를 열 때마다 부른 쪽이 key를 바꿔 새로 그린다 → 처음 상태는 모두 체크 · 오늘 다시 보지 않음 꺼짐
  const [checked, setChecked] = useState<ReadonlySet<TaskId>>(() => new Set(tasks.map((t) => t.id)));
  const [skip, setSkip] = useState(false);

  const toggle = (id: TaskId, on: boolean) =>
    setChecked((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });

  return (
    <Sheet
      open={open}
      title={title}
      yesLoading={busy}
      onYes={() => onYes(tasks.filter((t) => checked.has(t.id)).map((t) => t.id), canSkip && skip)}
      onNo={onNo}
    >
      <ul className={styles.list}>
        {tasks.map((t) => {
          const due = taskDue(t, asOfMs);
          return (
            <li key={t.id} className={styles.item}>
              <Checkbox checked={checked.has(t.id)} onCheckedChange={(on) => toggle(t.id, on)} label={<span className={styles.text}>{t.text}</span>} />
              <DueLabel kind={due.kind} text={due.text} srText={due.full ?? undefined} />
            </li>
          );
        })}
      </ul>
      {canSkip && <Checkbox checked={skip} onCheckedChange={setSkip} label="오늘 다시 보지 않음" />}
    </Sheet>
  );
}
