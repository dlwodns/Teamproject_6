import { useId, useState, type ReactNode } from 'react';
import { formatKstDateTime, formatKstTime } from './deadline.ts';
import { senderLabel, type ColumnView, type TaskView } from './aggregate.ts';
import { emptyColumnText } from './emptyText.ts';

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

interface Props<K extends string> {
  column: ColumnView<K>;
  icon?: ReactNode;
  showCategory: boolean; // 왼쪽 칸에서만 업무 성격 태그를 붙인다(오른쪽은 칸 이름과 같아서 뺀다)
}

export function TaskBlock<K extends string>({ column, icon, showCategory }: Props<K>) {
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
        <span className="count" data-zero={n === 0} aria-label={`${n}건`}>
          {n}
        </span>
      </div>
      {n === 0 ? (
        <p className="block-empty">{emptyColumnText(column.key, column.label)}</p>
      ) : (
        <ul className="tasks" id={listId}>
          {items.map((v) => (
            <li className="task" key={v.task.id}>
              <span className="task-text">
                {showCategory && <span className="tag">{v.mail.category ?? '미분류'}</span>}
                <span>{v.task.text}</span>
              </span>
              <DueChip view={v} />
              <span className="task-meta">
                {senderLabel(v)} · 원문: {v.mail.subject}
              </span>
            </li>
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
