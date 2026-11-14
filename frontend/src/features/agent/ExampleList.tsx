// 예시 명령 칩(눌러서 바로 실행). 소개 줄 아래와 '지원하지 않는 요청' 카드에서 쓴다.
// 명령이 진행 중이면 눌러도 보내지 않는다(aria-disabled, 포커스는 남는다).
import styles from './ExampleList.module.css';

interface Props {
  examples: readonly string[];
  busy: boolean;
  onRun: (text: string) => void;
  /** 목록 이름(화면 읽기용) */
  label: string;
}

export function ExampleList({ examples, busy, onRun, label }: Props) {
  return (
    <ul className={styles.list} aria-label={label}>
      {examples.map((text) => (
        <li key={text}>
          <button type="button" className={styles.chip} aria-disabled={busy || undefined} onClick={() => !busy && onRun(text)}>
            {text}
          </button>
        </li>
      ))}
    </ul>
  );
}
