# ai · 엑사원 서비스 (FastAPI, 독립 실행)

> 엑사원 역할 · 파트 역할은 `docs/40_ai/README.md`, 행동 목록 · 명령 해석은 `docs/40_ai/detail.md`. 모델 이름은 `hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:Q4_K_M` 하나로 고정한다(D44).

백엔드가 HTTP로 부르는 별도 서비스다(D34). DB에 접근하지 않고, 받은 입력으로 결과만 돌려준다.

| 폴더 | 내용 |
|---|---|
| `app/api/` | 엔드포인트: `POST /classify` · `POST /agent/plan` · `POST /summarize` · `POST /draft` · `POST /memory/extract` · `POST /signals` · `GET /health` (`POST /stt`는 AI-8) |
| `app/core/` | 설정(.env 읽기) · 로깅(본문을 남기지 않는다) |
| `app/schemas/` | 백엔드와 주고받는 요청 · 응답 형식. 바꿀 때는 백엔드 담당과 함께 고친다 |
| `app/pipeline/` | 분류: 라우터 → `rules/`(규칙) → 모호한 것만 엑사원 → 후처리(연도 · 18:00 · 우선순위는 코드로) |
| `app/llm/` | 엑사원 호출(ollama만). 외부 LLM 호출 경로를 두지 않는다(D41). 모델 비교는 `eval/`에서 한다 |
| `app/prompts/` | 분류 · 에이전트 프롬프트 (버전을 파일명에 남긴다) |
| `app/agent/` | 행동형 에이전트의 명령 해석: 규칙 → 애매하면 엑사원 + 예시 → `{action, target, params, source}`. 실행 · 확인 판정은 백엔드가 한다(D37 · D44) |
| `app/voice/` | 서버 STT(Whisper). `STT_MODE=server`일 때만 쓴다 |
| `tests/` | 파이프라인 · 엔드포인트 테스트 |

## 모델 준비

ollama 설치 · EXAONE 모델 받기 · 기준 버전(모델 태그 · 양자화 · 호출 옵션)은 `eval/README.md` 1~2절을 따른다. 서비스와 평가가 같은 모델 태그를 써야 평가 점수가 서비스 성능을 나타낸다.

## 실행

```bash
cd ai
uv sync --locked --extra dev                    # uv.lock 그대로 .venv에 설치(INF-3). pyproject.toml을 고치면 uv lock도 같이 커밋한다
.venv/bin/uvicorn app.main:app --port 8001      # backend .env의 AI_SERVICE_URL과 맞춘다. 셋을 한 번에: python scripts/run_dev.py
.venv/bin/python -m pytest                      # 엑사원 없이 도는 테스트(가짜 모델)
```

### 개발 서버(dev-server-02)에서는 PC 엑사원으로 실행한다 (AI-D9)

서버 메모리 한도(5 GiB)로는 7.8B를 올릴 수 없다(AI-T4). 엑사원은 PC(LG gram)의 ollama에서 돌리고, 서버는 역방향 SSH 터널로 부른다. 서버에 7.8B · llama-server를 띄우지 않는다.

```
PC ollama (127.0.0.1:11434) ──ssh -R──▶ 서버 ~/run/exaone/ollama.sock (0700 폴더) ──▶ ai 서비스 · eval
```

1. PC: ollama를 켜고 `powershell -ExecutionPolicy Bypass -File scripts\pc\exaone-tunnel.ps1` (창을 열어 둔다)
2. 서버, 선택(평가 수치를 남길 때 권장): `scripts/exaone-pc.sh pin` → 모델 digest · ollama 버전이 `scripts/exaone-pc.env`에 고정값으로 적힌다. 커밋한다. 비워 두면 확인 없이 경고만 낸다
3. 서버, 실행할 때마다 `scripts/exaone-pc.sh run`을 앞에 붙인다

```bash
cd ai && ../scripts/exaone-pc.sh run .venv/bin/uvicorn app.main:app --port 8001
scripts/exaone-pc.sh run ai/.venv/bin/python eval/runners/run_dummy.py --set test --llm
scripts/exaone-pc.sh check      # 터널 · 소켓 권한 · 고정값만 확인
```

