# eval/judges · 판정 (참고값, DE-6)

코드로 정답을 하나로 정할 수 없는 칸(할 일 문장 · 요약 · 회신 초안)을 판정자 모델이 본다. **정답이 아니라 참고값**이다. 코드 채점(`data/dummy/eval.py`)과 사람 검수가 우선한다(D15 · plan 10절). 판정자는 eval에서만 쓰는 오픈라우터 Claude다(D26 · DE-D24, 서비스 경로 `ai/`에는 두지 않는다).

| 파일 | 하는 일 |
|---|---|
| `judge_tasks.py` | 예측 할 일과 정답 할 일의 짝마다 같은 일인지 판정(같음 · 일부 · 다름). 예측 파일 옆에 `judge_<예측 이름>.md` 보고서와 판정 캐시를 남기고, 같은 예측의 `eval_report` 10절 칸을 개수로 채운다 |

```
# 레포 루트, ai/.venv 파이썬, 키는 .env의 OPENROUTER_API_KEY
python eval/judges/judge_tasks.py eval/reports/predictions_dev4_or-anthropic-claude-haiku-5.5.json --set dev4
python eval/judges/judge_tasks.py <봉인 폴더>/predictions_testA_api-k-exaone_v2.5.json --file <봉인 폴더>/testA_mails.json
python eval/judges/judge_tasks.py <예측> --set dev4 --dry     # 판정 없이 짝 수 · 부를 횟수만
python eval/judges/judge_tasks.py --selfcheck                 # 가짜 판정자로 점검(네트워크 없음)
```

- 짝은 `eval.py`와 같은 글자 유사도 1:1 짝짓기다. 놓친 할 일 · 더 만든 할 일 · 분류 실패 메일은 짝이 없어 판정에서 빠진다(그건 코드 채점이 센다).
- 같은 짝(판정자 · 프롬프트 · 메일 · 두 문장이 같음)은 캐시에서 읽고 다시 부르지 않는다. 판정자나 프롬프트(`judge_tasks_v2`)를 바꾸면 다시 판정한다.
- 봉인 세트(레포 밖 정답)는 보고서에 개수만 적고 메일 ID · 문장을 적지 않는다. 예측 · 보고서 · 캐시는 그 폴더에만 둔다(DE-D15).
- 요약 · 회신 초안 품질 판정은 시연 기능(T01 오늘 요약 · 초안)이 화면에 붙은 뒤 같은 방식으로 더한다(DE-6 남은 일).
