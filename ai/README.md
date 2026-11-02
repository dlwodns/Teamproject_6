# ai · 엑사원 서비스 (FastAPI, 독립 실행)

> 엑사원 역할 · 파트 역할은 `docs/40_ai/README.md`, 행동 목록 · 명령 해석은 `docs/40_ai/detail.md`. 모델 이름은 `hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:Q4_K_M` 하나로 고정한다(D44).

백엔드가 HTTP로 부르는 별도 서비스다(D34). DB에 접근하지 않고, 받은 입력으로 결과만 돌려준다.

| 폴더 | 내용 |
|---|---|
| `app/api/` | 엔드포인트: `POST /classify` · `POST /agent/plan` · `POST /stt` · `GET /health` |
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
