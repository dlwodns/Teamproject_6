# scripts

개발자가 직접 돌리는 실행 · 점검 스크립트다. 서비스에는 들어가지 않는다.

| 파일 | 내용 |
|---|---|
| `run_dev.py` | ai · backend · frontend를 한 번에 띄우고 Ctrl+C로 한 번에 끈다(INF-7). 밖에 여는 포트는 frontend 하나(Vite 프록시). `--no-llm`(엑사원 없이) · `--only` · `--reload`. 공용 개발 서버에서는 계정 번호로 포트를 정한다. 표준 라이브러리만, Windows도 된다 |
| `check_boundaries.py` | 경계 · 비밀값 검사(INF-8): 서비스 경로의 외부 LLM 호출 · eval import · backend의 ai import · ai의 DB 접근, 키 · 토큰 · `.env` · `data/raw/` · 계정 홈 경로 · IP. `--staged`(커밋 전 훅 `.githooks/pre-commit`) · `--all`(CI) · `--selfcheck` |
| `plan_sync.py` | `docs/*/plan.md` 작업 표를 GitHub 이슈 · 마일스톤에 맞춘다. 기본은 보기만(dry run), `--apply`로 반영 |
| `exaone-pc.sh` · `exaone-pc.env` · `pc/` · `gpu/` | 지금 쓰지 않는다. 서비스가 엑사원 API로 바뀌기 전(11-11) PC ollama 터널 · GPU 측정에 쓰던 스크립트다 |

```bash
python scripts/run_dev.py                 # 세 서비스 한 번에
python scripts/run_dev.py --no-llm        # 엑사원 없이(분류 · 명령은 실패를 알린다)
python scripts/check_boundaries.py --all  # CI와 같은 검사
python scripts/plan_sync.py               # plan.md ↔ 이슈 차이 보기
```
