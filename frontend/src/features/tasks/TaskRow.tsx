// 업무 줄 R (components.md 4.2): ☐ · 업무 글자 · 새 업무 점 · 둘째 줄 발신자(긴급 칸은 + 유형) · 오른쪽 기한 라벨.
// 줄(글자)을 누르면 메일 화면의 그 메일로, 체크 상자는 이동하지 않고 완료 요청만 한다.
// 완료 중에는 같은 업무의 모든 줄에 data-leaving이 붙어 CSS만으로 빠진다(TaskRow.module.css).
import { useRef, type ReactNode } from 'react';
import { Checkbox, DueLabel, VisuallyHidden } from '../../ui/index.ts';
import type { TaskRowModel } from './aggregate.ts';
import styles from './TaskRow.module.css';
import { useOpenMail } from './useOpenMail.ts';
import { useCompleteTask, useCompletionPhase } from './useTaskCompletion.ts';

/** 업무 줄 목록 */
export function TaskRowList({ children }: { children: ReactNode }) {
  return <ul className={styles.list}>{children}</ul>;
}

/** 줄이 사라진 뒤 포커스가 갈 곳: 같은 목록의 같은 자리(없으면 바로 위) 체크 상자 */
function refocusInList(list: HTMLElement | null, index: number) {
  if (!list?.isConnected) return;
  const active = document.activeElement;
  if (active && active !== document.body && active.isConnected) return; // 사용자가 이미 다른 곳으로 옮겼다
  const boxes = list.querySelectorAll<HTMLElement>('[role="checkbox"]');
  const next = boxes[Math.min(index, boxes.length - 1)];
  next?.focus();
}

interface Props {
  row: TaskRowModel;
  /** 둘째 줄에 유형을 덧붙인다(긴급 칸 · 사이드바) */
  showType?: boolean;
}

export function TaskRow({ row, showType = false }: Props) {
  const phase = useCompletionPhase(row.id);
  const completeTask = useCompleteTask();
  const openMail = useOpenMail();
  const ref = useRef<HTMLLIElement>(null);

  const onChecked = (checked: boolean) => {
    if (!checked || phase !== undefined) return;
    const li = ref.current;
    const list = li?.parentElement ?? null;
    const index = list && li ? Array.prototype.indexOf.call(list.children, li) : 0;
    void completeTask(row.id).then((ok) => {
      if (ok) requestAnimationFrame(() => refocusInList(list, index));
    });
  };

  const sub = `${row.sender ?? '메일 정보 없음'}${showType && row.type ? ` · ${row.type}` : ''}`;
  const body = (
    <>
      <span className={styles.title}>
        <span className={styles.text}>{row.text}</span>
        {row.isNew && (
          <>
            <span className={styles.newDot} aria-hidden="true" />
            <VisuallyHidden>새 업무</VisuallyHidden>
          </>
        )}
      </span>
      <span className={styles.sub}>{sub}</span>
    </>
  );

  return (
    <li ref={ref} className={styles.row} data-leaving={phase === 'leaving' ? '' : undefined} data-task={row.id}>
      <div className={styles.clip}>
        <div className={styles.inner}>
          <Checkbox checked={phase !== undefined} onCheckedChange={onChecked} aria-label={row.text} />
          {row.sender === null ? (
            // 메일 정보가 없으면 갈 곳이 없으므로 이동 버튼을 만들지 않는다
            <span className={styles.body}>{body}</span>
          ) : (
            <button type="button" className={styles.body} onClick={() => openMail(row.mailId)}>
              {body}
            </button>
          )}
          <DueLabel
            kind={row.due.kind}
            text={row.due.text}
            srText={row.due.srText ?? undefined}
            fullTime={row.due.fullTime ?? undefined}
          />
        </div>
      </div>
    </li>
  );
}
