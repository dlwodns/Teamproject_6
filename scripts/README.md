# scripts

| 파일 | 내용 |
|---|---|
| `exaone-pc.sh` | 서버에서 ai 서비스 · 평가를 PC 엑사원으로 실행한다(`check` · `pin` · `run <명령>`). 실행 방법은 `ai/README.md` '실행' |
| `exaone-pc.env` | 위 스크립트의 설정 한 곳: 실행기 · 소켓 경로 · 모델 태그 · 고정값(모델 digest · ollama 버전). 비밀값 없음 |
| `pc/exaone-tunnel.ps1` | PC(Windows)에서 실행. ollama 확인 후 서버로 역방향 SSH 터널(Unix 소켓)을 연다 |

예정:
- `check_boundaries.py`: `frontend/` · `backend/` · `ai/`에 anthropic · Claude 호출이 없는지, `backend` · `ai`가 `eval`을 import하지 않는지, `backend`가 `ai` 코드를 import하지 않는지(HTTP로만 부름) 검사
- `run_dev`: 프론트 · 백엔드 · ai 동시 실행
