import type { ReactNode } from 'react';

interface Props {
  title: string;
  children: ReactNode;
}

/** 메뉴로 이동은 되지만 기능은 아직 없는 화면. 작업 번호 · 후속 계획은 화면이 아니라 frontend/README.md에 둔다. */
export function ComingSoon({ title, children }: Props) {
  return (
    <section className="card coming" aria-labelledby="page-title">
      <div className="page-head" style={{ marginBottom: 0 }}>
        <h1 id="page-title" tabIndex={-1}>
          {title}
        </h1>
        <span className="badge-soon">준비 중</span>
      </div>
      {children}
      <p>
        <a href="#/dashboard">대시보드로 돌아가기</a>
      </p>
    </section>
  );
}
