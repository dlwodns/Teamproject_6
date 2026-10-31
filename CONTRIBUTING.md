# 작업 규칙

전체 규칙은 `docs/00_common/work_rules.md`에 있다. 핵심만 적는다.

1. 작업 전 `docs/10_planning/refs/PRD.md`와 자기 파트 `docs/<파트>/plan.md`를 읽는다.
2. 브랜치: `feature/` · `fix/` · `docs/` + 작업 번호 (예: `feature/FE-3-dashboard`). 커밋: `유형: 요약` (예: `feat: FE-3 업무 칸 렌더링`).
3-1. main 직접 푸시 금지. 작성자 외 1명 리뷰 승인 후 병합 (`docs/00_common/pr_review.md`).
3. AI는 commit까지만 한다. push · PR은 사람이 한다. Co-Authored-By는 넣지 않는다.
4. 결정 · 트러블슈팅 항목에는 상태 · 제안 · 결정 · 리뷰 · 공동 · 근거를 적는다.
5. 키 · 토큰 · 실제 메일은 코드와 문서에 넣지 않는다. Claude는 `eval/`에서만 쓴다.