- `run`은 소켓 폴더가 내 소유 0700이 아니거나, 터널이 끊겼거나, (채워 둔) 고정값과 다르면 명령을 실행하지 않는다.
- 실행 중 고정값이 달라지면(터널을 다시 붙였는데 PC 모델이 바뀐 경우) ai 서비스가 엑사원을 부르지 않는다. 분류 · 명령 해석은 503(model_failed)으로 실패를 알리고 backend가 다시 부른다(AI-D19).
- 고정값을 바꿀 때(ollama 업데이트 · 모델 다시 받기)는 `exaone-pc.env`를 직접 고치고 평가를 다시 돌린다(eval/README.md 버전 기록).
- PC가 꺼져 있으면 분류 · 명령 해석은 503으로 실패를 알린다(규칙으로 메우지 않는다, AI-D19). 서비스 기본은 엑사원 API다(D52).

| 환경 변수 | 기본값 | 뜻 |
|---|---|---|
| `LLM_BACKEND` | `exaone_api` | `exaone_api`(엑사원 API, 기본) · `ollama` · `llamacpp`(로컬 실행기). 이 값 하나로 바꿔 끼운다(D52, AI-D18) |
| `EXAONE_API_KEY` | (빈 값) | 엑사원 API 키. `.env`에만 둔다. 비어 있으면 서비스는 뜨고 모델 호출만 실패한다(분류 · 명령 해석은 503, `/health`의 `llm.error`) |
| `EXAONE_API_MODEL` | `k-exaone_v2.5` | API 모델 이름. 로컬 모델 이름 `EXAONE_MODEL`과 따로 둔다 |
| `EXAONE_API_BASE_URL` | `https://api.exaone.ai/v1` | 바꾸지 않는다 |
| `EXAONE_REASONING_EFFORT` | (빈 값 = API 기본 max) | `low` · `high` · `max`. 추론은 끌 수 없다 |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | ollama 주소. 팀 공용 서버를 쓸 때만 바꾼다 |
| `OLLAMA_UDS` | (빈 값) | 값이 있으면 이 Unix 소켓으로 ollama를 부른다. PC 엑사원 터널용(`scripts/exaone-pc.env`) |
| `EXAONE_MODEL` | `hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:Q4_K_M` | 로컬 옵션 모델. 바꾸지 않는다(D55) |
| `EXAONE_MODEL_DIGEST` | (빈 값) | 고정값. ollama 모델 digest가 다르면 엑사원을 부르지 않는다 |
| `OLLAMA_VERSION` | (빈 값) | 고정값. ollama 버전이 다르면 엑사원을 부르지 않는다 |
| `LLM_ENABLED` | `true` | `false`면 엑사원을 부르지 않는다(모델 없는 PC). 분류 · 명령 해석은 503, 요약 · 초안은 코드 문장 |
| `ROUTER_THRESHOLD` | `0.8` | 규칙 확신도가 이 값 미만인 메일만 엑사원으로 보낸다 `[미정: 측정 후 결정]` |
| `LLM_TIMEOUT_S` | `120` | 모델 호출 제한 시간. API는 혼잡(429 · 5xx) 때 다시 부르는 시간까지 합친다. backend가 기다리는 시간보다 짧게 둔다(대화형 130초 고정, 백그라운드는 backend `AI_BACKGROUND_TIMEOUT_S` — 늘리면 그보다 10초 이상 짧게, AI-28) |
| `OLLAMA_KEEP_ALIVE` | `30m` | 모델을 메모리에 두는 시간. 서비스가 뜰 때 모델을 미리 올린다(첫 호출 117초 → 제한 시간 120초에 걸리지 않게) |

- `GET /health`는 모델이 없어도 `status: ok`다. 모델 상태는 `llm.reachable` · `llm.model_ready`로 따로 본다. ollama는 `llm.version` · `llm.digest` · `llm.pin_mismatch`도 돌려준다.
- 엑사원 API 모드의 `/health`는 API를 부르지 않고 마지막 호출에서 본 상태만 알린다. `llm.error`는 셋 중 하나다: `EXAONE_API_KEY 없음`, `키 거절(HTTP 401) — …`, `하루 호출 한도 소진`. 키 거절과 한도 소진은 다음 호출이 성공하면 지워진다.

