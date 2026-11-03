# 백엔드 상세 명세 · 행동 레지스트리 · 확인 정책 · 상태 · 리마인더 · MCP 자리 (2026-11-03)

> 상태: 초안 · 작성: 홍태겸 · 결정: [파트 팀장 확정 후] · 리뷰: [미정] · 작업 번호: BE-10
> 작성 방식: 작성자의 아이디어를 Claude로 템플릿화해 초안을 잡고 구체화했다.
> 근거: 구조도 v3.1 5~9 · 12절, `docs/40_ai/detail.md` 1~5절(`feature/AI`), `docs/10_planning/detail.md` 4 · 9.2 · 12절(`feature/PL`), `docs/00_common/decisions.md` D34~D38 · D41 · D43
> 표기: `[확정]` 팀 결정 · `[제안]` 팀 확인 필요 · `[결정 필요]` 정하지 않고 TODO로 남김 · `[미확인]` 출처 미검증
> 짝 문서: AI 상세 명세 `docs/40_ai/detail.md` (행동 목록 · 명령 해석 · MCP 도구 · 평가). 행동의 **내용**은 AI 명세가, **구현 구조**는 이 문서가 기준이다.

## 1. 설계 원칙

1. 행동 정의는 **한 곳**(`backend/app/agent/tools/registry.py`)에만 둔다. 웹 에이전트 · REST 버튼 · MCP 서버가 같은 정의를 읽는다 `[확정]` (D37 · D43, AI detail 1절 3).
2. 실행은 백엔드 코드가 한다. ai는 행동 이름 · 대상 · 인자만 고른다 `[확정]` (D34).
3. 확인이 필요한지는 백엔드 규칙이 정한다. ai 출력에 확인 여부를 넣지 않는다 `[확정]` (D37, AI detail 3절).
4. 모든 상태 변경은 `action_log`에 남기고, 되돌리기는 `action_log.before_json`으로 한다 `[확정]` (구조도 5절).
5. 추적 종료는 사용자의 완료 체크 · 제외뿐이다. 회신 · 발송으로 자동 완료하지 않는다 `[확정]` (D36).
6. MCP 서버는 P2다. 지금은 레지스트리에 MCP 노출 이름 칸만 둔다 → MCP를 붙일 때 레지스트리 코드를 고치지 않는다 `[확정 방향]` (AI detail 5.2절).

## 2. 행동 레지스트리

### 2.1 정의 형식 `[제안]`

AI detail 2.1절 예시를 그대로 따르고, 백엔드가 실행에 쓰는 칸(`handler`)만 더한다.

```python
# backend/app/agent/tools/registry.py
@dataclass(frozen=True)
class ActionDef:
    id: str                 # "T05"
    name: str               # "나중에_처리" (ai /agent/plan 응답의 action 값과 맞춘다)
    kind: str               # query | display | state_change | settings | send
    target_schema: type     # pydantic 모델: mail_ids · sender · category · date_range ...
    params_schema: type     # pydantic 모델: until · due_within ...
    undoable: bool
    side_effects: tuple     # ("reminder.schedule",) 등
    mcp_tool: str | None    # MCP 노출 이름 (AI detail 5.3절). None이면 미노출
    priority: str           # P0 | P1 | P2
    handler: Callable       # 실제 실행 함수 (backend/app/agent/tools/<행동>.py)

REGISTRY: dict[str, ActionDef] = {d.id: d for d in [...]}
```

- 레지스트리는 **목록만** 가진다. 실행 로직은 행동별 파일로 나눈다(`tools/today_summary.py` 등).
- ai에 보내는 목록(`POST /agent/plan`의 `actions`)은 레지스트리에서 만든다: `{id, name, args_schema}`(구조도 8절). 손으로 따로 적지 않는다.
- P1 · P2 행동은 정의만 넣고 `handler`가 없으면 "아직 지원하지 않는 요청"으로 응답한다 `[제안]`.

### 2.2 P0 행동 7개 — 백엔드가 하는 일

목록 · 예시 명령 · 유형은 AI detail 2절이 기준이다. 아래는 실행 쪽만 적는다.

| ID | 행동 | kind | 읽는 곳 → 바꾸는 곳 | 부수 효과 | MCP 이름 |
|---|---|---|---|---|---|
| T01 | 오늘_요약 | query | 미처리 · 오늘 기한 `tasks` → ai `/summarize`(가린 입력) | — | `get_today_summary` |
| T02 | 미처리_조회 | query | `tasks` 필터(sender · category · date_range · due_within) | — | `list_pending` |
| T03 | 일괄_완료 | state_change | `tasks.status` → `done`, `done_at` | 해당 업무 리마인더 취소 | `preview_action` |
| T04 | 되돌리기 | state_change | 대상 `action_log`의 `before_json` 복원, `undone_at` | 리마인더 재예약 | `undo_action` |
| T05 | 나중에_처리 | state_change | `tasks.status` → `snoozed`, `snoozed_until` | R-나중에 리마인더 1건 예약 | `preview_action` |
| T06 | 무응답_확인 | query | `mails`(`direction=sent`, 같은 `conversation_id`에 회신 없음, `min_days` 이상) | — (조치 없음) | `list_awaiting_reply` |
| T07 | 회신_초안 | display | 메일 1건 → ai `/draft`(가린 입력). 보내지 않는다 | — | `draft_reply` |

