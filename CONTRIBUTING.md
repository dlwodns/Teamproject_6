# 작업 규칙

전체 규칙은 `docs/00_common/work_rules.md`에 있다. 핵심만 적는다.

1. 작업 전 `docs/10_planning/refs/PRD.md`와 자기 파트 `docs/<파트>/plan.md` · `detail.md`(있으면)를 읽는다.
2. 브랜치
   - 기능 · 수정: `feature/` · `fix/` · `docs/` + 작업 번호 (예: `feature/FE-3-dashboard`, `fix/BE-2-dummy-load`) (D32 · D33)
   - 파트 문서 브랜치: `feature/<파트 약어>` (예: `feature/AI` · `feature/PL`). 한 파트의 상세 명세 · 계획 문서를 모아 올린다.
   - 여러 파트가 함께 보는 문서(`docs/00_common/` · PRD · 루트와 폴더 README · `.env.example` · `eval/README.md` 등)는 main에서 고친다. log · handoff는 충돌을 피하려고 main에서만 고친다.
   - 환경 설정: 한 파트만 읽는 값(예: 엑사원 변수는 ai · eval만)은 그 파트 브랜치에 커밋한다. 여러 파트가 같은 값을 써야 하는 항목(공용 주소 · 루트 README 환경 변수 표)은 파트 브랜치에서 작업하는 중이라도 main에 커밋할 수 있다. 파트 브랜치 코드가 있어야 동작하는 항목은 "(`feature/…` 병합 후)"라고 적는다.
3. 커밋: `유형: 요약`, 요약 앞에 작업 번호 (예: `feat: FE-3 업무 칸 렌더링`). 커밋 작성자는 사람 한 명이고 Co-Authored-By는 넣지 않는다. AI가 만든 커밋도 공동 저자 줄 없이 작성자 한 명으로 남긴다.
4. main 직접 푸시 금지. 작성자 외 1명 리뷰 승인 후 병합한다 (`docs/00_common/pr_review.md`).
5. AI는 commit까지만 한다. push · PR은 사람이 한다.
6. 결정 · 트러블슈팅 항목에는 상태 · 제안 · 결정 · 리뷰 · 공동 · 근거를 적는다.
7. 키 · 토큰 · 실제 메일은 코드와 문서에 넣지 않는다. Claude · OpenRouter는 `eval/`에서만 쓴다(D26 · D41).