### 엑사원 API 운영 점검 (#64 리뷰)

- **키는 발급일부터 30일만 쓸 수 있다.** 한 달 공개 운영(11-13 멘토링) 중에 만료된다. 만료되면 분류가 오류 없이 규칙 결과로만 나와서 알아채기 어렵다. 키를 발급한 사람이 만료 날짜를 팀 일정에 적고, 만료 전에 새 키로 `.env`를 바꾼다.
- **매일 한 번 `/health`를 본다.** `llm.model_ready`가 `false`이고 `llm.error`가 `키 거절`로 시작하면 키가 만료됐거나 틀린 것이다. `하루 호출 한도 소진`이면 다음 날 풀린다.
- **학습용 이용 기록 분석에는 동의하지 않는다.** 메일 본문이 API로 나가므로(D53), 엑사원 API 콘솔에서 이용 기록을 모델 학습 · 분석에 쓰는 데 동의하는 항목은 꺼 둔다. 키를 새로 발급할 때마다 다시 확인한다. 개인정보 가리기(BE-6)는 아직 없으므로 API 모드에는 가상 데이터만 넣는다.

## 리마인더 신호 `POST /signals` (AI-24 · AI-D20)

리마인더(BE-12)가 '내가 한 약속 · 상대 약속 지남 · 기한 바뀜 · 끝난 것 같아요 · 끊긴 대화'를 띄울 때 쓰는 신호를 메일 한 통에서 읽는다. 분류(`/classify`)와 따로 둔 이유는 분류 프롬프트를 흔들지 않고, 보낸 메일에도 부를 수 있게 하기 위해서다. backend는 분류가 끝난 받은 메일과 보낸 메일 동기화 때 부르고, 대화에 미처리 업무가 없는 받은 메일은 부르지 않는다(명세 `docs/10_planning/reminders.md` 8절).

무엇이 약속 · 기한 변경 · 해결 · 질문인지는 모델(`signals_v1`)이 판단한다. 코드는 모델 답을 다른 답으로 바꾸지 않고, 형식이 맞지 않는 신호만 버린다(버린 수는 `dropped`).

- 근거(`evidence`)가 이 메일 본문에 글자 그대로 없으면 그 신호를 버린다. 공백만 느슨하게 맞추고, 화면이 칠할 수 있게 본문 문장 그대로 돌려준다. 앞 메일 · 제목 · 서명 아래 글자는 근거가 아니다.
- 날짜는 `mail.sent_at` 기준으로 `pipeline/dates.py`가 계산한다. 문구로 날짜를 정할 수 없으면('다음 주') `due_at`은 null이고 문구는 남긴다. 메일에 없는 기한 문구는 지어낸 것으로 보고 약속에서는 지우고, 기한 변경은 버린다.
- `task_id`는 받은 `open_tasks` 안의 것만 돌려준다. 새 기한이 지금 기한과 같으면 바뀐 것이 아니므로 버린다.
- 보낸 메일의 약속은 `me`, 받은 메일의 약속은 `them`만 받는다. 보낸 메일의 `asks_me_question`은 늘 false다.
- 모델이 판단하지 못해도 200으로 신호 없이 돌려준다. `fallback`이 `quota`면 시도로 세지 않고 한도가 풀린 뒤, `model_failed` · `bad_output`이면 시도로 세며 다시 부른다(분류와 같은 규칙, AI-D19). `empty_body`(본문이 비었거나 서명 · 답장 인용뿐)는 다시 부르지 않는다.

요청(시각은 시간대가 붙어도 되고, 없으면 KST로 본다. `thread`는 최근 5통 · 앞 400자만 쓰며 `body` 대신 `snippet`이라고 보내도 된다)

