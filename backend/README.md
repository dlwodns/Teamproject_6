# backend · API 서버 + SQLite

> 프레임워크: Python · FastAPI · APScheduler(1프로세스) · SQLite로 확정했다(D38). AI는 `ai/` 서비스를 HTTP로 부른다(D34).
> 기준 문서: 구조도 v3.1 `docs/00_common/architecture.md` (API 8절 · 데이터 9절 · 테스트 12절)
> 파트 문서: `docs/30_backend/README.md`(역할) · `detail.md`(행동 레지스트리 · 확인 정책 · 실행 흐름 · MCP 자리) · `plan.md`(작업 BE-1~BE-17)

| 폴더 | 내용 |
|---|---|
| `app/api/` | 라우터: dashboard · tasks · actions(preview · execute · undo) · mails(응답 대기 포함) · calendar(P1) · notifications · push · accounts · settings · contacts · templates · agent · voice(→ ai 중계) · dev(개발 모드 전용) |
| `app/core/` | 설정(.env 읽기) · DB 연결 · 토큰 암호화 · `APP_MODE` |
| `app/models/` | DB 테이블: users · accounts · contacts · mails · classify_jobs · tasks · reminders · notifications · push_subscriptions · action_log · action_previews · settings · templates |
| `app/schemas/` | 요청 · 응답 형식. ai와 주고받는 형식은 `ai/app/schemas`와 함께 고친다(AI-9 · BE-9) |
| `app/services/` | 여러 경로가 같이 쓰는 로직. `task_status.py`: 업무 상태 변경 · `action_log` 기록 · 되돌리기 · 일괄 변경 미리보기 → 실행(BE-4). REST 버튼 · 에이전트 · MCP가 같은 함수를 쓴다 |
| `app/mail/connectors/` | 메일 가져오기(받은편지함 + 보낸편지함): `dummy`(개발 · 평가) · `outlook_graph`(OAuth 권장) · `imap` |
| `app/ai_client/` | `ai/` 서비스 호출(`/classify` · `/agent/plan` · `/summarize` · `/draft` · `/memory/extract` · `/signals` · `/health`, `/stt`는 미구현. `/signals`가 없으면(404) 그 기능을 건너뛴다). 주소는 `AI_SERVICE_URL`, 제한 시간 130초. 응답 ID(문자열) → 정수 · 시각 → 시간대 없는 KST 변환은 `app/schemas/ai.py` 한 곳에서(D47). 실패는 `AIError`(timeout · unavailable · bad_response)로 알린다 |
| `app/agent/` | 행동 레지스트리(`tools/`, T01~T14 정의 한 곳) · 대상 해석 · 확인 정책 판정 · preview/execute 실행기. 웹 에이전트 · REST 버튼 · MCP가 같은 정의를 쓴다 |
| `app/privacy/` | ai에 보내기 전 개인정보 가리기 · 본문 읽기 on/off · 로그에 본문 · 토큰 남기지 않기 |
| `app/reminders/` | 리마인더 엔진(BE-12): 유형 · 묶음 표(`types.py`) · 항목 계산(`rules.py`) · 알림 정책(`policy.py`) · 1분 틱(`engine.py`) · 버튼과 T16(`actions.py`) · 브리핑(`briefings.py`) · 예전 DB 맞추기(`schema.py`) |
| `app/notify/` | 리마인더 발송 채널: 지금은 앱 내 알림 센터(`notifications` 표)만. 웹 푸시(채널 `[미정]`) · Apprise는 다음(D35) |
| `app/jobs/` | 주기 작업: 분류 작업자(`worker.py`, `CLASSIFY_WORKER=1`) · 리마인더 스케줄러(`scheduler.py`, `REMINDER_SCHEDULER=1`, APScheduler 1프로세스 1분 틱) · 리마인더 신호(`signals.py`, `REMINDER_SIGNALS=1`) |
| `app/mcp/` `[예정, P2]` | MCP 서버. 같은 레지스트리를 MCP 도구로 노출 |
| `tests/` | API 테스트. 기준은 구조도 v3.1 12절 19건 |

