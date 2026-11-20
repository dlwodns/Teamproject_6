# eval · 분류 평가 (Claude · OpenRouter는 여기서만)

| 폴더 | 내용 |
|---|---|
| `datasets/` | 평가에 쓸 메일 목록 · 테스트셋/검증셋 나눔 정보. 메일 원문은 `data/`에 두고 여기는 목록만 |
| `runners/` | `ai/app/pipeline`을 그대로 불러 결과(predictions.json)를 만든다. 모델은 엑사원 API(`LLM_BACKEND=exaone_api` + `--llm`, 서비스 호출부 그대로 · D51 · D52) · 오픈라우터(`--or <모델 ID>`, 평가 전용 `openrouter_client.py`, 또는 `--model openrouter:<모델 ID>`) · 로컬 엑사원(`LLM_BACKEND=ollama` + `--llm`). `--model exaone:`은 비교 실험용. 모델끼리는 `compare_models.py`로 맞댄다(최종 · 원출력, `--or` · `--model` 결과 모두, DE-D25). 강도끼리는 `effort_table.py`로 강도 · 회차 · 본문 길이 구간(1,000자 미만 · 1,000~2,000자 · 2,000자 이상)별 표와 io_spec 6절 판단을 낸다(#210, 모델 호출 없음) 명령 해석은 `run_agent_commands.py`(엑사원 하루 한도에 걸리면 `--resume`으로 이어 잼) · 모델 맞대기 · 영역별 표는 `command_table.py`(DE-10). |
| `metrics/` | 코드 채점(재현율 · 누락 건수). 현재 채점기는 `data/dummy/eval.py` |
| `judges/` | Claude 채점(참고값): 할 일 문장 · 요약처럼 코드로 맞히기 어려운 항목만. 할 일 문장 판정은 `judge_tasks.py`(DE-6, `judges/README.md`) |
| `bench/` | 모델 비교 실험. `exaone_20261024/`는 10/24 로컬 벤치 원본 |
| `reports/` | 자동 생성 보고서(md). 사람이 검수한다(D15) |

## 규칙
- 성공 기준: 테스트셋 할 일 메일 누락 0건(D15).
- Claude 키(`ANTHROPIC_API_KEY`) · 오픈라우터 키(`OPENROUTER_API_KEY`)는 이 폴더 코드만 읽는다. 키는 레포 맨 위 `.env`(깃에 안 올라감)에만 두고 `.env.example`은 빈 칸으로 둔다.
- Claude 채점 결과는 정답이 아니라 참고값이다. 코드 채점과 사람 검수가 우선한다.
- 평가 결과를 남길 때는 아래 '버전 기록'의 항목(모델 태그 · 양자화 · ollama 버전 · 프롬프트 버전 · 데이터 버전 · 하드웨어)을 보고서 맨 위에 함께 적는다. 하나라도 바뀌면 점수를 직접 비교하지 않는다.

## 엑사원이 여기서 맡는 역할

> 11/7부터 데이터 · 평가의 분류 측정은 오픈라우터 2종으로 한다(`docs/50_data_eval/decisions.md` DE-D24). 엑사원은 서비스 모델이라 따로 잰다 — 11/11부터 서비스는 엑사원 API(D51 · D53)라 `LLM_BACKEND=exaone_api` + `--llm`으로 잰다(하루 100회, 끊기면 `--resume`, DE-D24 추가). AI-D19부터 모델이 판단하지 못한 메일은 '분류 실패'(오답)이고 '규칙만'은 재지 않는다. 아래는 로컬 엑사원(`LLM_BACKEND=ollama`)으로 잴 때의 안내다.

채점 대상이다. `runners/`가 `ai/app/pipeline`을 불러 엑사원 결과를 만들므로, 채점하려면 엑사원이 로컬(또는 팀 공용 서버)에 있어야 한다. 모델은 서비스와 같은 이름을 쓴다(D44). 설치는 아래 2절이 팀 기준이다.

## 파트 역할

| 일 | 담당 | 근거 |
|---|---|---|
| 테스트셋 · 정답 라벨 · 명령 테스트 세트, 채점 실행, 보고서 | 데이터 · 평가 | DE-1~DE-9 |
| 분류기(규칙 · 라우터 · 엑사원 호출 · 후처리) · 명령 해석 구현 | AI | AI-1~AI-17 |
| 채점 결과를 보고 규칙 · 프롬프트 수정안 확정 | 데이터 · 평가 + AI 공동. 반영은 AI, 같은 테스트셋 재채점은 데이터 · 평가 | D46 · DE-9 · AI-18 |
| Claude 채점 · OpenRouter 모델 비교 | 이 폴더에서만. 분류 측정은 오픈라우터 2종이 기본(데이터 · 평가, 11/7) | D26 · D41 · DE-D24 |

## 1. 기준 버전 (2026-10-31)

| 항목 | 기준 | 근거 |
|---|---|---|
| 분류 모델 | **EXAONE 3.5 7.8B Instruct, GGUF Q4_K_M** | 10/24 벤치 결정(AI-D3 제안) |
| ollama 모델 태그 | `hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:Q4_K_M` | `bench/exaone_20261024/bench_v2.ps1` |
| 비교용(분류기 제외) | EXAONE 4.0 1.2B, GGUF Q8_0 — `hf.co/LGAI-EXAONE/EXAONE-4.0-1.2B-GGUF:Q8_0` | 공지를 할 일로 판단 · 마감 지어냄 |
| 실행기 | ollama 0.34.0 (벤치 기록 기준) | `결과_및_결정.md` |
| 호출 방식 | `POST http://localhost:11434/api/chat`, `stream=false`, `think=false`, `temperature=0`, `format`=JSON 스키마 | `bench_v2.ps1` |
| 벤치 하드웨어 | LG gram, RAM 16GB, CPU만(GPU 없음) | `결과_및_결정.md` |
| 모델 digest (평가 고정값) | `099a498b9cbf…` (전체 값은 `scripts/exaone-pc.env`의 `EXAONE_MODEL_DIGEST`), ollama 0.34.0 | 2026-11-03 PC 엑사원에서 `scripts/exaone-pc.sh pin` (AI-D9) |
| 채점 데이터 | 더미 메일 v1 100건(`data/dummy/dummy_mails.json`, 2026-10-17 생성) | `data/README.md` |
| 채점기 | `data/dummy/eval.py` (표준 라이브러리만 사용, Python 3.10 이상) | 2026-10-31 `--selfcheck` 통과(Python 3.12.3) |

- 2026-11-03 실측(위 digest 기준): 테스트셋 할 일 누락 규칙만 11건 → 엑사원 포함 1건, 메일 1통 평균 약 37초, JSON 형식 오류 0건. 표는 `feature/AI-service`의 `docs/40_ai/plan.md` 4.2절. digest가 다른 PC에서 잰 점수는 이 수치와 직접 비교하지 않는다.
- `.env.example`의 `EXAONE_MODEL`도 위 태그로 맞췄다. ollama 공식 라이브러리 태그(`exaone3.5:7.8b`)는 같은 모델이지만 양자화 · 빌드가 다를 수 있어 평가에는 쓰지 않는다 `[불확실]`.
- 라이선스: EXAONE 모델은 LG AI연구원 라이선스를 따른다. 상업적 사용 가능 여부는 Hugging Face 모델 카드에서 확인해야 한다 `[미확인]`(PRD 제약 · architecture 13절).

## 2. 엑사원 로컬 모델 받기

**① ollama 설치**

| OS | 방법 |
|---|---|
| Windows | https://ollama.com/download 에서 설치 파일 실행. 설치 경로 `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`(벤치 스크립트가 이 경로를 쓴다) |
| macOS | https://ollama.com/download 에서 앱 설치 |
| Linux | `curl -fsSL https://ollama.com/install.sh \| sh` |

설치 뒤 `ollama --version`으로 버전을 확인하고, 평가 보고서에 적는다.

**② 모델 받기** (Hugging Face에서 GGUF를 직접 받는다. 7.8B Q4_K_M은 약 5GB `[대략]`)

```bash
ollama pull hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:Q4_K_M
# 비교 실험을 다시 돌릴 때만
ollama pull hf.co/LGAI-EXAONE/EXAONE-4.0-1.2B-GGUF:Q8_0
```

**③ 확인**

```bash
ollama list    # 위 태그가 보여야 한다
curl http://localhost:11434/api/chat -d '{
  "model": "hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:Q4_K_M",
  "stream": false, "options": {"temperature": 0},
  "messages": [{"role": "user", "content": "한 줄로 자기소개"}]
}'
```

- 첫 호출은 모델 로딩 때문에 느리다(벤치 기록: 7.8B 10~13초). 시간 측정은 첫 호출을 빼고 한다.
- CPU 기준 메일 1통 약 25~28초다. 100건 채점에 약 45분이 걸리므로 `datasets/`의 소규모 목록으로 먼저 확인한다.
- RAM 16GB에서 7.8B Q4_K_M이 동작했다. 8GB 장비는 확인하지 못했다 `[미확인]`.
- 팀 공용 서버 하나에 ollama를 띄우고 나눠 쓸 때는 `.env`의 `OLLAMA_BASE_URL`만 바꾼다. PC 사양이 모자라면 이 방법을 쓴다. 서비스 경로에서 OpenRouter로 바꾸는 방법은 없다(D41).
- ollama가 떠 있지 않으면 `ollama serve`로 켠다. Windows는 `Invoke-RestMethod http://localhost:11434/api/tags`로 모델 목록을 확인한다.
- 메모리가 모자라면 다른 프로그램을 닫고, 작업 후 `ollama stop <모델 이름>`으로 모델을 내린다.
- 1.2B 모델은 분류기로 쓰지 않는다(AI-T1). 모델 · 압축 수준을 바꿀 때는 `bench/`의 같은 벤치로 먼저 비교하고 D44를 새 번호로 대체한다.

## 3. 채점 실행

```bash
python data/dummy/eval.py --selfcheck            # 채점 로직 점검 → selfcheck OK
python data/dummy/eval.py predictions.json       # → eval_report_predictions.md
```

- `predictions.json` 형식은 `data/dummy/eval.py` 맨 위 설명을 따른다(gold와 같은 필드 + 메일 id).
- 보고서는 `reports/`로 옮겨 사람이 검수한다. `reports/`는 레포에 올리지 않는다(.gitignore).

## 4. 벤치 기록 (`bench/exaone_20261024/`)

| 회차 | 메일 | 결과 (7.8B, 조건 C: 규칙 프롬프트 + JSON 스키마 + 코드 후처리) | 파일 |
|---|---|---|---|
| v1 | 가상 업무 메일 8통 | 전 항목 100%, 메일 1통 평균 24.6초 | `bench.ps1` · `mails.json` · `results.csv` · `summary.txt` |
| v2 | 8통 + 공지 · 참조 · 상대 날짜 보강 11통 | 분류 · 할 일 여부 · 우선순위 100%, 마감 91%, 평균 28.4초 | `bench_v2.ps1` · `mails_v2.json` · `results_v2.csv` · `summary_v2.txt` |

- 스크립트는 Windows PowerShell용이다. 다른 OS에서는 `pwsh`(PowerShell 7)로 실행하거나 `runners/`의 Python 실행기로 옮긴다.
- 결정과 한계는 `bench/exaone_20261024/결과_및_결정.md`. 작성자가 만든 메일 8~11통이라 실제 메일 성능을 보장하지 않는다.
