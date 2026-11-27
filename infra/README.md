# CNE 인프라 · 배포

배포 설정 문서와 저장소 규칙을 둔다. 배포는 **Railway 서비스 3개**(`web` · `backend` · `ai`)로 하고, 각 서비스의 Dockerfile과 Caddy 설정은 서비스 폴더에 있다. 인프라 담당은 문규남이다(2026-11-07 확정, D45). 서비스 전체 소개는 [저장소 README](../README.md)에 있다.

| 항목 | 내용 |
|---|---|
| 상태 | Railway 배포 완료(11-22), 기본 인증 제거 · 운영 시드 · 메일 추출 켬(11-23), 브라우저별 세션 · Outlook 연결(11-25) |
| 남은 일 | SQLite 볼륨 백업 · 사용량 한도 · 로그 보관 기간 |
| 결정 근거 | [deploy_decision.md](deploy_decision.md)(R1~R10) · [railway_setup.md](railway_setup.md) |

## 기술 스택

| 영역 | 기술 | 버전 | 쓰는 곳 |
|---|---|---|---|
| 호스팅 | Railway (리전 싱가포르) | — | 서비스 3개 · 내부망(`*.railway.internal`) · HTTPS 종료 · 볼륨 |
| 컨테이너 | Docker | — | 서비스마다 `Dockerfile`. Railpack 대신 Dockerfile로 빌드 |
| 웹 서버 · 프록시 | Caddy | 2.10 (alpine) | `web`: 화면 정적 파일 + `/api` → backend 프록시, zstd · gzip |
| 프론트 빌드 | Node.js | 22 (bookworm-slim) | `web` 이미지의 빌드 단계 |
| 파이썬 런타임 | uv 공식 이미지 | python3.12-bookworm-slim | `backend` · `ai` 이미지, `uv sync --locked` |
| 저장소 | SQLite on Railway 볼륨 `/data` | — | `backend`에만 붙인다 → 복제 1개가 플랫폼 규칙으로 지켜진다 |
| CI | GitHub Actions | — | `.github/workflows/ci.yml` 4단계 |
| 검사 | ruff · pytest · `scripts/check_boundaries.py` · 커밋 전 훅(`.githooks/pre-commit`) | — | 경계 · 비밀값 · 테스트 |

## 구성

```
사용자 ── HTTPS ──▶ web  (Caddy: 화면 + /api 프록시)   ← 공개 주소 1개
                      ▼ http://backend.railway.internal:8000
                    backend (FastAPI · 분류 작업자 · 리마인더, 복제 1, 볼륨 /data)
                      ▼ http://ai.railway.internal:8001
                    ai  (FastAPI, 공개 주소 없음) ── HTTPS ──▶ 엑사원 API
```

- HTTPS는 Railway가 끝낸다. 리전은 싱가포르.
- backend는 프로세스 1개로 고정한다 — APScheduler가 둘이면 리마인더를 두 번 보낸다(`deploy_decision.md` R2).
- 운영 변수: `APP_MODE=prod` · `AUTH_MODE=session`(브라우저마다 사용자 하나) · `MAIL_SOURCE=outlook_graph` · `DATABASE_URL=sqlite:////data/demo.db`. 비밀값은 Railway 서비스 변수에만 넣는다.
- 기본 인증은 11-23에 뺐다. 주소를 아는 사람은 누구나 들어올 수 있으므로 **배포 주소는 팀에만 공유하고 레포에 적지 않는다.**

## 파일

| 파일 | 내용 | 작업 |
|---|---|---|
| [railway_setup.md](railway_setup.md) | 서비스 3개 구성 · 변수(비밀값 제외) · 배포 순서 · 확인 방법 · 첫 빌드 로그에서 볼 것 | INF-11 |
| [deploy_decision.md](deploy_decision.md) | 배포 서비스 선정 근거(R1~R10). 보고서 원본은 `CNE_배포_서비스_선정_보고서.docx` | INF-11 |
| [plan.md](plan.md) | 인프라 · 개발 환경 할 일(INF-1~12) · 버전 고정 · `.env` 원칙 · 위험 | — |
| [status.md](status.md) | 기능별 한 일 · 쓰는 법 · 확인 결과 (11-07 기준, 이후 상태는 `plan.md` 작업 표) | — |
| `frontend/Caddyfile` | `/api/health` → backend `/health`, `/api/*` → `{$BACKEND_URL}`, 나머지는 화면 빌드 결과(SPA). zstd · gzip, 해시 붙은 파일 캐시 | INF-11 |
| `backend/Dockerfile` · `ai/Dockerfile` · `frontend/Dockerfile` | 서비스 실행 이미지. backend는 저장소 루트를 컨텍스트로 빌드한다(`data/dummy` 포함). 빌드에서 뺄 파일은 각 `.dockerignore` | INF-11 |