## 규칙
- Claude(anthropic) · OpenRouter 패키지와 키를 넣지 않는다(D26 · D41).
- 엑사원을 직접 부르지 않는다. 분류 · 명령 해석 · 요약 · 초안 · STT는 `ai_client/`로만 요청한다.
- 분류 요청은 백그라운드 작업으로 보낸다(메일 1통 약 25초). ai가 응답하지 않아도 메일 동기화와 화면은 동작해야 한다.
- 보낸 메일도 저장한다(`direction=sent`, 무응답 계산용). 분류에는 보내지 않는다.
- 업무 상태는 `pending` · `done` · `excluded` · `snoozed` 넷이다. 답장 뒤에는 완료 확인 팝업으로 묻고, '오늘 하루 보지 않기'면 바로 완료한다(D48, `source = reply_auto`). 모든 상태 변경은 `action_log`에 남긴다.
- 에이전트는 레지스트리에 등록한 행동만 실행한다. 확인이 필요한지는 이 서버의 규칙이 정한다: 조회 · 표시 · 1건 변경은 바로 실행(1건 변경은 되돌리기 제공), 2건 이상 · 설정 변경은 preview → execute, 발송은 항상 미리보기 + 확인(D37).
- 리마인더는 `(task_id, rule, slot)`(업무가 없는 항목은 `(user_id, subject_kind, subject_id, rule, slot)`) 유일 제약으로 중복을 막고, 발송 직전에 아직 미처리인지 다시 확인한다(BE-D28).
- 시간 이동 · 리마인더 강제 실행 · 더미 적재 엔드포인트는 `APP_MODE=dev`에서만 켠다.

## 실행

```bash
cd backend
uv sync --locked --extra dev                    # uv.lock 그대로 .venv에 설치(INF-3). pyproject.toml을 고치면 uv lock도 같이 커밋한다
.venv/bin/uvicorn app.main:app --port 8000      # 시작할 때 테이블을 만든다 → backend/ax.db. 셋을 한 번에: python scripts/run_dev.py
.venv/bin/python -m pytest                       # CI backend 단계와 같은 명령 (메모리 DB, 엑사원 불필요)
```

- 확인: `curl localhost:8000/health` → `{"status": "ok", "app_mode": "dev", "db": "ok"}`
- 시작할 때 설정을 검사한다(`app/core/config.py` `check_settings`, INF-4). `APP_MODE` · `MAIL_SOURCE` 값이 틀리거나 `MAIL_SOURCE=outlook_graph`인데 Graph 키 · 암호화 키가 비면 뜨지 않는다.
- 요청 ID(INF-12): 모든 응답에 `X-Request-ID`가 붙고 로그 줄에도 같은 ID가 찍힌다(`app/core/request_id.py`). ai를 부를 때(BE-9 `ai_client`) `headers=request_id_headers()`로 넘긴다. 로그에는 쿼리 · 본문 · 헤더를 남기지 않는다.
- 테이블은 시작할 때 `create_all`로 만든다. 이미 있는 테이블은 고치지 않으므로 테이블 정의를 바꾸면 로컬 `ax.db`를 지우고 다시 만든다. 마이그레이션 도구(Alembic) 도입은 `[미정]`. 예외로 BE-12가 바꾼 `reminders` · `notifications`(비어 있을 때만 다시 만듦) · `settings`(새 칸 5개)는 `create_all` 직후 자동으로 맞춘다(`app/reminders/schema.py`, BE-D33). 예전 표에 행이 있으면 멈추고 DB를 새로 만들라고 알린다.
- 시각은 `app/core/clock.py`의 `now()`(한국 시간)만 쓴다. 요청 시각은 `to_kst_naive()`로 저장 형식으로, 응답 시각은 `as_kst()`로 `+09:00`을 붙인다(D47). 개발 모드 시간 이동(BE-14)이 여기를 바꾼다.

## 리마인더 (BE-12)

명세는 `docs/10_planning/reminders.md`(PL-18), 결정은 `docs/30_backend/decisions.md` BE-D26~D33이다. 항목은 저장하지 않고 매번 DB 값으로 계산하고, `reminders` 표에는 '언제 몇 번 알렸나'만 남는다. 모든 응답 시각은 `+09:00`이 붙은 KST다.

| 환경 변수 | 하는 일 |
|---|---|
| `REMINDER_SCHEDULER=1` | 서버와 함께 APScheduler가 1분마다 엔진을 돈다(시작하자마자 한 번 → DB에서 다시 계산). 비우면 꺼짐 |
| `REMINDER_SIGNALS=1` | 분류가 끝난 받은 메일 · 저장된 보낸 메일에 ai `/signals`를 부른다(AI-24). 엑사원을 연결한 뒤 켠다. 꺼져 있거나 ai에 `/signals`가 없으면 AI 신호 유형만 안 나온다 |

