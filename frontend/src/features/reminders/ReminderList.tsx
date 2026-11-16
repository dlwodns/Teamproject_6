// 리마인더 목록 (FE-16 · 명세 5절 가운데 칸). 11-14: 슬랙 · 디스코드 알림봇 메시지처럼 한 건 = 카드 한 장.
//   업무 유형(크고 아주 굵게)
//   보낸 사람
//   업무 내용
//   캐치봇 메시지(이유 한 문장)
//   ▍메일 열기 ›  (왼쪽 선이 있는 첨부 칸 — 누르면 그 메일로 간다)
// - 카드 본문 버튼을 누르면 오른쪽 상세가 열린다. 메일 칸은 따로 누르는 버튼이라 목록 상자(listbox) 대신 목록 + 버튼으로 둔다(Tab으로 옮긴다)
// - 고른 카드는 진한 테두리 + aria-current
// - '조용히 둔 것 N건'은 맨 아래 접기 한 곳에(알림을 3번 보내 이제 목록에만 두는 항목)
// - 11-15: 이 순서(ReminderSummary)를 상세 · 패널 미리보기도 함께 쓴다(어디서나 같은 순서로 읽힌다)
import type { ReactNode } from 'react';
import type { ReminderItem } from '../../api/contract.ts';
import { ChevronRight, Collapsible, cx } from '../../ui/index.ts';
import type { DashboardSource } from '../../api/types.ts';
import { senderLookup } from '../agent/agentText.ts';
import { counterpartText, TASK_TYPE_LABEL, TYPE_LABEL } from './reminderModel.ts';
import styles from './ReminderList.module.css';

interface Props {
  label: string;
  items: readonly ReminderItem[];
  quiet: readonly ReminderItem[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
  /** 보낸 사람 이름(없으면 그 줄을 그리지 않는다) */
  whoOf: (item: ReminderItem) => string | null;
  /** 메일로 갈 수 있으면 여는 함수, 없으면 null(메일 칸을 그리지 않는다) */
  openMailOf: (item: ReminderItem) => (() => void) | null;
  empty: ReactNode;
}

/** 보낸 사람: 서버가 준 상대(이름 · 직책), 없으면 메일 보낸 사람 */
export function reminderWho(item: ReminderItem, source: DashboardSource | undefined): string | null {
  return counterpartText(item) ?? (item.mailId === null ? null : senderLookup(source)(item.mailId));
}

interface SummaryProps {
  item: ReminderItem;
  who: string | null;
  /** 업무 칸에 넣을 것(상세는 제목 h2). 없으면 업무 글자 */
  title?: ReactNode;
  /** 버튼 밖(상세)에서는 div로 그린다 — 버튼 안에는 span만 들어간다 */
  block?: boolean;
}

/** 알림 한 건의 글: 업무 유형(굵게) · 보낸 사람 · 업무 · 캐치봇 메시지. 목록 카드 · 상세 · 패널이 같은 순서로 쓴다 */
export function ReminderSummary({ item, who, title, block = false }: SummaryProps) {
  const T = block ? 'div' : 'span';
  return (
    <>
      <T className={styles.kind}>{item.taskType ? TASK_TYPE_LABEL[item.taskType] : TYPE_LABEL[item.type]}</T>
      {who && (
        <T className={styles.field}>
          <span className={styles.fieldName}>보낸 사람</span>
          <span className={styles.fieldValue}>{who}</span>
        </T>
      )}
      <T className={styles.field}>
        <span className={styles.fieldName}>업무</span>
        <T className={styles.fieldValue}>{title ?? item.title}</T>
      </T>
      <T className={styles.message}>{item.reason}</T>
    </>
  );
}

/** 메일 열기 칸(슬랙 첨부 모양) */
export function MailLink({ onClick, title }: { onClick: () => void; title: string }) {
  return (
    <button type="button" className={styles.mail} onClick={onClick} aria-label={`메일 열기: ${title}`}>
      <span>메일 열기</span>
      <ChevronRight size={16} aria-hidden="true" />
    </button>
  );
}

/** 카드 본문 버튼 id(목록 밖에서 포커스를 옮길 때) */
export const reminderOptionId = (key: string) => `reminder-option-${key.replace(/[^A-Za-z0-9_-]/g, '-')}`;

function Cards({ label, items, selectedKey, onSelect, whoOf, openMailOf }: Omit<Props, 'quiet' | 'empty'>) {
  return (
    <ul aria-label={label} className={styles.list}>
      {items.map((it) => {
        const selected = it.key === selectedKey;
        const who = whoOf(it);
        const openMail = openMailOf(it);
        return (
          <li key={it.key} className={cx(styles.card, selected && styles.selected)}>
            <button
              type="button"
              id={reminderOptionId(it.key)}
              className={styles.main}
              aria-current={selected ? 'true' : undefined}
              onClick={() => onSelect(it.key)}
            >
              <ReminderSummary item={it} who={who} />
            </button>
            {openMail && <MailLink onClick={openMail} title={it.title} />}
          </li>
        );
      })}
    </ul>
  );
}

export function ReminderList({ empty, quiet, ...rest }: Props) {
  if (rest.items.length === 0 && quiet.length === 0) return <div className={styles.empty}>{empty}</div>;
  const quietSelected = quiet.some((q) => q.key === rest.selectedKey);
  return (
    <div className={styles.root}>
      {rest.items.length > 0 && <Cards {...rest} />}
      {quiet.length > 0 && (
        <Collapsible className={styles.quiet} label={<span className={styles.quietLabel}>{`조용히 둔 것 ${quiet.length}건`}</span>} defaultOpen={quietSelected}>
          <Cards {...rest} label={`${rest.label} · 조용히 둔 것`} items={quiet} />
        </Collapsible>
      )}
    </div>
  );
}
