# refs · 기획 참고 문서 목차

> 갱신: 2026-11-02 · 이 폴더에는 성격이 다른 문서 세 종류가 함께 있다. 고치기 전에 아래 '성격'과 '규칙'을 먼저 본다.

## 1. 문서 성격

| 성격 | 규칙 |
|---|---|
| **최종** | 항상 현재 정답만 남긴다. 내용이 바뀌면 덮어쓰고, 이전 버전은 `.backup/`에 둔다 |
| **누적** | 지우지 않고 계속 붙인다. 질문지 · 결론 줄만 고쳐 쓴다 |
| **기록** | 그날의 조사 · 회의 기록이다. 다시 고치지 않는다. 결론은 PRD · decisions로 옮겨 간다 |

## 2. 목차

| 파일 | 성격 | 날짜 | 상태 | 내용 · 이어지는 곳 |
|---|---|---|---|---|
| [PRD.md](PRD.md) | 최종 | 2026-11-02 | **현재 유효 (v3.1)** | 한 단락 PRD · 6질문. 상세는 `../detail.md`(기획) · `../../40_ai/detail.md`(AI) |
| [benchmark.md](benchmark.md) | 누적 | 2026-11-02 | 현재 유효 | 벤치마킹 스크랩. 맨 위 결론 두 줄이 PRD Q3으로 올라간다. 최신 스크랩: 행동형 에이전트 · 국내 그룹웨어 · LG 사내 도구(11-02) |
| [interview.md](interview.md) | 누적 | 2026-11-02 | 현재 유효 | 인터뷰 질문지 · 기록. 1차 2026-10-16. 2차 질문지 추가분(11-02)은 맨 아래 |
| [research_pickle_20261111.md](research_pickle_20261111.md) | 기록 | 2026-11-11 | 현재 유효 | 피클(Pickle) 개인 AI 에이전트 조사: 공개된 것(credential-enclave · tau2-bench 포크) · 사용자 기능 · 보도된 실패 사례 · 참고 오픈소스. 계획과 명세는 `../agent_pickle_plan.md`(PL-16) |
| [research_reminder_20261113.md](research_reminder_20261113.md) | 기록 | 2026-11-13 | 현재 유효 | 리마인더 · 에이전트 기능 27가지의 제품 · 가이드라인 근거(Gmail Nudges · Viva Briefing · SaneBox · HAX · NN/g 등), 확인 수준 표시. 명세는 `../reminders.md`(PL-18) |
| [research_outlook_features_20261113.md](research_outlook_features_20261113.md) | 기록 | 2026-11-13 | 현재 유효 | 메일 화면에 들일 Outlook 메일 관리 기능 조사(공식 문서 8곳). 결론은 FE-5d(#59) · UX-D18 |
| [research_fe_benchmark_20261112.md](research_fe_benchmark_20261112.md) | 기록 | 2026-11-12 | 현재 유효 | 프론트 벤치마킹: 화면 부품 · 피그마 · 참고 구현. 결론은 UX-D17 · FE-D15–D19 · `components.md` |
| [research_outlook_20261107.md](research_outlook_20261107.md) | 기록 | 2026-11-07 | 현재 유효 | Outlook 메일 읽기 · 쓰기 화면 구성(스크린샷 2장). 결론은 메일 화면 v3.2(UX-D13–D16) |
| [research_deck_design_20261121.md](research_deck_design_20261121.md) | 기록 | 2026-11-21 | 현재 유효 | IR 발표자료 디자인 레퍼런스: Notion Mail 첫 화면 · Apple Mail 기능 소개 · Front 투자 덱 캡처 → 색 · 글자 · 여백 · 장 종류 7개. 쓰는 곳 `../ir_draft.md`(PL-19) |
| [research_ux_20261107.md](research_ux_20261107.md) | 기록 | 2026-11-07 | 현재 유효 | UX v3.1 근거: 브랜드 · 에이전트 화면 · 모핑 · 시트 · 알림. 결론은 UX-D4–D9 · `design_system.md` |
| [research_20261022.md](research_20261022.md) | 기록 | 2026-10-22 | 일부 대체됨 | 우선순위 · 처리 완료 감지 · 계정 연결 조사. 처리 완료 감지 권장안(회신 → 완료 후보)은 D36으로 대체됨(자동 완료 없음) |
| [research_dashboard_20261022.md](research_dashboard_20261022.md) | 기록 | 2026-10-22 | 대체됨 | 대시보드 레퍼런스 1차. 배치 결론은 D18 → D20으로 대체됨 |
| [research_dashboard_20261024.md](research_dashboard_20261024.md) | 기록 | 2026-10-24 | 대체됨 | 대시보드 레퍼런스 보강. 배치 결론 D19 → D20으로 대체됨 |
| [research_dashboard_v2_20261024.md](research_dashboard_v2_20261024.md) | 기록 | 2026-10-24 | 참고 | 대시보드 v2 브랜드 · 화면 패턴. wireframe 12절 · D21의 근거 |
| [review_20261024.md](review_20261024.md) | 기록 | 2026-10-24 | 참고 | 중간 리뷰 피드백. D23(답장 후 완료 확인 팝업)의 근거 |
| [drive_update_20261022.md](drive_update_20261022.md) | 기록 | 2026-10-22 | 완료 · 보관 | 드라이브 팀 문서 갱신 정리(D1). 할 일 끝남 |

- '대체됨'은 문서 전체가 아니라 그 문서의 결론이 이후 결정으로 바뀌었다는 뜻이다. 조사 사실(링크 · 제품 설명)은 여전히 참고할 수 있다.
- 기록 문서 안의 `docs/handoff.md` 같은 경로는 D30 폴더 정리 전 경로다. 당시 기록이라 고치지 않는다.
- 새 조사를 남길 때는 `research_<주제>_<YYYYMMDD>.md`로 만들고 이 표에 한 줄 추가한다.
