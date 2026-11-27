# 백엔드 상세 명세 · 행동 레지스트리 · 확인 정책 · 상태 · 리마인더 · MCP 자리 (2026-11-03)

> 상태: 초안 · 작성: 홍태겸 · 결정: [파트 팀장 확정 후] · 리뷰: [미정] · 작업 번호: BE-10 · 갱신: 2026-11-27 (지금 코드와 어긋난 곳: 실행 위치 · 답장 후 완료 응답 경로 · MCP 서버 아직 · 시연 도구 접근 · 미결 표 상태 / 11-07 #6 리뷰 반영: params 키 · D47 · D48 · 무응답 범위)
> 작성 방식: 작성자의 아이디어를 Claude로 템플릿화해 초안을 잡고 구체화했다.
> 근거: 구조도 v3.1 5~9 · 12절, `docs/40_ai/detail.md` 1~5절, `docs/10_planning/detail.md` 4 · 5 · 9.2 · 12절, `docs/00_common/decisions.md` D34~D38 · D41 · D43 · D47 · D48
> 표기: `[확정]` 팀 결정 · `[제안]` 팀 확인 필요 · `[결정 필요]` 정하지 않고 TODO로 남김 · `[미확인]` 출처 미검증
> 짝 문서: AI 상세 명세 `docs/40_ai/detail.md` (행동 목록 · 명령 해석 · MCP 도구 · 평가). 행동의 **내용**은 AI 명세가, **구현 구조**는 이 문서가 기준이다.

## 1. 설계 원칙

1. 행동 정의는 **한 곳**(`backend/app/agent/tools/registry.py`)에만 둔다. 웹 에이전트 · REST 버튼 · MCP 서버가 같은 정의를 읽는다 `[확정]` (D37 · D43, AI detail 1절 3).
2. 실행은 백엔드 코드가 한다. ai는 행동 이름 · 대상 · 인자만 고른다 `[확정]` (D34).
3. 확인이 필요한지는 백엔드 규칙이 정한다. ai 출력에 확인 여부를 넣지 않는다 `[확정]` (D37, AI detail 3절).
4. 모든 상태 변경은 `action_log`에 남기고, 되돌리기는 `action_log.before_json`으로 한다 `[확정]` (구조도 5절).
5. 추적 종료는 사용자의 완료 체크 · 제외, 그리고 답장 후 완료 확인('예' 또는 '오늘 하루 보지 않기')이다 `[확정]` (D48, D36 대체). 상세는 6.1절.
6. MCP 서버는 P2다. 지금은 레지스트리에 MCP 노출 이름 칸만 둔다 → MCP를 붙일 때 레지스트리 코드를 고치지 않는다 `[확정 방향]` (AI detail 5.2절). 11-27: 레지스트리의 `mcp_tool` 칸은 채웠고, MCP 서버 구축은 아직이다(BE-17).

## 2. 행동 레지스트리

### 2.1 정의 형식 `[제안]`

AI detail 2.1절 예시를 그대로 따르고, 백엔드가 실행에 쓰는 칸(`handler`)만 더한다.

```python
# backend/app/agent/tools/registry.py
@dataclass(frozen=True)
class ActionDef:
    id: str                 # "T05" (ai /agent/plan 응답의 action 값과 맞춘다. 레지스트리 조회 키)
    name: str               # "나중에_처리" (ai 응답 action_name, 화면 표시용)
    description: str        # ai 명령 해석에 함께 보내는 한 줄 설명
    kind: str               # query | display | state_change | settings | send
    target_schema: type     # pydantic 모델: mail_ids · sender · category · date_range · keyword · awaiting_reply
    params_schema: type     # pydantic 모델: 행동별 키(AI detail 2.1절). 예: T05 until · T06 min_days · T09 rule · time · hours
    undoable: bool
    side_effects: tuple     # ("reminder.schedule",) 등
    mcp_tool: str | None    # MCP 노출 이름 (AI detail 5.3절). None이면 미노출
    priority: str           # P0 | P1 | P2
    handler: Callable       # 실제 실행 함수 (backend/app/agent/tools/<행동>.py)

REGISTRY: dict[str, ActionDef] = {d.id: d for d in [...]}
```

- 레지스트리는 **목록만** 가진다. 실행 로직은 행동별 파일로 나눈다(`tools/today_summary.py` 등).
- ai에 보내는 목록(`POST /agent/plan`의 `actions`)은 레지스트리에서 만든다: `{id, name, description}`. 손으로 따로 적지 않는다.
  - `args_schema`는 보내지 않는다. 구조도 8절이 ai 구현(`ai/app/schemas/agent.py` `ActionSpec`) 기준으로 갱신됐다 `[확정]` (#8, D47).
  - 행동 ID(T01~T20, 11-27 레지스트리 기준)와 params 키는 backend · ai 공동 계약이다. 레지스트리의 ID · params 키는 AI detail 2.1절 표와 같게 두고, 바꿀 때는 `ai/app/agent/rules_v1.py`(`extract_params`)와 같은 PR 묶음에서 함께 고친다 `[확정]` (D47 결정 3).
  - 11-03 대비 바뀐 params 키: T02 `due_within` 삭제(기한 범위는 `target.date_range`), T09 `interval` 삭제 · `hours` 추가, T14 `template_id` → `template_name`.
  - params 값을 못 읽으면 키를 빼지 않고 `null`로 온다(예: T05에서 시각을 못 읽으면 `until: null`). 레지스트리 스키마는 키를 필수로 두고 값은 `null`을 허용한다. 실행 전 필수 값이 `null`이면 사용자에게 되묻는다 `[제안]`.
- P1 · P2 행동은 정의만 넣고 `handler`가 없으면 "아직 지원하지 않는 요청"으로 응답한다 `[제안]`.

### 2.2 P0 행동 7개 — 백엔드가 하는 일

목록 · 예시 명령 · 유형은 AI detail 2절이 기준이다. 아래는 실행 쪽만 적는다.

| ID | 행동 | kind | 읽는 곳 → 바꾸는 곳 | 부수 효과 | MCP 이름 |
|---|---|---|---|---|---|
| T01 | 오늘_요약 | query | 미처리 · 오늘 기한 `tasks` → ai `/summarize`(가린 입력) | — | `get_today_summary` |
| T02 | 미처리_조회 | query | `tasks` 필터(target: sender · category · date_range · keyword. 기한 범위는 `date_range`) | — | `list_pending` |
| T03 | 일괄_완료 | state_change | `tasks.status` → `done`, `done_at` | 해당 업무 리마인더 취소 | `preview_action` |
| T04 | 되돌리기 | state_change | 대상 `action_log`의 `before_json` 복원, `undone_at` | 리마인더 재예약 | `undo_action` |
| T05 | 나중에_처리 | state_change | `tasks.status` → `snoozed`, `snoozed_until` | R-나중에 리마인더 1건 예약 | `preview_action` |
| T06 | 무응답_확인 | query | `mails`(`direction=sent` 중 **요청한 메일만**, 같은 `conversation_id`에 상대 회신 없음, `min_days` 이상). 경계 규칙(자동회신 · 재요청 · 여러 수신자 · 72시간)은 PL detail 5절 | — (조치 없음) | `list_awaiting_reply` |
| T07 | 회신_초안 | display | 메일 1건 → ai `/draft`(가린 입력). 초안은 표시만 한다. 발송은 사용자가 보내기를 누를 때 `POST /mails/{id}/reply`로 따로 한다(D48, `Mail.Send` 권한 없으면 숨김) | — | `draft_reply` |

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
| 1 | `POST /api/agent/command {text, selected_mail_ids, last_result_ids, task_ids, reminder_key}` 받기(task_ids = 캐치봇에서 고른 리마인더의 업무, BE-18) | `api/agent.py` | — |
| 2 | 레지스트리 목록 + 맥락(`now` · 선택 메일 id)으로 ai `/agent/plan` 호출 | `ai_client/` | ai 응답 없음 → "지금은 명령을 처리할 수 없습니다", 500 없음 |
| 3 | **허용 목록 검증**: `action`(행동 ID)이 레지스트리에 있고 `target` · `params`가 스키마에 맞는가 | `agent/executor.py` | `action: null` · `reason: unsupported` → "지원하지 않는 요청" (구조도 12절 #16), `reason: ambiguous` → 사용자에게 되묻기 |
| 4 | **대상 해석**: 고른 리마인더(`task_ids`)가 있고 말에 보낸 사람 · 분류 · 낱말이 없으면 고른 업무만 대상(기간 · 메일 조건은 보지 않음. 단 조회는 기간을 말하면 그 기간으로 찾음, #243 리뷰), 대면 고른 업무는 쓰지 않는다 · 발신자명 → `contacts` 매칭, 지시어 → `selected_mail_ids`, 조건 → `tasks` 조회 | `agent/resolve.py` | 0건 → 3.2절 |
| 5 | **확인 판정** `needs_confirm` | `agent/policy.py` | — |
| 6a | 확인 불필요 → `handler` 실행 → `action_log` 기록 → 결과 카드(+ 되돌리기 `action_id`) | `agent/executor.py` | — |
| 6b | 확인 필요 → `action_previews` 저장 → `{preview_id, 대상 목록, 바뀔 상태}` 반환 | `agent/executor.py` | — |
| 7 | `POST /api/actions/execute {preview_id}` → 미사용 · 미만료 확인 → 실행 · 기록(`confirmed=true`) · `used_at` | `api/actions.py` | 사용됨 · 만료 → 409 `[제안]` |

- REST 버튼(`PATCH /tasks/{id}` · `POST /tasks/bulk/preview`)도 5~7을 같은 함수로 탄다. 경로만 다르고 판정 · 기록은 같다.
- `preview_id` 만료 시간 `[결정 필요]` (권장: 5분).
- `action_log.source`: `ui` · `agent_rule` · `agent_model`(ai 응답의 `source`로 정함) · `mcp` · `reply_auto`(답장 후 바로 완료, D48).
- ai와 주고받는 시각 · ID는 `ai_client/` 한 곳에서 맞춘다 `[확정]` (D47): ai 응답의 시간대 없는 시각은 KST로 보고, 문자열 ID는 정수로 바꾼다. backend → frontend 응답 시각에는 항상 `+09:00`을 붙인다.

## 5. MCP 자리 (P2)

지금 할 일은 2.1절의 `mcp_tool` 칸을 채워 두는 것뿐이다. MCP 서버를 만들 때는 아래만 더한다.

```
backend/app/mcp/   [예정, P2 — 11-27 아직 없음(BE-17), 레지스트리는 준비됨]
  server.py   ← REGISTRY에서 mcp_tool이 있는 행동만 골라 MCP tool로 등록
              ← 호출은 4절 3~7을 그대로 탄다 (ai 명령 해석은 거치지 않음)
```

- 상태 변경은 `preview_action` → `execute_action` 2단계만 연다. 바로 실행 도구는 만들지 않는다.
- 응답에 메일 본문을 넣지 않는다(제목 · 발신자 · 기한 · 분류 · 근거 문장만). 발송 도구는 노출하지 않는다 `[제안]`.
- 접근 토큰 `MCP_ACCESS_TOKEN`(`.env` 자리표시자), `action_log.source = mcp`.
- 구현 방식(같은 FastAPI 프로세스 · 별도 엔드포인트)은 P2 착수 때 정한다 `[결정 필요]`. 일정이 밀리면 뺀다(PL detail 15절 R2).

## 6. 업무 상태 · 리마인더

### 6.1 상태 전이 `[확정]` (D48 · 구조도 5절)

| 현재 | 행동 | 다음 | 기록 |
|---|---|---|---|
| `pending` | 완료 (☐ · T03 · 답장 후 팝업 '예') | `done` (`done_at`) | `action_log` |
| `pending` | 답장 후 '오늘 하루 보지 않기' 기간에 답장 | `done` (`done_at`) | `action_log.source = reply_auto` |
| `pending` | 제외 (T10) | `excluded` | `action_log` |
| `pending` | 나중에 (T05) | `snoozed` (`snoozed_until` 필수) | `action_log` + 리마인더 1건 |
| `snoozed` | `snoozed_until` 도래 | `pending` | 스케줄러 (리마인더 발송) |
| `done` · `excluded` · `snoozed` | 되돌리기 (T04) | `before_json`의 상태 | `action_log.undone_at` |

- 허용되지 않은 상태 값은 422, 상태 변경 없음(구조도 12절 #18).
- 재동기화 · 재분류는 사용자가 바꾼 상태를 덮어쓰지 않는다(구조도 12절 #9).
- 답장 후 완료 (D48, 상세는 PL detail 4.4절 · 구조도 5 · 8 · 12절, 백엔드 구현은 BE-5에서 따로 정리한다):
  - 경로: (가) 서비스 안 발송(`POST /mails/{id}/reply`) 직후 팝업, (나) 보낸편지함 동기화로 Outlook 답장 감지 → 알림 센터 "완료할까요?"(`notifications.kind = reply_confirm`). (가)로 물은 업무는 (나)에서 다시 묻지 않는다.
  - 응답: `POST /tasks/reply-confirm {task_ids, answer: yes | no, skip_today?}`. '아니오' · 닫기는 미처리 유지. → 구현(BE-5, 11-20): 따로 경로를 만들지 않고 알림 답 `PATCH /api/notifications/{id}` `{answer: yes | no}`로 한다(yes = T03 완료).
  - '오늘 하루 보지 않기': `settings.reply_confirm_skip_until`(다음 R-아침 시각)까지 묻지 않고 바로 완료, `source = reply_auto`. 무응답 재촉(`nudge`) 발송은 대상이 아니다.
  - BE-1 테이블(`action_log.source` 제약 · `settings` · `notifications`)에 이 값들이 아직 없다 → 별도 코드 PR로 보완한다. → 보완됨: `action_log.source`에 `reply_auto`(`app/models/action.py`), 설정 `reply_confirm_skip_until`(`app/models/user.py`). 구현: 값은 저장 · 응답까지만 있고, 그 기간 답장을 바로 완료하는 경로는 없다 — 지금은 '오늘 하루 보지 않기'를 골라도 답장마다 `reply_confirm` 알림으로 묻는다(11-27 코드 확인, `reply_auto`로 쓰는 곳 없음).

### 6.2 리마인더 `[결정: 문규남 11-02 · 팀 리뷰 대기]` (PL detail 4.2절)

| 규칙 | 조건 | 기본값 |
|---|---|---|
| R-아침 | 미처리 전체 + 지난 R-아침 이후 `reply_auto`로 바로 완료된 업무 목록(되돌리기, D48 안전장치) | 매일 08:30 (사용자 설정) |
| R-기한 | 기한 있는 미처리 | 기한 3시간 전 |
| R-나중에 | `snoozed_until` 도래 | 해당 시각 |

- APScheduler **단일 프로세스**, 시작할 때 DB에서 예약 복구.
- 중복 방지: `reminders` 유일 `(task_id, rule, slot)`. 발송 직전 상태 재조회 → 완료 · 제외면 `skipped_reason` 남기고 건너뜀.
- 시간대는 `ZoneInfo("Asia/Seoul")`로 적는다(CI `TZ=Asia/Seoul`과 맞춤, INF-6).
- 시간 이동 · 강제 실행 라우터는 `APP_MODE`와 관계없이 `DEMO_TOOLS=true`일 때만 등록한다(`APP_MODE=dev`여도 `DEMO_TOOLS`가 false면 등록하지 않는다). 라우터는 BE-14(#93)로 구현됐다. 공개 배포(Railway)는 기본 인증을 뺐으므로(#310) `DEMO_TOOLS`를 켜지 않는다(`infra/railway_setup.md`).
- 시각은 `clock.now()` = 실제 현재 KST + offset이다. 시연 시작 시각은 `CLOCK_START`, 시간 이동은 `clock.set_offset()`(교체, 단일 worker 전제)으로 바꾼다(BE-D23).

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
| 1 | TODO `preview_id` 만료 시간 | 5분 | 4절 · `action_previews`. 11-27: 코드는 권장안 5분(`services/task_status.py` `PREVIEW_TTL`, 주석 `[제안]`) |
| 2 | TODO 대상 0건일 때 응답 | 실행 없이 안내 문구 (AI detail 7.2절 제안과 같음) | 3.2절. 11-27: 권장안대로 구현("해당하는 … 업무가 없습니다", `agent/executor.py`) |
| 3 | TODO T04 되돌리기 확인 여부 | 바로 실행 | 3.2절. 11-27: 권장안대로 바로 실행, 직전 기록이 되돌리기면 되묻는다(`executor._undo`, #31 리뷰) |
| 4 | MCP 서버 위치 (같은 프로세스 · 별도) | P2 착수 때 결정 | 5절. 11-27: MCP 서버를 아직 만들지 않아 정하지 않음(BE-17) |
| 5 | 백엔드 파트 팀장 · 작업별 담당 | 임동하(BE-D23 기록) | `plan.md` 3 · 4절 · D45 |
| 6 | 인프라 담당 → 문규남(11-07 확정, PL detail 9.5 · 미결 #7) | 문규남 | PL detail 미결 #7 |
| 7 | D48 백엔드 상세: (나) 감지 방법 · 중복 방지 · `reply_auto` 되돌리기 | BE-5에서 정리 | 6.1절 · 구조도 8 · 12절. 11-20 BE-5 완료: (나)는 Outlook 보낸편지함 동기화 → 리마인더 `reply_confirm`(`reminders/rules.py`) |
| 8 | TODO 보낸 메일 '요청' 판정 방법 (규칙 / 엑사원) | AI와 함께 정함 (AI-17 P2) | 2.2절 T06 · PL detail 5절. 11-27: 지금은 규칙 `[제안]`(공지 · 기타 · RE: · FW: 등 제외, `reminders/rules.py` `is_request_sent`) |
| 9 | TODO params 필수 값이 `null`일 때 되묻기 문구 | 행동별로 정함 | 2.1절 |
