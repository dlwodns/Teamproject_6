# backend

CNE의 API 서버다. 메일 연동(더미 · Outlook) · 업무 상태 · 행동 실행기(캐치봇) · 리마인더 · 분류 작업자를 Python · FastAPI · SQLite 한 프로세스로 돌린다(D38). AI는 [ai 서비스](../ai/README.md)를 HTTP로 부른다(D34).

← [루트 README](../README.md) · 기준 문서: [구조도 v3.1](../docs/00_common/architecture.md)(API 8절 · 데이터 9절 · 테스트 12절) · [BE 명세](../docs/30_backend/detail.md) · [BE 결정](../docs/30_backend/decisions.md) · [리마인더 명세](../docs/10_planning/reminders.md)

## 요구 사항

| 도구 | 버전 |
|---|---|
| Python | 3.12 (루트 `.python-version`) |
| uv | 파이썬 패키지 설치 · 실행. `uv.lock` 그대로 설치한다(INF-3) |

엑사원 · ai 서비스 없이도 서버 · 테스트는 돈다. ai가 응답하지 않아도 메일 동기화와 화면은 동작해야 한다.

## 실행

```bash
cd backend
uv sync --locked --extra dev                  # pyproject.toml을 고치면 uv lock도 같이 커밋한다
.venv/bin/uvicorn app.main:app --port 8000    # 시작할 때 테이블을 만든다 → backend/ax.db
curl localhost:8000/health                    # {"status": "ok", "app_mode": "dev", "db": "ok"}
```

- ai · frontend까지 한 번에: 루트에서 `python scripts/run_dev.py`.
- 시작할 때 설정을 검사한다(`app/core/config.py` `check_settings`, INF-4). `APP_MODE` · `AUTH_MODE` · `MAIL_SOURCE` 값이 틀리거나, `MAIL_SOURCE=outlook_graph`인데 Graph 키 · 암호화 키가 비면 뜨지 않는다.
- 테이블은 시작할 때 `create_all`로 만든다. 이미 있는 테이블은 고치지 않으므로, 테이블 정의를 바꾸면 로컬 `ax.db`를 지우고 다시 만든다(Alembic 도입은 `[미정]`). 예외로 리마인더가 바꾼 표는 `app/reminders/schema.py`가 맞춘다(BE-D33).

### 시연 데이터

더미 메일의 정답 라벨로 메일 · 업무 · 연락처를 바로 채운다(ai를 거치지 않는다). 시연 전용 파일 `demo*.db`에만 쓴다.

```bash
.venv/bin/python -m app.dev.seed load --db demo.db --this-week   # 더미 메일함을 이번 주로 옮겨 지금까지 온 것만
DATABASE_URL=sqlite:///demo.db DUMMY_MAIL_SOURCE=<출력된 경로> .venv/bin/uvicorn app.main:app --port 8000
```

- `--this-week`은 날짜를 7일 단위로 옮겨 본문의 '금요일까지' 같은 요일이 맞는다. 본문 날짜도 옮긴 사본 `<db 이름>.mails.json`을 쓰므로 출력된 `DUMMY_MAIL_SOURCE`로 띄운다.
- `--source ../data/dummy/demo_mails.json`으로 시연용 메일 묶음을 고른다. `check` · `reset` 명령은 `python -m app.dev.seed -h`.

## 테스트

```bash
.venv/bin/python -m pytest      # CI 'backend 테스트'와 같은 명령. 메모리 DB, 엑사원 불필요
```

`tests/` 34개 파일. ai 호출은 가짜 응답으로 바꿔 시험한다.

## 설정

루트 `.env`(`run_dev.py`가 넘긴다) 또는 셸 환경 변수로 읽는다. 셸 값이 이긴다.

