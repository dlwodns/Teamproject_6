// 선택한 메일 줄 (components.md 4.4 SelectedMailBar). 메일 화면에서 고른 메일 제목 + [빼기].
// '이거 완료' · '이 메일 회신 초안 써줘'처럼 가리키는 말을 이 메일로 해석하도록 명령과 함께 메일 번호를 보낸다.
import { Button } from '../../ui/index.ts';
import styles from './SelectedMailBar.module.css';

interface Props {
  /** 메일 제목. 원자료를 아직 못 불러왔으면 null */
  subject: string | null;
  onRemove: () => void;
}

export function SelectedMailBar({ subject, onRemove }: Props) {
  return (
    <div className={styles.bar}>
      <span className={styles.label}>선택한 메일</span>
      <b className={styles.subject} title={subject ?? undefined}>
        {subject ?? '제목을 불러오는 중'}
      </b>
      <Button variant="ghost" size="sm" onClick={onRemove} aria-label={`선택한 메일 빼기${subject ? `: ${subject}` : ''}`}>
        빼기
      </Button>
    </div>
  );
}
