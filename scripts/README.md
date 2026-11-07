# scripts

| 파일 | 내용 |
|---|---|
| `check_boundaries.py` | 경계 · 비밀값 검사(INF-8): 서비스 경로의 외부 LLM 호출 · eval import · backend의 ai import · ai의 DB 접근, 키 · 토큰 · `.env` · `data/raw/` · 계정 홈 경로 · IP. `--staged`(커밋 전 훅 `.githooks/pre-commit`) · `--all`(CI) · `--selfcheck` |
| `exaone-pc.sh` | 서버에서 ai 서비스 · 평가를 PC 엑사원으로 실행한다(`check` · `pin` · `run <명령>`). 실행 방법은 `ai/README.md` '실행' |
| `exaone-pc.env` | 위 스크립트의 설정 한 곳: 실행기 · 소켓 경로 · 모델 태그 · 고정값(모델 digest · ollama 버전). 비밀값 없음 |
| `pc/exaone-tunnel.ps1` | PC(Windows)에서 실행. ollama 확인 후 서버로 역방향 SSH 터널(Unix 소켓)을 연다 |
| `run_dev.py` | ai · backend · frontend 동시 실행(INF-7). 밖에 여는 포트는 frontend 하나(Vite 프록시), `--no-llm` · `--only` · `--reload`. 표준 라이브러리만, Windows도 된다 |
| `gpu/` | 빌린 GPU에서 최종 측정(`gpu/README.md`) |