- "1건 완료"는 T03에 대상이 1건 걸린 경우다(AI detail 2절).
- 상태 변경 행동(T03 · T05)은 MCP에서 바로 실행하지 않고 `preview_action` → `execute_action` 2단계로만 노출한다(5절).

## 3. 확인 정책 판정 `[확정]` (D37) · 구현 `[제안]`

### 3.1 규칙

| kind | 대상 | 확인 | 되돌리기 |
|---|---|---|---|
| query · display | — | 없음 | 해당 없음 |
| state_change | 확정 대상 1건 | 없음, 실행 후 되돌리기 알림 | 가능 |
| state_change | 2건 이상 **또는** 대상 후보 여러 개 | **확인창** (preview → execute) | 가능 |
| settings | — | **확인창** | 가능 |
| send | — | **항상 미리보기 + 확인** | **불가** (확인창에 명시) |

### 3.2 함수

```python
# backend/app/agent/policy.py
def needs_confirm(action: ActionDef, resolved_ids: list[int], ambiguous: bool) -> bool:
    if action.kind in ("query", "display"):
        return False
    if action.kind in ("settings", "send"):
        return True
    return len(resolved_ids) >= 2 or ambiguous   # state_change
```

- 입력은 행동 `kind`와 **대상 해석 결과**(건수 · 후보가 여럿인지)뿐이다. ai 응답의 다른 값은 보지 않는다.
- 대상 0건이면 실행하지 않고 "해당하는 미처리 업무가 없습니다"를 돌려준다 `[제안]` (AI detail 7.2절: "공지 메일 다 처리했어"는 D40과 만나 0건일 수 있다).
- T04 되돌리기는 직전 행동 1개를 되돌리는 것이므로 바로 실행한다(되돌리기 자체도 `action_log`에 남아 다시 되돌릴 수 있다) `[제안]`.
- 단위 테스트로 표 3.1의 모든 칸을 고정한다(7절).

## 4. 실행 흐름 (웹 에이전트)

구조도 6절 시퀀스를 백엔드 함수 단위로 나눈다.

