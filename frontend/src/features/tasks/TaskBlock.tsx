import { useId, useState, type ReactNode } from 'react';
import { formatKstDateTime, formatKstTime } from './deadline.ts';
import type { TaskStatus } from '../../api/types.ts';
import { senderLabel, type ColumnView, type TaskView } from './aggregate.ts';

const VISIBLE = 3;

export function DueChip({ view }: { view: TaskView }) {
  const due = view.task.dueAtMs;
  switch (view.due) {
    case 'overdue':
      return (
        <span className="due" data-state="overdue">
          <span aria-hidden="true">⚠</span> 기한 지남 · {formatKstDateTime(due!)}
        </span>
      );
    case 'today':
      return (
        <span className="due" data-state="today">
          <span aria-hidden="true">⏱</span> 오늘 {formatKstTime(due!)} 마감
        </span>
      );
    case 'tomorrow':
      return (
        <span className="due" data-state="tomorrow">
          내일 {formatKstTime(due!)}
        </span>
      );
    case 'later':
      return (
        <span className="due" data-state="later">
          {formatKstDateTime(due!)}
        </span>
      );
    case 'none':
      return (
        <span className="due" data-state="none">
          기한 없음
        </span>
      );
  }
}

const STATUS_LABELS: Record<TaskStatus, string> = { pending: '미처리', done: '완료', excluded: '제외', snoozed: '나중에' };

/** 업무 한 줄. 메일 정보가 없으면 분류 태그 · 발신자 · 원문 제목 대신 '메일 정보 없음'을 보인다(값을 지어내지 않음). */
export function TaskRow({ view: v, showCategory, showStatus = false }: { view: TaskView; showCategory: boolean; showStatus?: boolean }) {
  return (
    <li className="task" data-mail={v.mailState}>
      <span className="task-text">
        {showCategory && v.mailState === 'found' && <span className="tag">{v.mail.category ?? '미분류'}</span>}
        <span>{v.task.text}</span>
      </span>
      <DueChip view={v} />
      <span className="task-meta">
        {showStatus && `상태: ${STATUS_LABELS[v.task.status]} · `}
        {v.mailState === 'found' ? `${senderLabel(v)} · 원문: ${v.mail.subject}` : '메일 정보 없음'}
      </span>
    </li>
  );
}

interface Props<K extends string> {
  column: ColumnView<K>;
  icon?: ReactNode;
  showCategory: boolean; // 왼쪽 칸에서만 업무 성격 태그를 붙인다(오른쪽은 칸 이름과 같아서 뺀다)
  emptyText: string; // 칸이 비었을 때 문구(emptyText.ts, 칸 종류별 함수로 만든다)
}

export function TaskBlock<K extends string>({ column, icon, showCategory, emptyText }: Props<K>) {
  const [expanded, setExpanded] = useState(false);
  const listId = useId();
  const titleId = useId();
  const n = column.items.length;
  const items = expanded ? column.items : column.items.slice(0, VISIBLE);

  return (
    <section className="card" aria-labelledby={titleId}>
      <div className="block-head">
        {icon && (
          <span className="block-icon" aria-hidden="true">
            {icon}
          </span>
        )}
        <h3 id={titleId}>{column.label}</h3>
        {column.overdue > 0 && (
          <span className="due" data-state="overdue">
            <span aria-hidden="true">⚠</span> 기한 지남 {column.overdue}
          </span>
        )}
        <span className="count" data-zero={n === 0}>
          {n}
          <span className="sr-only">건</span>
        </span>
      </div>
      {n === 0 ? (
        <p className="block-empty">{emptyText}</p>
      ) : (
        <ul className="tasks" id={listId}>
          {items.map((v) => (
            <TaskRow key={v.task.id} view={v} showCategory={showCategory} />
          ))}
        </ul>
      )}
      {n > VISIBLE && (
        <button type="button" className="block-more" aria-expanded={expanded} aria-controls={listId} onClick={() => setExpanded((e) => !e)}>
          {expanded ? '접기' : `+${n - VISIBLE}건 더 보기`}
        </button>
      )}
    </section>
  );
}
