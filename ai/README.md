# ai · 엑사원 서비스 (FastAPI, 독립 실행)

> 엑사원 역할 · 파트 역할은 `docs/40_ai/README.md`, 행동 목록 · 명령 해석은 `docs/40_ai/detail.md`. 모델 이름은 `hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:Q4_K_M` 하나로 고정한다(D44).

백엔드가 HTTP로 부르는 별도 서비스다(D34). DB에 접근하지 않고, 받은 입력으로 결과만 돌려준다.

| 폴더 | 내용 |
|---|---|
| `app/api/` | 엔드포인트: `POST /classify` · `POST /agent/plan` · `POST /summarize` · `POST /draft` · `GET /health` (`POST /stt`는 AI-8) |
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
uv venv .venv && uv pip install --python .venv/bin/python -r pyproject.toml --extra dev
.venv/bin/uvicorn app.main:app --port 8001      # backend .env의 AI_SERVICE_URL과 맞춘다
.venv/bin/python -m pytest                      # 엑사원 없이 도는 테스트(가짜 모델)
```

### 개발 서버(dev-server-02)에서는 PC 엑사원으로 실행한다 (AI-D9)

서버 메모리 한도(5 GiB)로는 7.8B를 올릴 수 없다(AI-T4). 엑사원은 PC(LG gram)의 ollama에서 돌리고, 서버는 역방향 SSH 터널로 부른다. 서버에 7.8B · llama-server를 띄우지 않는다.

```
PC ollama (127.0.0.1:11434) ──ssh -R──▶ 서버 ~/run/exaone/ollama.sock (0700 폴더) ──▶ ai 서비스 · eval
```

1. PC: ollama를 켜고 `powershell -ExecutionPolicy Bypass -File scripts\pc\exaone-tunnel.ps1` (창을 열어 둔다)
2. 서버, 처음 한 번만: `scripts/exaone-pc.sh pin` → 모델 digest · ollama 버전이 `scripts/exaone-pc.env`에 고정값으로 적힌다. 커밋한다
3. 서버, 실행할 때마다 `scripts/exaone-pc.sh run`을 앞에 붙인다

```bash
cd ai && ../scripts/exaone-pc.sh run .venv/bin/uvicorn app.main:app --port 8001
scripts/exaone-pc.sh run ai/.venv/bin/python eval/runners/run_dummy.py --set test --llm
scripts/exaone-pc.sh check      # 터널 · 소켓 권한 · 고정값만 확인
```

- `run`은 소켓 폴더가 내 소유 0700이 아니거나, 터널이 끊겼거나, 고정값과 다르면 명령을 실행하지 않는다.
- 실행 중 고정값이 달라지면(터널을 다시 붙였는데 PC 모델이 바뀐 경우) ai 서비스가 엑사원을 부르지 않고 규칙 결과만 낸다.
- 고정값을 바꿀 때(ollama 업데이트 · 모델 다시 받기)는 `exaone-pc.env`를 직접 고치고 평가를 다시 돌린다(eval/README.md 버전 기록).
- PC가 꺼져 있으면 서비스는 규칙 결과만 낸다. 실배포 · 시연 때 모델을 어디서 돌릴지는 따로 정한다 `[결정 필요]`.

| 환경 변수 | 기본값 | 뜻 |
|---|---|---|
| `LLM_BACKEND` | `ollama` | `ollama` · `llamacpp` (둘 다 로컬 실행기, D41) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | ollama 주소. 팀 공용 서버를 쓸 때만 바꾼다 |
| `OLLAMA_UDS` | (빈 값) | 값이 있으면 이 Unix 소켓으로 ollama를 부른다. PC 엑사원 터널용(`scripts/exaone-pc.env`) |
| `EXAONE_MODEL` | `hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:Q4_K_M` | 바꾸지 않는다(D44) |
| `EXAONE_MODEL_DIGEST` | (빈 값) | 고정값. ollama 모델 digest가 다르면 엑사원을 부르지 않는다 |
| `OLLAMA_VERSION` | (빈 값) | 고정값. ollama 버전이 다르면 엑사원을 부르지 않는다 |
| `LLM_ENABLED` | `true` | `false`면 엑사원을 부르지 않고 규칙 결과만 낸다(모델 없는 PC) |
| `ROUTER_THRESHOLD` | `0.8` | 규칙 확신도가 이 값 미만인 메일만 엑사원으로 보낸다 `[미정: 측정 후 결정]` |
| `LLM_TIMEOUT_S` | `120` | 모델 호출 제한 시간 |

- `GET /health`는 모델이 없어도 `status: ok`다. 모델 상태는 `llm.reachable` · `llm.model_ready`로 따로 본다. ollama는 `llm.version` · `llm.digest` · `llm.pin_mismatch`도 돌려준다.

## 백엔드와의 경계

```
backend ──(개인정보 가린 메일)──▶ ai  POST /classify   ──▶ 분류 결과 JSON
backend ──(사용자 지시 글자)────▶ ai  POST /agent/plan ──▶ 실행 계획 JSON → backend가 사용자 확인 후 실행
backend ──(음성)───────────────▶ ai  POST /stt        ──▶ 글자
```

- 개인정보 가리기는 백엔드(`backend/app/privacy/`)가 보내기 전에 한다. ai는 원문 실명 · 주소를 받지 않는 것을 전제로 한다.
- 엑사원 7.8B는 CPU에서 메일 1통 약 25초다. 백엔드는 분류를 백그라운드 작업으로 부르고, 동기 요청 안에서 기다리지 않는다.
- 에이전트가 고를 수 있는 기능 목록은 백엔드 `agent/tools/`와 이름을 맞춘다. 목록에 없는 intent는 돌려주지 않는다.

## 규칙
- Claude(anthropic) · OpenRouter 호출 코드와 키를 넣지 않는다. 실서비스 AI는 엑사원만 쓴다(D41).
- `eval/`은 이 서비스의 `app/pipeline`을 직접 불러 채점한다(`eval → ai`). ai는 `eval`을 가져다 쓰지 않는다.
- 우선순위 · 날짜 보정은 모델에 맡기지 않고 코드로 한다(엑사원 벤치 결정).
