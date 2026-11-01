# eval · 엑사원 분류 평가 (Claude는 여기서만)

| 폴더 | 내용 |
|---|---|
| `datasets/` | 평가에 쓸 메일 목록 · 테스트셋/검증셋 나눔 정보. 메일 원문은 `data/`에 두고 여기는 목록만 |
| `runners/` | `ai/app/pipeline`을 그대로 불러 엑사원 결과(predictions.json)를 만든다 |
| `metrics/` | 코드 채점(재현율 · 누락 건수). 현재 채점기는 `data/dummy/eval.py` |
| `judges/` | Claude 채점: 할 일 문장 · 요약처럼 코드로 맞히기 어려운 항목만 |
| `bench/` | 모델 비교 실험. `exaone_20261024/`는 10/24 로컬 벤치 원본 |
| `reports/` | 자동 생성 보고서(md). 사람이 검수한다(D15) |

## 규칙
- 성공 기준: 테스트셋 할 일 메일 누락 0건(D15).
- Claude 키(`ANTHROPIC_API_KEY`)는 이 폴더 코드만 읽는다.
- Claude 채점 결과는 정답이 아니라 참고값이다. 코드 채점과 사람 검수가 우선한다.

## 엑사원이 여기서 맡는 역할

채점 대상이다. `runners/`가 `ai/app/pipeline`을 불러 엑사원 결과를 만들므로, 채점하려면 엑사원이 로컬에 있어야 한다. 모델은 서비스와 같은 이름을 쓴다(D35).

## 파트 역할

| 일 | 담당 | 근거 |
|---|---|---|
| 테스트셋 · 정답 라벨, 채점 실행, 보고서 | 데이터 · 평가 | DE-1~DE-8 |
| 분류기(규칙 · 라우터 · 엑사원 호출 · 후처리) 구현 | AI | AI-1~AI-9 |
| 채점 결과를 보고 규칙 · 프롬프트 수정안 확정 | 데이터 · 평가 + AI 공동. 반영은 AI, 같은 테스트셋 재채점은 데이터 · 평가 | D36 · DE-9 · AI-10 |
| Claude 채점 | 이 폴더에서만, 참고값 | D26 |

## 엑사원 준비

1. Ollama 설치: https://ollama.com/download
2. 모델 받기: `ollama pull hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:Q4_K_M`
3. 확인: `ollama list` → 위 이름이 있다. `Invoke-RestMethod http://localhost:11434/api/tags`(Windows) 또는 `curl http://localhost:11434/api/tags` → `models`에 같은 이름이 있다.
4. `.env`: `LLM_PROVIDER=ollama` · `EXAONE_MODEL=hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:Q4_K_M`

- 사양 · 호출 조건 · 속도 · 주의는 `docs/40_ai/README.md` 3절. 두 곳 내용이 다르면 그쪽을 따른다.
- 채점 보고서에 쓴 모델 이름을 적는다 `[제안]`. 다른 모델로 낸 결과와 섞이지 않게 하기 위해서다.