남은 일: SQLite 볼륨 백업(Railway Backups, Hobby 요금제에서 되는지 `[확인 필요]`) · 사용량 한도 · 로그 보관 기간(INF-12).

## 여기에 두지 않는 것

도구가 위치를 정해 둔 파일은 옮기면 동작하지 않는다.

| 파일 | 있어야 하는 곳 | 이유 |
|---|---|---|
| `.env` · `.env.example` | 루트 | 서비스가 루트 `.env` 하나를 읽는다(`plan.md` 3-4) |
| `.gitattributes` · `.editorconfig` · `.pre-commit-config.yaml` | 루트 | 레포 전체에 적용되고, 도구가 루트에서 찾는다 |
| `ruff.toml` | 루트 | ruff는 검사하는 파일에서 위로 올라가며 설정을 찾는다. 루트에 두면 ai · backend · eval · data가 같은 기준을 쓴다 |
| `.python-version` · `.nvmrc` | 루트 | uv · nvm은 현재 폴더부터 위로 올라가며 찾는다 |
| `.githooks/pre-commit` | 루트 `.githooks/` | `git config core.hooksPath .githooks`가 가리키는 곳. 검사 본체는 `scripts/check_boundaries.py` |
| CI 워크플로 · `CODEOWNERS` | `.github/` | GitHub가 이 위치만 읽는다 |
| `uv.lock` · `package-lock.json` · `vite.config.ts` · `Dockerfile` | 각 서비스 폴더 | `pyproject.toml` · `package.json` · 서비스 코드와 같이 바뀐다 |
| `run_dev.py` · `check_boundaries.py` | `scripts/` | 개발자가 직접 돌리는 실행 · 점검 스크립트다(INF-7 · INF-8) |

## CI

`.github/workflows/ci.yml` 네 단계가 PR마다 돈다.

| 단계 | 하는 일 |
|---|---|
| `경계 · 비밀값 · 파이썬 검사` | `scripts/check_boundaries.py`(서비스 경로의 외부 LLM 코드 · 키, 비밀값, `.env.example` 누락) · ruff · 채점기 selfcheck |
| `ai 테스트` | ai pytest (가짜 모델) |
| `backend 테스트` | backend pytest (메모리 DB) |
| `frontend 검사 · 빌드` | npm ci · build · test |

## 저장소 설정 (저장소 관리자, INF-10)

GitHub 화면에서 관리자만 바꿀 수 있어 커밋으로는 하지 못한다.

1. Settings → Rules → Rulesets → New branch ruleset, 대상 `main`
   - Restrict deletions · Block force pushes
   - Require a pull request before merging: 승인 1명, 새 커밋이 올라오면 승인을 다시 받는다(`work_rules.md` 6절)
   - Require status checks to pass: 위 CI 네 단계
2. **11/7 확인: 지금 저장소(비공개, 소유자 무료 개인 계정)는 main 규칙을 켤 수 없다.** GitHub API가 "Upgrade to GitHub Pro or make this repository public to enable this feature"(403)를 돌려준다. 켜려면 소유 계정을 GitHub Pro로 올리거나(학생 인증 GitHub Education이면 무료) 저장소를 공개로 바꾼다. 그전까지는 PR 규칙을 사람이 지키고, 리뷰어가 CI 결과(초록)를 확인한 뒤 승인한다.
3. 비공개 저장소의 GitHub 비밀값 검사(push protection)는 유료 기능이다 `[확인 필요]`. 그래서 커밋 전 훅과 CI의 `scripts/check_boundaries.py`로 막는다.
4. `CODEOWNERS`도 비공개 저장소에서는 Pro 이상에서만 동작한다 `[결정 필요]`.

## 규칙

- 비밀값(키 · 토큰 · 인증서 개인키)은 커밋하지 않는다. 로컬은 `.env`, 배포는 Railway 서비스 변수로 넣는다.
- 서버 IP · 접속 계정 · SSH 키 경로 · 배포 주소는 설정 파일과 문서에 적지 않고 `.env`나 실행 인자로 받는다.
- 설정을 바꾸면 `plan.md` 작업 표의 상태를 같이 고친다.