| 요청 | 응답 |
|---|---|
| `GET /api/reminders?group=all` (`due` · `waiting` · `promise` · `revisit` · `prepare` · `cleanup`) | `{as_of, counts: {due, waiting, promise, revisit, prepare, cleanup, all}, muted_types: [유형], items: [ReminderItem]}`. counts는 group과 상관없이 전체 |
| `POST /api/reminders/{key}/dismiss` `{reason: hide \| not_mine \| wrong_signal \| keep \| stop_waiting}` | `{key, reason, hidden_until, action_id}`. hide는 다음 R-아침까지, not_mine은 T10 기록(action_id로 되돌리기) |
| `POST /api/reminders/{key}/apply` | `{key, action_id, task: TaskState \| null, due_at, commitment_id}`. due_changed → T16, resolved · reply_confirm → T03, their_promise · my_promise → 약속 done. 되돌리기는 `POST /api/actions/{action_id}/undo` |
| `PATCH /api/reminders/types/{type}` `{notify: bool}` | `{type, notify, muted_types}`. 목록에서는 사라지지 않는다 |
| `GET /api/notifications?unread_only=false` | `{items: [Notification], unread}` 최근 100건 |
| `PATCH /api/notifications/{id}` `{read?: true, answer?: "yes" \| "no"}` | 바뀐 Notification. answer는 reply_confirm에만(yes = T03 완료, no = 아직 남았어요) |
| `POST /api/notifications/read-all` | `{updated}` |
| `GET /api/briefings/{morning \| evening \| weekly}?date=YYYY-MM-DD` | `{kind, date, as_of, scheduled_at, title, summary, total, sections: [{id, label, count, items: [{task_id, mail_id, commitment_id, reminder_key, title, reason, due_at, action_id, actions}]}]}`. `scheduled_at`은 그 날짜의 브리핑을 만드는 시각(아침 = R-아침, 퇴근 = 근무 끝 30분 전, 주간 = 그 주 금요일 근무 끝 30분 전)이고, `as_of`가 이보다 이르면 아직 만들 시각이 아니다. date는 2000-01-01 ~ 2099-12-31(밖이면 422) |
| `POST /api/dev/reminders/run?at=ISO` | 개발 모드에서만(운영 404). 그 시각으로 모든 사용자에 엔진을 한 번 돌린다. `{at, results: [{user_id, sent: [key], skipped: [{key, reason}], notifications: [id]}]}` |

```json
ReminderItem = {"key": "due_soon:task:2", "type": "due_soon", "type_label": "기한 임박", "group": "due",
  "title": "견적 회신", "reason": "기한이 오늘 17:00이에요", "evidence": "금요일까지 회신 부탁드립니다.",
  "task_id": 2, "task_ids": [2], "mail_id": 2, "commitment_id": null, "due_at": "2026-11-11T17:00:00+09:00",
  "counterpart": {"email": "kim@cne.com", "name": "김민준", "position": "팀장", "label": "김민준 팀장님"},
  "created_at": "2026-11-10T17:00:00+09:00", "state": "active", "notify_count": 1,
  "last_notified_at": "2026-11-11T14:00:00+09:00", "notify": true,
  "actions": [{"id": "draft", "label": "초안 보기", "action": "T07", "primary": true, "params": {"mail_id": 2, "tone": "polite"}},
              {"id": "snooze", "label": "미루기", "action": "T05", "primary": false, "params": {"until": null}},
              {"id": "done", "label": "완료", "action": "T03", "primary": false, "params": {}}]}
Notification = {"id": 7, "kind": "reminder | reply_confirm | digest", "type": "due_soon", "group": "due",
  "reminder_key": "due_soon:task:2", "reminder_keys": ["due_soon:task:2"], "title": "견적 회신",
  "body": "기한 임박 · 기한이 오늘 17:00이에요", "task_ids": [2], "rule": "R-기한",
  "scheduled_at": "…+09:00", "read_at": null, "answered_at": null, "created_at": "…+09:00"}
```

- 항목 키: `유형:대상종류:id` — 대상종류는 `task` · `sent_mail` · `commitment` · `day`(YYYYMMDD). 정렬은 기한 이른 순, 기한 없으면 생긴 순, `state = quiet`(3번 알린 뒤, 미룬 일은 예외)는 맨 아래. `last_notified_at`은 그 항목을 마지막으로 알린 시각(묶음 알림 포함, 알린 적 없으면 null).
- `actions[].action`: 행동 레지스트리 T코드(T03 · T05 · T07 · T13) · `open_mail` · `apply` · `dismiss`(params.reason). T05의 `until: null`은 화면이 시각을 고르게 한다.
- digest 알림: `type`이 `digest`(같은 분 3건 이상, 제목 "챙길 것 N건") · `away_return`(부재 중 복귀) · `evening` · `weekly`(회고). 들어간 항목은 `reminder_keys`.
- 제안 카드 `GET /api/suggestions`는 이 목록의 앞쪽 N건을 예전 카드 형식으로 준다(BE-D31).
