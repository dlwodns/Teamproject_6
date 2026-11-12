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
| `app/ai_client/` | `ai/` 서비스 호출(`/classify` · `/agent/plan` · `/summarize` · `/draft` · `/health`, `/stt`는 미구현). 주소는 `AI_SERVICE_URL`, 제한 시간 130초. 응답 ID(문자열) → 정수 · 시각 → 시간대 없는 KST 변환은 `app/schemas/ai.py` 한 곳에서(D47). 실패는 `AIError`(timeout · unavailable · bad_response)로 알린다 |
| `app/agent/` | 행동 레지스트리(`tools/`, T01~T14 정의 한 곳) · 대상 해석 · 확인 정책 판정 · preview/execute 실행기. 웹 에이전트 · REST 버튼 · MCP가 같은 정의를 쓴다 |
| `app/privacy/` | ai에 보내기 전 개인정보 가리기 · 본문 읽기 on/off · 로그에 본문 · 토큰 남기지 않기 |
| `app/notify/` | 리마인더 발송: 앱 내 알림 센터 · 웹 푸시(채널 `[미정]`), Apprise는 확장용(D35) |
| `app/jobs/` | 주기 작업(동기화 · 분류 요청 · 리마인더). APScheduler 1프로세스, 시작할 때 DB에서 예약 복구 |
| `app/mcp/` `[예정, P2]` | MCP 서버. 같은 레지스트리를 MCP 도구로 노출 |
| `tests/` | API 테스트. 기준은 구조도 v3.1 12절 19건 |

## 규칙
- Claude(anthropic) · OpenRouter 패키지와 키를 넣지 않는다(D26 · D41).
- 엑사원을 직접 부르지 않는다. 분류 · 명령 해석 · 요약 · 초안 · STT는 `ai_client/`로만 요청한다.
- 분류 요청은 백그라운드 작업으로 보낸다(메일 1통 약 25초). ai가 응답하지 않아도 메일 동기화와 화면은 동작해야 한다.
- 보낸 메일도 저장한다(`direction=sent`, 무응답 계산용). 분류에는 보내지 않는다.
- 업무 상태는 `pending` · `done` · `excluded` · `snoozed` 넷이다. 답장 뒤에는 완료 확인 팝업으로 묻고, '오늘 하루 보지 않기'면 바로 완료한다(D48, `source = reply_auto`). 모든 상태 변경은 `action_log`에 남긴다.
- 에이전트는 레지스트리에 등록한 행동만 실행한다. 확인이 필요한지는 이 서버의 규칙이 정한다: 조회 · 표시 · 1건 변경은 바로 실행(1건 변경은 되돌리기 제공), 2건 이상 · 설정 변경은 preview → execute, 발송은 항상 미리보기 + 확인(D37).
- 리마인더는 `(task_id, rule, slot)` 유일 제약으로 중복을 막고, 발송 직전에 아직 미처리인지 다시 확인한다.
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
- 테이블은 시작할 때 `create_all`로 만든다. 이미 있는 테이블은 고치지 않으므로 테이블 정의를 바꾸면 로컬 `ax.db`를 지우고 다시 만든다. 마이그레이션 도구(Alembic) 도입은 `[미정]`.
- 시각은 `app/core/clock.py`의 `now()`(한국 시간)만 쓴다. 요청 시각은 `to_kst_naive()`로 저장 형식으로, 응답 시각은 `as_kst()`로 `+09:00`을 붙인다(D47). 개발 모드 시간 이동(BE-14)이 여기를 바꾼다.
