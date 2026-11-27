# eval · 분류 평가 (Claude · OpenRouter는 여기서만)

서비스 모델(엑사원 API)이 메일 속 할 일을 얼마나 맞게 뽑는지 재고, 다른 모델과 비교한다. 서비스에 포함하지 않으며, `ai/app/pipeline`을 그대로 불러 서비스와 같은 호출부로 잰다(`eval → ai`). 서비스 전체 소개는 [저장소 README](../README.md), 점수 기록은 [scores.md](../docs/50_data_eval/scores.md)에 있다.

| 항목 | 내용 |
|---|---|
| 서비스 모델 | 엑사원 API `k-exaone_v2.5`(`LLM_BACKEND=exaone_api`). 로컬 모델은 받지 않는다. 기업 도입 때는 같은 호출부에 엔터프라이즈 LLM을 끼워 다시 잰다(D52 · D58) |
| 비교 모델 | 오픈라우터(Claude Haiku · DeepSeek · Gemma 등). 이 폴더에서만 부른다(D26 · D41 · DE-D24) |
| 최신 결과 | FINAL TEST 200통, `classify_v8.4`: 엑사원 할 일 메일 90/90 찾음 · 정밀도 93.8% · 모든 칸 정답 169/200 ([scores.md 16절](../docs/50_data_eval/scores.md)) |
| 성공 기준 | 테스트셋 할 일 메일 누락 0건(D15) |

## 폴더

| 폴더 | 내용 |
|---|---|
| `runners/` | 세트를 파이프라인에 넣어 `predictions.json`을 만든다. 분류 `run_dummy.py` · 명령 해석 `run_agent_commands.py` · 리마인더 신호 `run_signals.py` · 요약 `run_mail_summary.py`. 모델 맞대기 `compare_models.py` · 영역별 표 `part_table.py` · 추론 강도 표 `effort_table.py` · 명령 표 `command_table.py` |
| `datasets/` | 명령 해석 · 신호 세트(JSONL)와 세트 나눔 정보. 메일 원문은 `data/`에 둔다 |
| `judges/` | Claude 채점(참고값): 할 일 문장 · 요약처럼 코드로 맞히기 어려운 항목만(`judge_tasks.py`, DE-6) |
| `scenarios/` | 캐치봇 시나리오 평가(`run_scenarios.py`) |
| `reports/` | 자동 생성 보고서. 사람이 검수하고 레포에 올리지 않는다(D15) |
| `bench/` | 10/24 초기 모델 고르기 기록. 지금 측정에는 쓰지 않는다 |

채점기는 `data/dummy/eval.py`(표준 라이브러리만, Python 3.10 이상)다.

## 실행

레포 루트에서 `ai/.venv` 파이썬으로 돌린다. 키는 레포 맨 위 `.env`에 둔다(`EXAONE_API_KEY` · `OPENROUTER_API_KEY` · `ANTHROPIC_API_KEY`).

```bash
python data/dummy/eval.py --selfcheck                                  # 채점 로직 점검 → selfcheck OK

# 엑사원(서비스 호출부 그대로). 서비스와 같은 입력이 되게 개인정보를 가린다(--mask)
ai/.venv/bin/python eval/runners/run_dummy.py --set dev4 --llm --mask --retry 2

# 봉인 세트: 레포 밖 파일. 재기 전에 SHA-256을 sealed_sets.md와 맞춘다
EXAONE_REASONING_EFFORT=high ai/.venv/bin/python eval/runners/run_dummy.py --file <레포 밖 폴더>/final_mails.json --llm --mask --retry 2

# 비교 모델(오픈라우터)
ai/.venv/bin/python eval/runners/run_dummy.py --set dev4 --or anthropic/claude-haiku-5.5 --mask

# 명령 해석 · 리마인더 신호
ai/.venv/bin/python eval/runners/run_agent_commands.py --llm
ai/.venv/bin/python eval/runners/run_signals.py --llm
```

- 엑사원 API는 키당 하루 호출 한도가 있다. 한도에 닿으면 받은 출력을 남기고 멈추므로 다음 날 같은 명령에 `--resume`을 붙인다. 키를 쉼표로 여러 개 넣으면 다음 키로 넘어간다(AI-47).
- 모델이 판단하지 못한 메일(호출 실패 · 형식 오류)은 '분류 실패'로 오답이다(AI-D19). `--retry 2`는 그 메일만 두 번 더 부른다.
- `--llm` 없이 돌리면 모델을 부르지 않는다. 실행기 점검용이라 점수 비교에 쓰지 않는다.
- 결과 · 보고서 · 모델 출력 캐시는 `eval/reports/`(봉인 세트는 그 파일 옆)에 남는다. `--replay <캐시>`로 모델 없이 다시 채점한다.
- 세트 목록 · 명령 전체는 [scores.md 실행 표](../docs/50_data_eval/scores.md), 봉인 세트는 [sealed_sets.md](../docs/50_data_eval/sealed_sets.md).

## 규칙

- Claude · 오픈라우터 키와 코드는 이 폴더만 쓴다. `.env.example`은 빈 칸으로 둔다. 서비스 경로에서 이 폴더를 가져다 쓰지 않는다.
- Claude 채점 결과는 정답이 아니라 참고값이다. 코드 채점과 사람 검수가 우선한다.
- 평가 결과를 남길 때는 코드 커밋 · 프롬프트 버전 · 모델(`k-exaone_v2.5` · 추론 강도) · 세트와 정답 버전 · `--mask` 여부를 보고서 맨 위에 적는다. 하나라도 바뀌면 점수를 직접 비교하지 않는다.
- 평가 메일 작성과 재라벨을 Claude가 했으므로 Claude 계열 점수는 이 점을 감안해 읽는다(DE-D33).

## 파트 역할

| 일 | 담당 | 근거 |
|---|---|---|
| 테스트셋 · 정답 라벨 · 명령 테스트 세트, 채점 실행, 보고서 | 데이터 · 평가 | DE-1~DE-13 |
| 분류기 · 명령 해석 구현 | AI | AI-1~AI-47 |
| 채점 결과를 보고 프롬프트 수정안 확정 | 데이터 · 평가 + AI 공동. 반영은 AI, 같은 세트 재채점은 데이터 · 평가 | D46 · DE-9 · AI-18 |
| Claude 채점 · 오픈라우터 모델 비교 | 이 폴더에서만 | D26 · D41 · DE-D24 |

- 라이선스: 엑사원 API는 LG AI연구원 약관을 따른다. 상업적 사용 조건 `[미확인]`.
