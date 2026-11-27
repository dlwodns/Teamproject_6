# docs · 문서 지도

| 폴더 | 파트 | 들어 있는 것 |
|---|---|---|
| `00_common/` | 공통 | 작업 규칙 · PR 리뷰 규칙(`pr_review.md`) · 공통 decisions · 기여도 · AI 활용 기록(`ai_usage.md`) · log · handoff · 구조도(`architecture.md`, 그림은 `img/architecture/`) · 템플릿(`templates/`) |
| `10_planning/` | 기획 | 구현계획 · decisions · 트러블슈팅 · `detail.md`(상세 명세) · `suggestion_cards.md`(에이전트 제안 카드 규칙, D50) · `agent_pickle_plan.md`(피클 벤치마킹 계획 · 명세, PL-16) · `reminders.md`(리마인더 · 에이전트 메뉴 명세, PL-18) · `agent_scenarios.md`(에이전트 시나리오 평가) · `ir_draft.md`(IR 발표 초안, PL-19) · `refs/`(PRD · 인터뷰 · 벤치마킹 · 조사, 목차는 `refs/README.md`) |
| `20_frontend/` | 프론트엔드 | 구현계획 · decisions · 트러블슈팅 · 와이어프레임 · `design_system.md`(디자인 토큰) · `components.md`(부품 명세) · `outlook_benchmark.md`(Outlook 벤치마킹) · `be3_contract_comparison.md`(BE-3 계약 비교) · `ui_reference/`(시안) |
| `30_backend/` | 백엔드 (메일 연동 · 개인정보 · DB · API) | `README.md`(파트 안내) · `detail.md`(상세 명세) · `agent_api_contract.md`(에이전트 API 계약) · 구현계획 · decisions · 트러블슈팅 |
| `40_ai/` | AI (엑사원 분류 · 에이전트 · 음성) | `README.md`(엑사원 역할 · 파트 역할) · `detail.md`(상세 명세) · `io_spec.md`(입출력 정의서) · `service_overview.md`(팀원용 한눈에 보기) · 구현계획 · decisions · 트러블슈팅 |
| `50_data_eval/` | 데이터 · 평가 (더미 메일 · Claude 채점) | 구현계획 · decisions · 트러블슈팅 · `scores.md`(점수 기록) · `sealed_sets.md`(봉인 세트) · `label_guide.md`(라벨 가이드) · `error_analysis.md`(놓친 메일 원인) |
| `user-manual/` | 사용자 (비개발자) | 화면만 보고 쓰는 방법: 접속 · Outlook 연결 · 대시보드 · 메일 · 캐치봇 · 설정 · 이럴 때는. 캡처는 `img/` |
| `assets/` | 공통 그림 | `brand/`(로고 라이트 · 다크) · `screenshots/`(루트 README 화면 캡처) |

## 파트마다 같은 파일 3개

| 파일 | 무엇을 쓰나 | 번호 |
|---|---|---|
| `plan.md` | 목표 · 범위 · 작업 목록 · 다른 파트와의 접점 · 완료 기준 | 작업 `FE-1` |
| `decisions.md` | 파트 결정과 근거, 누가 제안 · 결정 · 리뷰했는지 | 결정 `FE-D1` |
| `troubleshooting.md` | 문제 · 원인 · 해결 · 재발 방지, 누가 발견 · 해결했는지 | 문제 `FE-T1` |

파트 약어: 공통 `D` · 기획 `PL` · 프론트엔드 `FE`(화면 설계 결정은 `UX-D`) · 백엔드 `BE` · AI `AI` · 데이터 · 평가 `DE` · 인프라 `INF`

- 인프라 문서는 docs가 아니라 루트 `infra/`에 둔다(`README.md` 폴더 규칙 · 배포 구성 · `plan.md` 할 일 · `status.md` 한 일 · `railway_setup.md` 배포 설정).
- 먼저 읽을 것: `00_common/work_rules.md`(규칙) → 자기 파트 `plan.md`. 지금 상태는 `00_common/handoff.md`.
- 기여도 표기 방법: `00_common/work_rules.md` 3절, 집계: `00_common/contribution.md`
- 2026-10-30에 `Project_Rocket6/docs`에서 복사해 재배치했다. 원본은 그대로 있다.
