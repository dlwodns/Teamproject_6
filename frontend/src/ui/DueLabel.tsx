// 기한 라벨 (components.md 3절 · UX-D10). 보여 주기만 한다 — 어떤 글자 · 종류인지는 부르는 쪽(features/tasks/deadline.ts)이 정한다.
// 보이는 글자는 짧게(D+2 · ASAP · 오늘 18:00 · 11/10(화) · 기한 없음), 화면 읽기용 전체 글자는 srText로 덧붙인다.
import styles from './DueLabel.module.css';
import { Tooltip } from './Tooltip.tsx';
import { VisuallyHidden } from './VisuallyHidden.tsx';

/** urgent = 기한 지남 · ASAP(검정) · today = 오늘 마감(파랑) · later = 기한 남음(초록) · none = 기한 없음 · 경과일(회색)
 *  done = 메일 목록 '완료'(초록) · overdue-mail = 메일 목록 '기한 지남'(검정) */
export type DueKind = 'urgent' | 'today' | 'later' | 'none' | 'done' | 'overdue-mail';

interface Props {
  kind: DueKind;
  text: string;
  /** 화면 읽기용으로 덧붙일 글자(예: "기한 지남 · 11/4(수) 18:00") */
  srText?: string;
  /** 마우스 올림 · 포커스 때 말풍선으로 보일 전체 시각. 있으면 라벨이 포커스를 받는다 */
  fullTime?: string;
}

export function DueLabel({ kind, text, srText, fullTime }: Props) {
  const label = (
    <span className={styles.due} data-kind={kind} tabIndex={fullTime ? 0 : undefined}>
      {text}
      {srText && <VisuallyHidden> · {srText}</VisuallyHidden>}
    </span>
  );
  return fullTime ? <Tooltip content={fullTime}>{label}</Tooltip> : label;
}
