# infra · 배포 설정

> 할 일 · 담당 · 일정 · 버전 고정 · `.env` 원칙은 같은 폴더 `plan.md`(INF-1~12). 인프라 담당은 미정이다(D45, 권장: 백엔드 겸임).

배포 서버에 올라가는 설정을 둔다. 서비스 코드는 각 서비스 폴더(`frontend/` · `backend/` · `ai/`)에, 개발자가 직접 돌리는 실행 · 점검 스크립트는 `scripts/`에 둔다.

| 파일 · 폴더 | 내용 | 작업 |
|---|---|---|
| `README.md` | 이 폴더 규칙 · 파일 위치 · 서버 준비 절차 | — |
| `plan.md` | 인프라 · 개발 환경 할 일(INF-1~12) · 버전 고정 · `.env` 원칙 · 정할 것 · 위험 | — |
| 리버스 프록시 설정 `[예정]` | HTTPS 종료(웹 푸시 필수 조건) · `/api`는 backend로, 나머지는 frontend 빌드 결과로. 도구(Caddy · nginx) `[미정]` | INF-11 |
| 서비스 실행 설정 `[예정]` | backend · ai 기동 · 재시작. backend 워커는 1개로 고정한다(APScheduler 중복 발송 방지, R3). 방식(systemd · docker compose) `[미정]` | INF-11 |
| 배포 · 백업 스크립트 `[예정]` | 배포 순서, SQLite 파일 백업 · 복구 | INF-11 |
| 로그 설정 `[예정]` | 보관 기간 · 회전. 메일 본문은 남기지 않는다(BE-6) | INF-12 |

배포 방식은 11/10 배포 수업 뒤에 정한다. 정해지면 위 표의 `[예정]` 행을 실제 파일 이름으로 바꾼다.

## 여기에 두지 않는 것

도구가 위치를 정해 둔 파일은 옮기면 동작하지 않는다.

| 파일 | 있어야 하는 곳 | 이유 |
|---|---|---|
| `.env` · `.env.example` | 루트 | 서비스가 루트 `.env` 하나를 읽는다(`plan.md` 3-4) |
| `.gitattributes` · `.editorconfig` · `.pre-commit-config.yaml` | 루트 | 레포 전체에 적용되고, 도구가 루트에서 찾는다 |
| `ruff.toml` | 루트 | ruff는 검사하는 파일에서 위로 올라가며 설정을 찾는다. 루트에 두면 ai · backend · eval · data가 같은 기준을 쓴다 |
| `.python-version` · `.nvmrc` | 루트 | uv · nvm은 현재 폴더부터 위로 올라가며 찾는다. 루트에 두면 세 서비스가 같은 값을 쓴다 |
| `.githooks/pre-commit` | 루트 `.githooks/` | `git config core.hooksPath .githooks`가 가리키는 곳. 검사 본체는 `scripts/check_boundaries.py` |
| CI 워크플로 · `CODEOWNERS` | `.github/` (`workflows/`) | GitHub가 이 위치만 읽는다. 할 일 · 후보는 `plan.md` INF-9 |
| `uv.lock` · `package-lock.json` · `vite.config` | 각 서비스 폴더 | `pyproject.toml` · `package.json` 옆에 있어야 한다 |
| Dockerfile (쓰게 되면) | 각 서비스 폴더 | 서비스 코드와 같이 바뀐다. compose 파일만 여기에 둔다 |
| `run_dev` · `check_boundaries.py` · `exaone-pc.sh` · `gpu/` | `scripts/` | 개발자가 직접 돌리는 실행 · 점검 · 측정 스크립트다. 할 일은 `plan.md` INF-7 · INF-8 |

## 규칙

- 비밀값(키 · 토큰 · 인증서 개인키)은 커밋하지 않는다. 서버 `.env`(권한 600) 또는 GitHub Secrets로 넣는다. 방식은 INF-11에서 정한다 `[결정 필요]`.
- 서버 IP · 접속 계정 · SSH 키 경로는 설정 파일에 적지 않고 `.env`나 실행 인자로 받는다 `[제안]`.
- 설정을 바꾸면 `plan.md` 작업 목록의 상태를 같이 고친다.