| 순서 | 하는 일 | 위치 | 실패 시 |
|---|---|---|---|
| 1 | `POST /api/agent/command {text, selected_mail_ids}` 받기 | `api/agent.py` | — |
| 2 | 레지스트리 목록 + 맥락(`now` · 선택 메일 id)으로 ai `/agent/plan` 호출 | `ai_client/` | ai 응답 없음 → "지금은 명령을 처리할 수 없습니다", 500 없음 |
| 3 | **허용 목록 검증**: `action`이 레지스트리에 있고 `target` · `params`가 스키마에 맞는가 | `agent/validate.py` | "지원하지 않는 요청" (구조도 12절 #16) |
| 4 | **대상 해석**: 발신자명 → `contacts` 매칭, 지시어 → `selected_mail_ids`, 조건 → `tasks` 조회 | `agent/resolve.py` | 0건 → 3.2절 |
| 5 | **확인 판정** `needs_confirm` | `agent/policy.py` | — |
| 6a | 확인 불필요 → `handler` 실행 → `action_log` 기록 → 결과 카드(+ 되돌리기 `action_id`) | `agent/executor.py` | — |
| 6b | 확인 필요 → `action_previews` 저장 → `{preview_id, 대상 목록, 바뀔 상태}` 반환 | `agent/executor.py` | — |
| 7 | `POST /api/actions/execute {preview_id}` → 미사용 · 미만료 확인 → 실행 · 기록(`confirmed=true`) · `used_at` | `api/actions.py` | 사용됨 · 만료 → 409 `[제안]` |

- REST 버튼(`PATCH /tasks/{id}` · `POST /tasks/bulk/preview`)도 5~7을 같은 함수로 탄다. 경로만 다르고 판정 · 기록은 같다.
- `preview_id` 만료 시간 `[결정 필요]` (권장: 5분).
- `action_log.source`: `ui` · `agent_rule` · `agent_model`(ai 응답의 `source`로 정함) · `mcp`.

## 5. MCP 자리 (P2)

지금 할 일은 2.1절의 `mcp_tool` 칸을 채워 두는 것뿐이다. MCP 서버를 만들 때는 아래만 더한다.

```
backend/app/mcp/   [예정, P2]
  server.py   ← REGISTRY에서 mcp_tool이 있는 행동만 골라 MCP tool로 등록
              ← 호출은 4절 3~7을 그대로 탄다 (ai 명령 해석은 거치지 않음)
```

- 상태 변경은 `preview_action` → `execute_action` 2단계만 연다. 바로 실행 도구는 만들지 않는다.
- 응답에 메일 본문을 넣지 않는다(제목 · 발신자 · 기한 · 분류 · 근거 문장만). 발송 도구는 노출하지 않는다 `[제안]`.
- 접근 토큰 `MCP_ACCESS_TOKEN`(`.env` 자리표시자), `action_log.source = mcp`.
- 구현 방식(같은 FastAPI 프로세스 · 별도 엔드포인트)은 P2 착수 때 정한다 `[결정 필요]`. 일정이 밀리면 뺀다(PL detail 15절 R2).

## 6. 업무 상태 · 리마인더

### 6.1 상태 전이 `[확정]` (D36 · 구조도 5절)

| 현재 | 행동 | 다음 | 기록 |
|---|---|---|---|
| `pending` | 완료 (☐ · T03 · 답장 후 '완료로 처리') | `done` (`done_at`) | `action_log` |
| `pending` | 제외 (T10) | `excluded` | `action_log` |
| `pending` | 나중에 (T05) | `snoozed` (`snoozed_until` 필수) | `action_log` + 리마인더 1건 |
| `snoozed` | `snoozed_until` 도래 | `pending` | 스케줄러 (리마인더 발송) |
| `done` · `excluded` · `snoozed` | 되돌리기 (T04) | `before_json`의 상태 | `action_log.undone_at` |

- 허용되지 않은 상태 값은 422, 상태 변경 없음(구조도 12절 #18).
- 재동기화 · 재분류는 사용자가 바꾼 상태를 덮어쓰지 않는다(구조도 12절 #9).

### 6.2 리마인더 `[결정: 문규남 11-02 · 팀 리뷰 대기]` (PL detail 4.2절)

| 규칙 | 조건 | 기본값 |
|---|---|---|
| R-아침 | 미처리 전체 | 매일 08:30 (사용자 설정) |
| R-기한 | 기한 있는 미처리 | 기한 3시간 전 |
| R-나중에 | `snoozed_until` 도래 | 해당 시각 |

- APScheduler **단일 프로세스**, 시작할 때 DB에서 예약 복구.
- 중복 방지: `reminders` 유일 `(task_id, rule, slot)`. 발송 직전 상태 재조회 → 완료 · 제외면 `skipped_reason` 남기고 건너뜀.
- 시간대는 `ZoneInfo("Asia/Seoul")`로 적는다(CI `TZ=Asia/Seoul`과 맞춤, INF-6).
- 시간 이동 · 강제 실행은 `APP_MODE=dev`에서만 켠다.

## 7. 완료 기준 · 테스트

| 묶음 | 테스트 | 근거 |
|---|---|---|
| 골격 | `GET /health` 200, CI backend 단계가 건너뛰지 않고 통과 | BE-1 · INF-9 |
| 레지스트리 | 모든 행동 id · name 유일, P0 7개에 `handler` 있음, `mcp_tool` 이름이 AI detail 5.3절 목록 안에 있음 | 이 문서 2절 |
| 확인 정책 | 3.1절 표의 모든 칸 (query · display · 1건 · 2건 · 후보 여럿 · settings · send) | 3절 |
| 명령 → 판정 | AI detail 7.2절 검증 입력 중 확인 · 실행 결과 항목: "이거 완료"(1건) → 확인 없이 실행, "이번 주 공지 메일 다 처리했어" → 확인창, "방금 거 취소해" → 직전 `action_log` 복원, "배고프다" → 지원하지 않는 요청 | AI detail 7.2절 |
| 실행 흐름 | 구조도 12절 #7 · #8 · #15 · #16 · #18 | 4 · 6절 |
| 리마인더 | 구조도 12절 #10 · #12 · #13 | 6.2절 |
| 외부 호출 | 서비스 경로 전체에서 외부 LLM 호출 0건 | 구조도 12절 #19 · D41 |

- 엑사원을 부르는 테스트는 CI에 넣지 않는다. `ai_client`는 가짜 응답으로 바꿔 테스트한다(INF-9).
- 명령 테스트 세트(AI detail 7.3절)의 `expected.confirm`은 백엔드 `needs_confirm` 결과와 같아야 한다. 판정 규칙을 바꾸면 테스트 세트도 함께 고친다(데이터 · 평가 파트와 공유).

## 8. 백엔드 관련 미결 사항

| # | 항목 | 권장안 | 바뀌는 곳 |
|---|---|---|---|
| 1 | TODO `preview_id` 만료 시간 | 5분 | 4절 · `action_previews` |
| 2 | TODO 대상 0건일 때 응답 | 실행 없이 안내 문구 (AI detail 7.2절 제안과 같음) | 3.2절 |
| 3 | TODO T04 되돌리기 확인 여부 | 바로 실행 | 3.2절 |
| 4 | TODO MCP 서버 위치 (같은 프로세스 · 별도) | P2 착수 때 결정 | 5절 |
| 5 | TODO 백엔드 파트 팀장 · 작업별 담당 | — | `plan.md` 3 · 4절 · D45 |
| 6 | TODO 인프라 담당 | 백엔드 겸임 | PL detail 미결 #7 |
