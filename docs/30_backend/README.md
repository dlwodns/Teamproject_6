# 30_backend · 백엔드 파트 안내

> 상태: 제안 · 작성: 홍태겸 · 결정: [파트 팀장 확정 후] · 리뷰: [미정] · 갱신: 2026-11-03
> 근거: D8 · D23 · D26 · D34~D38 · D41 · D43 · D45, 구조도 v3.1, `docs/10_planning/detail.md` 9.2절(`feature/PL`), `docs/40_ai/detail.md` 2 · 3 · 5절(`feature/AI`)
> 이 폴더 파일: `README.md`(역할 · 다른 파트와 나누는 일) · `detail.md`(상세 명세: 행동 레지스트리 · 확인 정책 · 상태 · 리마인더 · MCP 자리) · `plan.md`(작업 목록) · `decisions.md` · `troubleshooting.md`
> 코드 위치: 최상위 `backend/`(FastAPI · APScheduler · SQLite, D38). 폴더 안내는 `backend/README.md`

## 1. 백엔드가 맡는 일

백엔드는 **상태와 실행의 주인**이다. ai는 "무엇을 · 어디에"만 고르고, 판단 결과를 저장 · 검증 · 실행 · 기록하는 일은 모두 백엔드가 한다(D34 · D37).

| 기능 | 백엔드가 하는 일 | 다른 파트가 하는 일 | 근거 |
|---|---|---|---|
| 메일 가져오기 | 받은편지함 + 보낸편지함 저장(`direction`, `conversation_id`), 사전 필터, 분류 요청 등록 | — | D10 · D43 |
| 분류 요청 | 개인정보를 가린 뒤 ai `/classify`를 백그라운드로 부르고 결과를 `tasks`에 저장. ai가 꺼져도 화면은 동작 | ai: 규칙 · 엑사원 분류 | D34 |
| 업무 상태 · 되돌리기 | `pending` · `done` · `excluded` · `snoozed` 전이, 모든 전이를 `action_log`에 기록, 되돌리기 | — | D36 · 구조도 5절 |
| 행동형 에이전트 | 행동 레지스트리(T01~T14 정의 한 곳) · 대상 해석 · **확인 정책 판정** · preview/execute 실행 | ai: `/agent/plan`으로 행동 · 대상 고르기 | D37 · D44 |
| 리마인더 | APScheduler 단일 프로세스, 중복 방지 · 발송 직전 재확인 · 조용한 시간 | 프론트: 알림 센터 · 웹 푸시 화면 | D35 |
| 무응답 확인 | 보낸 메일 중 기준일(기본 3일) 넘게 회신 없는 대화 계산 | — | D43 |
| API | 대시보드 · 업무 · 메일 · 설정 · 에이전트 · 개발 모드 엔드포인트 | 프론트: 화면 | 구조도 8절 |
| MCP (P2) | 같은 레지스트리를 MCP 도구로 노출 | — | D43 · AI detail 5절 |

- 백엔드가 하지 않는 것: 엑사원 직접 호출(반드시 `ai_client/` 경유), 확인 없이 답장으로 자동 완료(D48: 팝업 또는 '오늘 하루 보지 않기'로만), 사용자가 누르지 않은 메일 발송, 외부 LLM 호출(D41), Claude · eval 사용(D26).

## 2. 파트 역할

파트원은 임동하 · 최수호 · 홍태겸이다(D45). 파트 팀장 · 작업별 담당은 `[미정]`이다(`plan.md` 3절).

| 일 | 담당 | 근거 |
|---|---|---|
| 백엔드 골격 · DB · API · 상태 · 리마인더 · 레지스트리 | 백엔드 | BE-1~BE-17 |
| ai 호출부(`ai_client/`) · 요청 · 응답 스키마 | 백엔드 + AI 공동 | BE-9 · AI-9 |
| 확인 정책 판정 규칙 | 백엔드 (ai 출력에 확인 여부를 넣지 않는다) | D37 · AI detail 3절 |
| 행동 목록(T01~T14) 내용 · 명령 해석 | AI가 정의, 백엔드가 레지스트리로 구현 | AI detail 2절 |
| CI 백엔드 단계 통과 조건 | 백엔드 (`backend/pyproject.toml` + `dev` extra에 pytest) | INF-9(`feature/INF`) |
| 인프라(배포 · 스케줄러 운영) | `[결정 필요]` 권장: 백엔드 겸임 | PL detail 9.5절 · 미결 #7 |

## 3. 먼저 읽을 것

1. `docs/00_common/work_rules.md` (브랜치 · 커밋 규칙)
2. 구조도 v3.1 `docs/00_common/architecture.md` 5 · 6 · 8 · 9 · 12절 (상태 · 에이전트 흐름 · API · 테이블 · 테스트)
3. 이 폴더 `detail.md` → `plan.md`
4. 행동 목록 원문: `docs/40_ai/detail.md` 2 · 3절 (`feature/AI`)

## 4. 실행

`[예정]` BE-1 골격이 생기면 채운다. CI와 같은 명령은 `cd backend && python -m pytest`이다(INF-6, `feature/INF`).