| 변수 | 기본값 | 뜻 |
|---|---|---|
| `APP_MODE` | `dev` | `prod`면 개발용 엔드포인트를 닫고 사용자 확인을 요구한다 |
| `AUTH_MODE` | `header` | `header`: `X-User-Id` 헤더(개발 · 테스트). `session`: 브라우저마다 사용자 하나(httpOnly 쿠키, 비밀번호 없음, 배포용, `app/api/session.py`) |
| `DATABASE_URL` | `sqlite:///./ax.db` | SQLite 주소만 받는다 |
| `AI_SERVICE_URL` | `http://localhost:8001` | ai 서비스 주소 |
| `AI_BACKGROUND_TIMEOUT_S` | `310` | 분류 · 기억 · 신호 호출 대기(ai 백그라운드 300초 + 10). 대화형 호출은 130초 고정 |
| `MAIL_SOURCE` | `dummy` | `dummy` \| `outlook_graph` |
| `MS_GRAPH_CLIENT_ID` · `MS_GRAPH_CLIENT_SECRET` · `MS_GRAPH_REDIRECT_URI` | — | `outlook_graph`일 때 필수. 리디렉션 예: `http://localhost:5173/api/accounts/outlook/callback` |
| `MS_GRAPH_TENANT` | `consumers` | 회사 · 학교 계정도 받으려면 `common` |
| `TOKEN_ENCRYPTION_KEY` | — | 메일 토큰 암호화 Fernet 키. `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `APP_URL` | (같은 출처) | Outlook 로그인 뒤 돌아갈 화면 주소 |
| `GRAPH_NOTIFY_URL` | — | Graph 변경 알림을 받을 공개 HTTPS 주소 앞부분(`/api/graph/notify`가 붙는다). https가 아니면 구독하지 않는다 |
| `CLASSIFY_WORKER` | 꺼짐 | `1`이면 분류 작업자를 띄운다. `CLASSIFY_WORKERS` · `CLASSIFY_PARALLEL`(기본 2 · 2) · `CLASSIFY_WORKER_INTERVAL`(5초) |
| `REMINDER_SCHEDULER` | 꺼짐 | `1`이면 APScheduler가 1분마다 리마인더 엔진을 돈다 |
| `REMINDER_SIGNALS` | 꺼짐 | `1`이면 ai `/signals`로 약속 · 기한 변경 · 해결을 읽는다(엑사원 연결 뒤 켠다) |
| `MEMORY_EXTRACT` | 꺼짐 | `1`이면 엑사원 분류 뒤 메일마다 ai를 한 번 더 불러 캐치봇 문맥 기억을 뽑는다(BE-D21) |
| `CLOCK_START` | (실제 시각) | 시연 시작 시각. 아래 '시간' 참고 |
| `DEMO_TOOLS` | 꺼짐 | `true`면 시간 이동 · 리마인더 강제 실행 라우터를 연다(`APP_MODE`와 관계없다) |
| `DEMO_SHARE_USER_ID` | — | `AUTH_MODE=session`에서 `/api/session/demo`가 붙여 줄 시연 사용자 번호 |
| `DUMMY_MAIL_SOURCE` | `data/dummy/dummy_mails.json` | 더미 메일 본문을 읽는 파일 |

## API

모든 경로는 `/api` 아래다(`/health`만 예외). 요청 · 응답 형식은 [구조도 8절](../docs/00_common/architecture.md)과 `app/schemas/`.

| 묶음 | 경로 | 파일 |
|---|---|---|
| 상태 | `GET /health` | `api/health.py` |
| 세션 | `POST /session` · `GET /session/demo` | `api/session.py` |
| 대시보드 | `GET /dashboard` · `GET /awaiting`(응답 대기) | `api/dashboard.py` · `api/awaiting.py` |
| 메일 | `GET /mails/{id}` · 이동 · 숨김 · 검색 · 첨부 · `POST /mails/{id}/reply` · 전체 회신 · 전달 · 새 메일 · 예약 발송 · `/polish` · `/summary` · `/translate` · `POST /uploads` | `api/mails.py` · `api/reply.py` · `api/polish.py` · `api/translate.py` · `api/uploads.py` |
| 업무 · 행동 | `PATCH /tasks/{id}` · `POST /tasks/bulk/preview` · `POST /actions/execute` · `POST /actions/{id}/undo` | `api/actions.py` |
| 캐치봇 | `POST /agent/command` · `/suggestions` · `/actions/history` · `/agent/memory` · `/agent/settings` | `api/agent_command.py` · `api/agent.py` |
| 리마인더 | `/reminders` · `/notifications` · `/briefings/{kind}` | `api/reminders.py` |
| 캘린더 | `/calendar` · `/events` | `api/calendar.py` |
| 계정 | `/accounts` · `/accounts/outlook/connect` · `/callback` · 동기화 · 연결 해제 · `POST /graph/notify` | `api/accounts.py` · `api/graph_notify.py` |
| 설정 | `GET` · `PATCH /settings` | `api/settings.py` |
| 분류 | `/classify/status` · `/classify/retry` | `api/classify.py` |
| 개발 전용 | `/dev/classify/*` · `/dev/scenario/*`(운영 404) · `/dev/clock` · `/dev/reminders/run`(`DEMO_TOOLS`) | `api/classify.py` · `api/dev_scenario.py` · `api/demo.py` |

모든 응답에 `X-Request-ID`가 붙고 로그 줄에도 같은 ID가 찍힌다(INF-12). ai를 부를 때 `request_id_headers()`로 넘긴다.

## 폴더

```
app/
├── api/         라우터 (위 표)
├── core/        설정 · DB 연결 · 시계(clock.py) · 요청 ID · 사용자 찾기(user.py) · 외부 송신 허용 목록(egress.py)
├── models/      DB 테이블 (users · accounts · mails · tasks · reminders · notifications · action_log …)
├── schemas/     요청 · 응답 형식. ai와 주고받는 형식(schemas/ai.py)은 ai/app/schemas와 함께 고친다
├── services/    여러 경로가 같이 쓰는 로직: 업무 상태 변경 · action_log · 되돌리기 · 응답 대기 · 캘린더 · 기록
├── agent/       행동 레지스트리(tools/registry.py, T01~T20) · 대상 해석 · 확인 정책 · 실행기
├── ai_client/   ai 서비스 호출. 실패는 AIError(timeout · unavailable · bad_response)
├── mail/        Graph 연결 · 동기화 · 변경 알림 · 토큰 암호화 · 본문 읽기
├── reminders/   리마인더 엔진: 유형(types) · 계산(rules) · 알림 정책(policy) · 1분 틱(engine) · 버튼(actions) · 브리핑
├── jobs/        주기 작업: 분류 작업자(worker) · 리마인더 스케줄러(scheduler) · 신호(signals)
├── privacy/     ai에 보내기 전 개인정보 가리기(mask.py)
└── dev/         시연 데이터 시드(seed.py)
```

## 규칙

- **외부 LLM 패키지 · 키를 넣지 않는다**(D26 · D41). 엑사원도 직접 부르지 않고 `ai_client/`로만 요청한다.
- **분류는 백그라운드 작업**으로 보낸다(메일 1통 약 25초). 동기 요청 안에서 기다리지 않는다.
- **업무 상태는 `pending` · `done` · `excluded` · `snoozed` 넷**이다. 모든 상태 변경은 `action_log`에 남는다. REST 버튼 · 캐치봇이 같은 `services/` 함수를 쓴다.
- **답장 뒤에는 완료 확인으로 묻는다.** '오늘 하루 보지 않기'면 바로 완료한다(D48, `source = reply_auto`). 묻지 않고 자동 완료하지 않는다.
- **캐치봇은 레지스트리에 등록한 행동만** 실행한다. 조회 · 표시 · 1건 변경은 바로 실행(되돌리기 제공), 2건 이상 · 설정 변경은 preview → execute, 발송은 항상 미리보기 + 확인(D37).
- **리마인더는 유일 제약으로 중복을 막는다** — `(task_id, rule, slot)`, 업무가 없는 항목은 `(user_id, subject_kind, subject_id, rule, slot)`. 발송 직전에 아직 미처리인지 다시 확인한다(BE-D28).
- **보낸 메일도 저장한다**(`direction=sent`, 응답 대기 계산용). 분류에는 보내지 않는다.
- **메일 본문 · 토큰 · 쿼리 · 헤더를 로그에 남기지 않는다.**

## 시간

시각은 `app/core/clock.py`의 `now()`(한국 시간)만 쓴다. 요청 시각은 `to_kst_naive()`로 저장하고, 응답 시각은 `as_kst()`로 `+09:00`을 붙인다(D47).

<details>
<summary>시연 시각 <code>CLOCK_START</code> · 시간 이동(BE-14)</summary>

- 서버 시작 때 `offset = CLOCK_START - 실제 현재 KST`를 한 번 정하고, `now()`는 `실제 현재 KST + offset`을 낸다. 멈춘 시각이 아니라 실제 시간만큼 흐른다. 예) `CLOCK_START=2026-10-20T09:00`으로 띄우고 5분 뒤 `now()` → `2026-10-20 09:05:00`.
- offset은 프로세스 메모리 값이다. 재시작 · `--reload`면 `CLOCK_START` 기준으로 돌아가고, worker가 여럿이면 서로 나누지 않는다(단일 worker 전제, BE-D23).
- 시간 이동은 `clock.set_offset()`으로 offset을 **바꿔 넣는다**(누적이 아니다). 특정 시각: `clock.set_offset(target - clock.real_now())`, 하루 앞으로: `clock.set_offset(clock.get_offset() + timedelta(days=1))`, 복귀: `clock.set_offset(timedelta(0))`.
- `DEMO_TOOLS=true`면 HTTP로도 된다: `GET /api/dev/clock` · `POST /api/dev/clock` `{"at": "2026-10-20T09:00"}` 또는 `{"forward_minutes": 180}` · `POST /api/dev/clock/reset` · `POST /api/dev/reminders/run?at=ISO`.
- 켜면 누구나 모든 사용자의 서비스 시각을 바꾸고 알림을 만들 수 있다. 공개 배포에서는 켜지 않는다.
- 날짜는 늘 실제 오늘을 쓴다(11-18 결정). 과거로 옮기면 이미 쌓인 `action_log` · 리마인더의 `created_at`이 서비스 시각보다 미래가 되므로, 뒤로 돌아갈 때는 더미를 다시 적재하거나 `reset`만 쓴다.

</details>

## 리마인더

항목은 저장하지 않고 매번 DB 값으로 계산한다. `reminders` 표에는 '언제 몇 번 알렸나'만 남는다. 명세는 [reminders.md](../docs/10_planning/reminders.md), 결정은 BE-D26~D33.

<details>
<summary>리마인더 · 알림 · 브리핑 API</summary>

| 요청 | 응답 |
|---|---|
| `GET /api/reminders?group=all` (`due` · `waiting` · `promise` · `revisit` · `prepare` · `cleanup`) | `{as_of, counts: {due, waiting, promise, revisit, prepare, cleanup, all}, muted_types: [유형], items: [ReminderItem]}`. counts는 group과 상관없이 전체 |
| `POST /api/reminders/{key}/dismiss` `{reason: hide \| not_mine \| wrong_signal \| keep \| stop_waiting}` | `{key, reason, hidden_until, action_id}`. hide는 다음 R-아침까지, not_mine은 T10 기록(action_id로 되돌리기) |
| `POST /api/reminders/{key}/apply` | `{key, action_id, task: TaskState \| null, due_at, commitment_id}`. due_changed → T16, resolved · reply_confirm → T03, their_promise · my_promise → 약속 done. 되돌리기는 `POST /api/actions/{action_id}/undo` |
| `PATCH /api/reminders/types/{type}` `{notify: bool}` | `{type, notify, muted_types}`. 목록에서는 사라지지 않는다 |
| `GET /api/notifications?unread_only=false` | `{items: [Notification], unread}` 최근 100건 |
| `PATCH /api/notifications/{id}` `{read?: true, answer?: "yes" \| "no"}` | 바뀐 Notification. answer는 reply_confirm에만(yes = T03 완료, no = 아직 남았어요) |
| `POST /api/notifications/read-all` | `{updated}` |
| `GET /api/briefings/{morning \| evening \| weekly}?date=YYYY-MM-DD` | `{kind, date, as_of, scheduled_at, title, summary, total, sections: [{id, label, count, items: [...]}]}`. `scheduled_at`은 그 날짜의 브리핑을 만드는 시각(아침 = R-아침, 퇴근 = 근무 끝 30분 전, 주간 = 금요일 근무 끝 30분 전). date는 2000-01-01 ~ 2099-12-31(밖이면 422) |
| `POST /api/dev/reminders/run?at=ISO` | `DEMO_TOOLS=true`일 때만(없으면 404). 그 시각으로 모든 사용자에 엔진을 한 번 돌린다 |

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

- 항목 키: `유형:대상종류:id` — 대상종류는 `task` · `sent_mail` · `commitment` · `day`(YYYYMMDD). 정렬은 기한 이른 순, 기한 없으면 생긴 순, `state = quiet`(3번 알린 뒤, 미룬 일은 예외)는 맨 아래.
- `actions[].action`: 행동 레지스트리 T코드(T03 · T05 · T07 · T13) · `open_mail` · `apply` · `dismiss`(params.reason). T05의 `until: null`은 화면이 시각을 고르게 한다.
- digest 알림: `digest`(같은 분 3건 이상, 제목 "챙길 것 N건") · `away_return`(부재 중 복귀) · `evening` · `weekly`(회고). 들어간 항목은 `reminder_keys`.
- 제안 카드 `GET /api/suggestions`는 이 목록의 앞쪽 N건을 예전 카드 형식으로 준다(BE-D31).

</details>

## 배포

`Dockerfile`은 저장소 루트를 컨텍스트로 빌드한다(`data/dummy`를 함께 담는다). 프로세스는 1개(분류 작업자 · 스케줄러 포함), SQLite는 볼륨 `/data`에 둔다. 서비스 변수는 [infra/railway_setup.md](../infra/railway_setup.md).
