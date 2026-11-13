// 사용자 · 보낸 사람 표시(사진 없음, 이름 첫 글자). 옆에 이름이 따로 보이면 장식(aria-hidden)이다.
import styles from './Avatar.module.css';

interface Props {
  name: string;
  /** 옆에 이름이 보이지 않을 때만 true — 이름을 화면 읽기용으로 단다 */
  labelled?: boolean;
}

export function Avatar({ name, labelled = false }: Props) {
  const initial = Array.from(name.trim())[0] ?? '?';
  return labelled ? (
    <span className={styles.avatar} role="img" aria-label={name}>
      <span aria-hidden="true">{initial}</span>
    </span>
  ) : (
    <span className={styles.avatar} aria-hidden="true">
      {initial}
    </span>
  );
}
