# data

| 폴더 | 내용 | 레포 업로드 |
|---|---|---|
| `dummy/` | 더미 메일 v1(가상 LG CNS 팀장 메일함 100건) 생성기 · 정답 · 채점기 | O |
| `synthetic/` | MailEx 상황만 뽑아 새로 쓴 우리 메일(D24). 정답 라벨을 생성할 때 함께 지정 | O |
| `raw/` | MailEx 원본(Enron 실명 포함) | **X** (.gitignore) |

- `dummy/eval.py`는 같은 폴더의 `dummy_mails.json`을 읽는다. 파일을 따로 옮기지 않는다.
- 실제 사내 메일 · 개인 메일은 어떤 폴더에도 넣지 않는다.