```json
{
  "mail_id": 31,
  "mail": {"direction": "received", "sender": "minho.jang@hanbitbank.example",
           "recipients": ["junho.lee@lgcns.example"], "cc": [], "subject": "RE: 이관 일정",
           "body": "…이관 일정표는 11/20까지만 주셔도 됩니다.\n보안 점검 결과는 제가 내일 오전 중에 보내 드리겠습니다.\n…",
           "sent_at": "2026-11-12T10:00:00+09:00"},
  "me": {"email": "junho.lee@lgcns.example", "name": "이준호"},
  "thread": [{"sender": "junho.lee@lgcns.example", "sent_at": "2026-11-11T16:20:00+09:00",
              "subject": "이관 일정", "body": "(앞 400자)"}],
  "open_tasks": [{"task_id": 12, "text": "이관 일정표 보내기", "due_at": "2026-11-13T18:00:00+09:00"},
                 {"task_id": 13, "text": "계정 목록 보내기", "due_at": null}]
}
```

응답(시각은 시간대 없는 KST, id는 문자열)

```json
{
  "mail_id": "31",
  "commitments": [{"who": "them", "text": "보안 점검 결과 보내기", "due_raw": "내일 오전 중",
                   "due_at": "2026-11-13T12:00:00",
                   "evidence": "보안 점검 결과는 제가 내일 오전 중에 보내 드리겠습니다."}],
  "due_changes": [{"task_id": "12", "new_due_raw": "11/20까지", "new_due_at": "2026-11-20T18:00:00",
                   "evidence": "내부 보고가 미뤄져서 이관 일정표는 11/20까지만 주셔도 됩니다."}],
  "resolved": [{"task_id": "13", "reason": "done_by_other",
                "evidence": "계정 목록은 박 과장님이 어제 이미 보내 주셔서 따로 안 주셔도 됩니다."}],
  "asks_me_question": true,
  "source": "exaone", "model": "k-exaone_v2.5", "prompt_version": "signals_v1",
  "elapsed_ms": 9400, "dropped": 0, "fallback": null, "detail": null
}
```

- `reason`: `done_by_other`(다른 사람이 이미 처리) · `cancelled`(일 자체가 취소) · `not_needed`(필요 없어짐 · 이미 받음).
- 모델이 판단하지 못하면 `source: "none"` · 신호 목록은 모두 빈 값 · `fallback`(`quota` | `model_failed` | `bad_output` | `empty_body`) · `detail`(이유, 본문 · 키 없음).
- 개발 세트 채점: `ai/.venv/bin/python eval/runners/run_signals.py --llm`(39통 = 하루 한도 39회). 정의 · 측정은 `docs/40_ai/decisions.md` AI-D20.

## 백엔드와의 경계

```
backend ──(개인정보 가린 메일)──▶ ai  POST /classify   ──▶ 분류 결과 JSON
backend ──(사용자 지시 글자)────▶ ai  POST /agent/plan ──▶ 실행 계획 JSON → backend가 사용자 확인 후 실행
backend ──(메일 · 대화 · 미처리 업무)▶ ai  POST /signals ──▶ 약속 · 기한 변경 · 해결 · 질문 JSON → backend가 리마인더로
backend ──(음성)───────────────▶ ai  POST /stt        ──▶ 글자
```

- 개인정보 가리기는 백엔드(`backend/app/privacy/`)가 보내기 전에 한다. ai는 원문 실명 · 주소를 받지 않는 것을 전제로 한다.
- 엑사원 7.8B는 PC CPU에서 메일 1통 약 37초다(2026-11-03 실측, `docs/40_ai/plan.md` 4.2절). 백엔드는 분류를 백그라운드 작업으로 부르고, 동기 요청 안에서 기다리지 않는다.
- 에이전트가 고를 수 있는 기능 목록은 백엔드 `agent/tools/`와 이름을 맞춘다. 목록에 없는 intent는 돌려주지 않는다.

## 규칙
- Claude(anthropic) · OpenRouter 호출 코드와 키를 넣지 않는다. 실서비스 AI는 엑사원만 쓴다(D41).
- `eval/`은 이 서비스의 `app/pipeline`을 직접 불러 채점한다(`eval → ai`). ai는 `eval`을 가져다 쓰지 않는다.
- 우선순위 · 날짜 보정은 모델에 맡기지 않고 코드로 한다(엑사원 벤치 결정).
