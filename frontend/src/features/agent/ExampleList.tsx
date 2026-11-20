// 예시 명령 칩(눌러서 바로 실행). 소개 줄 아래와 '지원하지 않는 요청' 카드에서 쓴다.
// 앞 명령이 진행 중이어도 바로 보낸다(11-20).
import styles from './ExampleList.module.css';

interface Props {
  examples: readonly string[];
  onRun: (text: string) => void;
  /** 목록 이름(화면 읽기용) */
  label: string;
}

export function ExampleList({ examples, onRun, label }: Props) {
  return (
    <ul className={styles.list} aria-label={label}>
      {examples.map((text) => (
        <li key={text}>
          <button type="button" className={styles.chip} onClick={() => onRun(text)}>
            {text}
          </button>
        </li>
      ))}
    </ul>
  );
}
