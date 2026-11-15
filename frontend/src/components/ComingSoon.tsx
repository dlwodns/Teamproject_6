import type { ReactNode } from 'react';
import { Link } from 'react-router';
import styles from './ComingSoon.module.css';

interface Props {
  /** 있으면 화면 하나 전체(h1#page-title)로 그린다. 없으면 패널 · 팝오버 안에 넣는 '준비 중' 자리 */
  title?: string;
  children?: ReactNode;
}

/** 이동은 되지만 기능은 아직 없는 화면 · 자리. 작업 번호 · 후속 계획은 화면이 아니라 frontend/README.md에 둔다. */
export function ComingSoon({ title, children }: Props) {
  if (title === undefined) {
    return (
      <div className={styles.body}>
        <span className={styles.badge}>준비 중</span>
        {children}
      </div>
    );
  }
  return (
    <section className={styles.page} aria-labelledby="page-title">
      <div className={styles.head}>
        <h1 id="page-title" className={styles.title} tabIndex={-1}>
          {title}
        </h1>
        <span className={styles.badge}>준비 중</span>
      </div>
      <div className={styles.body}>
        {children}
        <Link className={styles.link} to="/dashboard">
          대시보드로 돌아가기
        </Link>
      </div>
    </section>
  );
}
