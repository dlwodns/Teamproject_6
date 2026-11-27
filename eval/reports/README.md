# reports

자동 생성 보고서 자리. 생성물은 레포에 올리지 않고, 검수한 보고서만 `docs/`로 옮긴다.

- `summary.md`: 요약 보고서 하나. `eval/runners/run_dummy.py`를 돌릴 때마다 그 세트 · 방식 줄만 덮어쓴다(놓침 · 할 일로 잡음 · 정밀도 · 메일 1통 시간 · 놓친 메일 ID). 줄 값은 옆 `summary.json`.
- `eval_report_predictions_<세트>_<방식>.md`: 세트 · 방식별 상세 보고서. 같은 세트 · 방식을 다시 돌리면 덮어쓴다. 0절 한눈 요약부터 읽는다.
- `predictions_<세트>_<방식>.json`(예측) · `llm_cache_<예측 이름>.json`(모델 출력, `--replay`로 다시 채점) · `timing_<예측 이름>.json`(처리 시간, `effort_table.py` · `part_table.py`가 읽음).
- 다른 측정기 결과도 여기 남는다: 명령 해석 `<세트>_<방식>.md` · `.results.json`(`run_agent_commands.py`), 모델 맞대기 `compare_<세트>.md`, 판정 `judge_<예측 이름>.md`, 요약 · 회고 머리 문장 `briefing_payloads*.json` · `briefing_effort*.json` · `.md`.
- 봉인 테스트(`--file`)는 결과 · 요약이 세트 폴더(레포 밖)에 남고, 메일 ID는 적지 않는다. FINAL TEST · 테스트 A 점수는 `docs/50_data_eval/scores.md`에 개수만 옮긴다.
