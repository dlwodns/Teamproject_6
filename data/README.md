# data · 더미 메일

개발 · 평가 · 시연에 쓰는 가상 메일을 만들고 보관하는 폴더다. 모두 가상 LG CNS 조직의 메일이고, 실제 사내 메일 · 개인 메일은 어떤 폴더에도 넣지 않는다. 실서비스에 포함하지 않는다.

| 폴더 | 내용 | 레포 업로드 |
|---|---|---|
| `dummy/` | 더미 메일 생성기(`build.py` · `mails*.py` · `people.py`) · 만든 메일(`*_mails.json`) · 사람이 읽는 목록(`*_list.md`) · 채점기(`eval.py`) | O |
| `synthetic/` | MailEx 상황만 뽑아 새로 쓴 메일(D24). 지금 0건 | O |
| `raw/` | MailEx 원본(Enron 실명 포함) | **X** (.gitignore, D24) |

## 세트

| 파일 | 버전 | 메일(통) | 쓰는 곳 |
|---|---|---|---|
| `dummy/dummy_mails.json` | v1.1 | 100 | 개발 세트 dev. 가상 클라우드전환1팀 이준호 팀장 메일함 하루치(10-19) |
| `dummy/test_mails.json` | test-v1.3 | 49 | 개발 세트 dev5(처음엔 테스트셋, 11-05 오답을 열어 고친 뒤 개발 세트로) |
| `dummy/test3_mails.json` | test3-v1.1 | 60 | 개발 세트 dev6(위와 같은 이유) |
| `dummy/dev2_mails.json` | dev2-v1.2 | 47 | 보조 개발 세트 |
| `dummy/dev3_mails.json` | dev3-v1.3 | 60 | 다른 작성자가 쓴 개발 세트 |
| `dummy/dev4_mails.json` | dev4-v1.1 | 54 | 헷갈리는 메일 위주 |
| `dummy/dev7_mails.json` · `dev8_mails.json` | v2.2 | 60 · 60 | 별도 작성자가 쓴 헷갈리는 메일(할 일 있음 25 · 26, 처음 v1은 각 22) |
| `dummy/dev9_mails.json` | dev9-v1 | 20 | 길고 복잡한 메일 |
| `dummy/dev10_mails.json` | dev10-v1 | 36 | 영어 10 · 일본어 8 · 스팸 · 피싱 12 · 사내 2 |
| `dummy/core50_mails.json` | core50-v1 | 50 | 회귀 세트(할 일 있음 25 · 없음 25, `eval/runners/make_core.py`) |
| `dummy/demo_mails.json` | demo-v1 | 115 | **시연용**(받은 100 + 보낸 15). backend 시드로 넣는다. 채점에는 쓰지 않는다 |

- 봉인 테스트 A · B · FINAL TEST는 레포 밖에 둔다. 위치 · SHA-256 · 측정 기록은 [docs/50_data_eval/sealed_sets.md](../docs/50_data_eval/sealed_sets.md).
- 세트 이름(dev5 · dev6 …)과 `--set` 값의 대응은 [eval/datasets/README.md](../eval/datasets/README.md).
- 정답 라벨 기준은 [docs/50_data_eval/label_guide.md](../docs/50_data_eval/label_guide.md).

## 만들기 · 채점

```bash
cd data/dummy
python build.py              # dummy_mails.json 다시 만들기 (검증 오류 0이어야 정상)
python build.py dev4         # 다른 세트는 이름을 준다
python eval.py --selfcheck   # 채점 로직 점검 → selfcheck OK
python eval.py predictions.json   # → eval_report_predictions.md
```

- 생성 · 채점 스크립트는 Python 표준 라이브러리만 쓴다(Python 3.10 이상). 설치할 패키지가 없다.
- 메일을 고치면 세트 버전을 올리고 위 표를 고친다. 평가 보고서에는 데이터 버전을 함께 적는다.
- 레포 안 폴더로는 봉인 세트를 만들지 못하게 `build.py`가 막는다.
- `demo_mails.json`은 발표일(11/28) 기준 날짜로 만들어 두었다(`build.py demo`, #312). `dummy_mails.json`(10/19)은 backend 시드의 `--this-week`가 이번 주로 옮긴다. 둘을 섞어 쓰지 않는다(`backend/README.md` '시연 데이터 넣기').
