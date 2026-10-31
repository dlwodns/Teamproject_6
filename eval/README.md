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
