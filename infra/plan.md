# 인프라 · 개발 환경 할 일

> 상태: 코드 마감(11-27) · 작성: 문규남 · 결정: 문규남(인프라 담당) · 리뷰: [미정] · 갱신: 2026-11-27
> 인프라 담당은 **문규남**이다(2026-11-07 확정, D45의 남은 일). 작업 번호 접두어 `INF`는 제안이다.
> 인프라 문서는 이 폴더(`infra/`)에 모은다: 폴더 규칙 · 파일 위치는 `README.md`, 할 일 · 원칙은 이 문서, **한 일 · 쓰는 법 · 확인 결과는 `status.md`**. (2026-11-03 `docs/00_common/infra.md`에서 옮김)

## 1. 목표 · 범위

- 팀원 각자 PC(Windows 포함)와 개발 서버(dev-server-02)에서 **같은 명령으로 같은 결과**를 낸다.
- 범위: 버전 고정 · 환경 변수(`.env`) · 줄바꿈 · 린트 · 빌드 · 테스트 · 동시 실행 · 경계 검사 · CI · 저장소 설정 · 배포.
- 지금 정하는 이유: FE-1 · BE-1 골격이 곧 생긴다. 골격 전에 버전 · 줄바꿈 · 포맷을 정하지 않으면 나중에 전 파일이 한꺼번에 바뀌는 커밋이 생기고, 기능 PR과 섞여 충돌이 난다.
- 파일 위치: 배포 문서는 루트 `infra/` 폴더에 둔다. Dockerfile · Caddyfile은 각 서비스 폴더(`backend/` · `ai/` · `frontend/`)에 있다(INF-11, `README.md`). 루트 · `.github/` · 각 서비스 폴더에 있어야 하는 파일(`.env` · `.gitattributes` · `.python-version` · CI 등)은 옮기지 않는다. 표는 같은 폴더 `README.md`.
- 범위 밖: 엑사원 서빙 위치(구조도 13절, 응답 시간 측정 후 결정 → 엑사원 API로 정함, D51 · D53), 각 파트 기능 코드.

## 2. 시작할 때 상태와 지금 (2026-11-03 확인)

| 항목 | 11/3 시작할 때 | 문제 | 지금 |
|---|---|---|---|
| Python 버전 | 루트 README 3.10 이상 · `ai/pyproject.toml` 3.11 이상 · 개발 서버 3.12.3 | 문서마다 기준이 다르다 | **해결** INF-1: `.python-version` 3.12 · README 4-1 |
| Node 버전 | 루트 README 20 이상 `[제안]` · 개발 서버 v22.23.2 | frontend 골격 전이라 미정 | **해결** INF-1: `.nvmrc` 22 |
| 의존성 잠금 | ai는 `>=`만 있고 lock 파일이 없다(`feature/AI-service`). backend · frontend는 골격 전 | 설치한 날짜에 따라 버전이 달라진다 | **해결** INF-3: `ai/uv.lock` · `backend/uv.lock`, CI는 `--locked`. frontend `package-lock.json`도 FE-1과 함께 main에 들어왔다 |
| 줄바꿈 | 추적 파일 10개가 CRLF(`data/dummy/dummy_mails.json` · `mail_list.md` · `eval/bench/exaone_20261024/` 8개). `.gitattributes` 없음 | Windows에서 만든 `.sh`가 CRLF로 올라오면 서버 bash에서 실패한다 | **해결** INF-2: `.gitattributes` · `.editorconfig`, CRLF 10개 LF로 |
| 환경 변수 | `.env.example` 15개. ai 코드가 읽는 11개 중 `OLLAMA_BASE_URL` · `EXAONE_MODEL` 2개만 들어 있다(`feature/AI-service` 기준) | 새로 받은 사람이 `.env`를 채울 수 없다 | **해결** INF-4: 빠진 ai 변수를 주석(`# NAME=기본값`)으로 채움, 빠지면 CI가 막는다, 서비스는 시작할 때 설정을 검사한다 |
| 린트 · 포맷 | 없음 | 사람마다 포맷이 달라 diff가 커진다 | 일부 INF-5: ruff 실제 오류만. 스타일 · 포맷은 팀 결정 뒤 |
| CI | 워크플로 없음. 11/10 배포 수업 후 추가(옛 `.github/workflows/README.md` 메모는 INF-9로 옮겼다) | — | **해결** INF-9: `ci.yml`. PR마다 돈다(11-27 확인) |
| 경계 검사 · 동시 실행 | `scripts/README.md`에 `check_boundaries.py` · `run_dev` 예정 | — | **해결** 경계 검사 INF-8 · 동시 실행 INF-7(`scripts/run_dev.py`) |
| 시간대 | 개발 서버 `Asia/Seoul`. GitHub Actions 러너는 UTC | 기한 18:00 · 리마인드 08:30 테스트가 CI에서만 깨질 수 있다 | **해결** CI `TZ=Asia/Seoul`(INF-9), backend `app/core/clock.py`가 `ZoneInfo("Asia/Seoul")`(BE-1). ai는 시각을 backend 요청의 `now`로 받는다 |
| 개발 서버 포트 | 외부 브라우저 접속은 계정마다 할당된 포트(환경 변수 `$PORT`)와 `--host 0.0.0.0`이 필요하다. 계정 이름 · 포트 번호는 문서에 적지 않고 각자 `echo $PORT`로 확인한다. **11/7 확인: 여러 계정이 같은 서버를 써서 127.0.0.1의 8000 · 5173이 이미 다른 계정에 잡혀 있다** | 서비스 3개를 각각 외부에 열 수 없고, 고정 포트로 띄우면 다른 계정과 부딪힌다 | **해결** INF-7: 밖에는 frontend(`$PORT`) 하나만, ai · backend 포트가 사용 중이면 빈 포트를 골라 서로 잇는다 |
| Windows 출력 인코딩 | 한국어 Windows에서 `run_dev.py` 출력이 cp949다. 안내 문장의 `—`(U+2014)를 찍는 순간 `UnicodeEncodeError`로 죽는다(11/14, 루트 `.env` 없을 때 첫 안내에서 재현) | 서비스 3개가 같이 꺼진다. 서비스 로그도 run_dev가 옮겨 찍어 같은 문자가 나오면 같은 일이 난다 | **해결**: `main()` 시작에 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` |
| 서버 내부 정보 | 문서 · 스크립트에 계정 이름 · 홈 경로 · 개인 PC 경로 | 저장소를 공개하면 드러난다 | **해결**: 4곳 정리(`status.md` 4절), 다시 들어오면 INF-8이 막는다 |
| 비밀값 차단 | `.gitignore` · PR 체크 항목(사람 눈)뿐 | 실수로 키를 커밋해도 막는 것이 없다 | **해결** INF-8: 커밋 전 훅 + CI |

## 3. 버전 고정 · 환경 변수 원칙 `[제안]`

### 3-1. 고정값은 커밋하는 파일에, `.env`에는 사람 · 환경마다 다른 값만

`.env`는 레포에 올리지 않는다. 버전 고정값을 `.env`에만 두면 팀원마다 값이 달라진다. 그래서 둘을 나눈다.

| 무엇 | 어디에 둔다 | 커밋 | 예 |
|---|---|---|---|
| 버전 고정값 | 아래 3-2 표의 파일 | O | Python 3.12, Node 22, 패키지 lock, 엑사원 digest |
| 공용 기본값 | 코드의 설정 기본값 + `.env.example` | O | 포트, `MAIL_SOURCE=dummy` |
| 사람 · 환경마다 다른 값 · 비밀값 | `.env` | X | API 키, 토큰, 암호화 키, 내 PC 소켓 경로 |

`scripts/exaone-pc.env`(AI-D9)가 이미 이 방식이다. 비밀값 없이 고정값만 담고 커밋한다.

### 3-2. 버전 고정 위치

| 대상 | 고정하는 파일 | 제안 값 | 설치 명령 |
|---|---|---|---|
| Python | 루트 `.python-version`(uv가 읽는다) + 각 `pyproject.toml`의 `requires-python` | 3.12 (개발 서버와 같게) | — |
| Node | 루트 `.nvmrc` + `frontend/package.json`의 `engines` | 22 (개발 서버 v22.23.2) | — |
| Python 패키지 | `ai/uv.lock` · `backend/uv.lock` 커밋 | — | `uv sync --locked` |
| npm 패키지 | `frontend/package-lock.json` 커밋 | — | `npm ci` |
| 엑사원 · ollama | `scripts/exaone-pc.env`의 `EXAONE_MODEL_DIGEST` · `OLLAMA_VERSION` (이미 있음, AI-D9) | `099a498b9cbf…` · 0.34.0 | `scripts/exaone-pc.sh pin` (11-27: 로컬 엑사원은 쓰지 않음) |
| 모델 태그 | `EXAONE_MODEL` (D44) | `hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:Q4_K_M` | — (D55로 대체: 서비스 모델은 엑사원 API `k-exaone_v2.5`) |
| CI 액션 | 워크플로 파일에 주 버전까지 적는다 | 예: `actions/checkout@v4` | — |

- 채점기 · 더미 생성기(`data/dummy/`)는 표준 라이브러리만 쓰는 규칙을 그대로 둔다. Python 3.12로 고정해도 바뀌지 않는다.
- 버전을 올릴 때는 고정 파일과 lock을 한 커밋에서 같이 바꾸고, 커밋 메시지에 이유를 적는다.

### 3-3. 표준 라이브러리

같은 일에 라이브러리를 두 개 쓰지 않는다. 파트 골격을 만들 때 아래 표를 채우고, 바꿀 때는 파트 decisions에 남긴다.

| 용도 | ai · backend | frontend |
|---|---|---|
| 웹 서버 · 스키마 | FastAPI · pydantic (이미 사용) | — |
| 설정(`.env` 읽기) | pydantic-settings `[제안]` | Vite `import.meta.env` |
| HTTP 호출 | httpx (이미 사용) | `fetch` 감싼 함수 하나(`src/api/`) `[제안]` |
| 날짜 · 시간대 | 표준 `zoneinfo`(`Asia/Seoul` 명시) | [미정] |
| 테스트 | pytest | Vitest `[제안]` |
| 린트 · 포맷 | ruff | ESLint + Prettier `[제안]` |

### 3-4. 환경 변수 규칙

1. `.env`는 루트에 하나 둔다. 서비스마다 자기 묶음만 읽는다(지금 `.env.example` 묶음 구조 그대로).
2. 코드가 읽는 변수는 모두 `.env.example`에 있어야 한다. 한 파트만 읽는 변수는 그 파트 브랜치에서 추가한다(`CONTRIBUTING.md` 2). INF-8 검사에서 빠진 변수를 잡는다.
3. 서비스는 시작할 때 설정을 검사한다. `APP_MODE=prod`인데 필수값이 비어 있으면 뜨지 않는다. 비밀값은 로그 · `/health`에 찍지 않는다.
4. frontend(Vite)는 기본 설정에서 `frontend/` 폴더의 `.env`만 읽고, 화면 코드에는 `VITE_`로 시작하는 변수만 넘어간다. `VITE_` 값은 빌드 결과에 그대로 들어가 누구나 볼 수 있으므로 비밀값을 넣지 않는다. 지금 README 표의 `STT_MODE`(frontend · backend)는 frontend용 이름(`VITE_STT_MODE` 등)과 읽는 위치를 FE-1에서 정한다.
5. 배포 서버 비밀값은 서버 `.env`(권한 600) 또는 GitHub Secrets에 둔다. 방식은 INF-11에서 정한다 `[결정 필요]`. → INF-11: Railway 서비스 변수에만 넣는다(`deploy_decision.md` 5절 · `railway_setup.md` 2절).

## 4. 작업 목록

| 번호 | 작업 | 담당 | 공동 | 리뷰 | 목표일 | 상태 | 근거 |
|---|---|---|---|---|---|---|---|
| INF-1 | 런타임 버전 고정: `.python-version` 3.12 · `.nvmrc` 22, 루트 README 4-1 · `ai/pyproject.toml` 기준 맞추기 | 문규남 | — | [미정] | 11/4 | 완료(11/3, #2): 두 파일 · README 4-1. `ai/pyproject.toml`의 `>=3.11`은 하한이라 그대로 둔다(uv는 `.python-version`의 3.12를 쓴다) | 2절 · 3-2 |
| INF-2 | 줄바꿈 · 인코딩: `.gitattributes`(기본 LF, `*.ps1`만 CRLF) · `.editorconfig`(UTF-8 · LF · 들여쓰기). 기존 CRLF 10개 재정규화는 따로 한 커밋으로 | 문규남 | DE | [미정] | 11/4 | 완료(11/3, #2): `.gitattributes` · `.editorconfig`(`*.ps1`은 BOM 있는 UTF-8 · CRLF), CRLF 10개 재정규화 커밋 따로 | 2절 |
| INF-3 | 의존성 잠금 · 표준 라이브러리: ai · backend `uv.lock`, frontend `package-lock.json`, 3-3 표 채우기 | 문규남 | FE · BE · AI | [미정] | 11/5 (골격과 함께) | 완료(11/7, #22): `ai/uv.lock` · `backend/uv.lock`(uv 0.13.3), CI는 `uv run --locked`(pyproject를 고치고 lock을 안 바꾸면 실패). frontend `package-lock.json`은 FE-1과 함께 main에 들어왔다. 3-3 표의 [제안] 칸은 FE · BE가 쓸 때 정한다 | 3-2 · 3-3 |
| INF-4 | 환경 변수: 3-4 규칙 적용, `.env.example` 보강(ai 변수는 `feature/AI-service`에서), 시작 시 설정 검사, Vite `VITE_` 이름 | 문규남 | FE · BE · AI | [미정] | 11/5 | 완료(11/7, #22): `.env.example`에 빠진 ai 변수 6개를 주석(`# NAME=기본값`)으로, 경계 검사가 주석 줄도 적은 것으로 보고 빠진 변수는 **막음**. 시작 시 설정 검사 `check_settings`(ai · backend, 틀리면 뜨지 않음). `VITE_` 이름은 FE가 frontend 변수를 만들 때(지금 frontend가 읽는 값은 `vite.config.ts`의 `BACKEND_PROXY_TARGET` 하나, `run_dev`가 넣는다) | 3-4 · `CONTRIBUTING.md` 2 |
| INF-5 | 린트 · 포맷: Python ruff(검사 + 포맷), frontend ESLint + Prettier. 포맷만 바꾼 커밋은 기능 커밋과 섞지 않는다 | 문규남 | — | [미정] | 11/5 | 일부(11/3, #2): 루트 `ruff.toml` — 실제 오류만(E9 · F63 · F7 · F82, ruff 0.17.3), main · `feature/AI-service` 모두 통과. 스타일 규칙 · `ruff format` · frontend ESLint + Prettier는 대기(팀 결정 · FE-1 골격 뒤). 11-27 코드 마감까지 켜지 않았다: `ruff.toml`은 실제 오류만, frontend에는 `lint` 스크립트가 없어 CI가 `npm run lint --if-present`로 건너뛴다(타입 검사는 `npm run build`의 `tsc`) | 3-3 |
| INF-6 | 빌드 · 테스트 명령 통일: ai · backend `uv run pytest`, frontend `npm run lint` · `npm run build` · `npm test`. 테스트는 엑사원 · 외부 네트워크 없이 돈다. 시간대는 코드에서 `Asia/Seoul`을 명시하고 테스트도 `TZ=Asia/Seoul`로 돌린다 | 문규남 | FE · BE · AI | [미정] | 11/6 | 일부(11/3): CI가 쓰는 명령으로 정했다 — ai · backend `python -m pytest`(uv로 `pyproject.toml` 설치), frontend `npm run lint` · `build` · `test`. CI는 TZ=Asia/Seoul. lock이 생기면(INF-3) `uv run pytest`로 바꾸고, 코드의 `ZoneInfo("Asia/Seoul")` 명시는 BE-1 · ai 코드에서. 완료(11/7, #22): CI가 `uv run --locked --extra dev python -m pytest`, backend `clock.py`가 `ZoneInfo` 명시 | 2절 시간대 |
| INF-7 | 로컬 동시 실행 `scripts/run_dev`: ai 8001 · backend 8000 · frontend를 한 번에 띄운다. Vite 프록시로 `/api`를 backend에 넘겨 외부에 여는 포트를 1개로 줄이고 CORS 설정을 없앤다. Windows에서도 돌게 Python으로 쓴다 | 문규남 | FE · BE | [미정] | 11/6 | 완료(11/7, #22): `scripts/run_dev.py`(표준 라이브러리). 밖에는 frontend 하나(`$PORT`가 있으면 0.0.0.0), ai · backend는 127.0.0.1 · 사용 중이면 빈 포트로 잇기, 루트 `.env` 읽기(셸 값 우선), `--no-llm` · `--only` · `--reload`, 하나가 죽으면 모두 끈다. FE-1 브랜치와 합쳐 화면 → `/api/health` → backend 200 확인. 보완(11-14, #72): 개발 서버 포트를 계정 번호로(#68). 보완(11-15, #178): 한국어 Windows cp949 출력 오류(#177) | `scripts/README.md` 예정 · 2절 포트 |
| INF-8 | 경계 · 비밀값 검사: `scripts/check_boundaries.py`(서비스 경로 Claude · 외부 LLM 호출 없음, `eval` import 없음, backend가 `ai` 코드를 import하지 않음, 코드가 읽는 변수가 `.env.example`에 있음) + 키 · 토큰 · `data/raw/` 커밋을 막는 pre-commit 훅 | 문규남 | AI | [미정] | 11/6 | 완료(11/3, #2): 막음 = 비밀값 · 금지 파일 · 계정 홈 경로 · IP · 서비스 경계, 경고 = 개인 메일 · `.env.example`에 없는 변수(INF-4 뒤 막음으로). 훅은 클론마다 `git config core.hooksPath .githooks` | D24 · D26 · D34 · D41 · 구조도 12절 19 |
| INF-9 | CI(GitHub Actions): PR → main에서 INF-5 · INF-6 · INF-8 실행, 폴더별 경로 필터. 엑사원을 부르는 테스트는 넣지 않는다 | 문규남 | — | [미정] | 11/12 (11/10 수업 후) | 완료(11/3, #2): `.github/workflows/ci.yml` — PR → main · main 푸시 · 수동 실행. 경계 · 비밀값 · 파이썬 검사 / ai / backend / frontend 4개 작업, 골격이 없는 폴더는 건너뛰고 통과. TZ=Asia/Seoul. PR마다 돈다(11-27 Actions 기록 확인) | 옛 `.github/workflows/README.md`(후보: 백엔드 · ai 테스트, 경계 검사) |
| INF-10 | 저장소 설정: main 보호(승인 1명 · CI 통과 필수 · 직접 푸시 금지), `CODEOWNERS`(폴더 → 파트 담당 리뷰 자동 요청). 저장소 관리자 권한 필요 | 문규남 | — | [미정] | 11/12 | 절차만(11/3, `infra/README.md` '저장소 설정'). 11/7 GitHub API로 확인: 저장소가 **비공개 + 소유자 무료 개인 계정**이라 main 규칙(rulesets · 브랜치 보호)은 "Upgrade to GitHub Pro or make this repository public"(403)으로 막혀 있다. `CODEOWNERS`도 같은 조건이다. 소유자에게 Pro(학생 인증이면 무료) 또는 공개 전환을 요청한다. 그전까지는 CI 결과를 보고 승인하는 사람 규칙으로 막는다. 11-27 확인: 저장소가 공개로 바뀌었고 main이 보호 브랜치다(GitHub API `protected: true`). 세부 규칙은 관리자 권한이 없어 확인 불가, `CODEOWNERS`는 만들지 않았다 | `work_rules.md` 2 · 6절 |
| INF-11 | 배포(`infra/`): 호스팅 · 도메인 · HTTPS(웹 푸시 필수), 프로세스 관리, backend 워커 1개 고정(APScheduler 중복 발송 방지), SQLite 백업, 비밀값 주입, `/health`로 기동 확인 | 문규남 | BE · FE | [미정] | 11/14 | 완료(11-25, #291 · #304 · #310 · #315): Railway로 정함(`deploy_decision.md`, #176). 서비스별 Dockerfile · `frontend/Caddyfile`(`/api` 프록시) · `railway_setup.md`(구성 · 변수 · 순서 · 확인 방법). 비밀값은 Railway 서비스 변수에 넣는다. 11-23: 헬스체크 `--host 0.0.0.0`(#304), 기본 인증 뺌, 운영 첫 시드(`demo_mails.json` 115통) · 메일 추출(`MEMORY_EXTRACT` · `REMINDER_SIGNALS`) 켬, 엑사원 키 2개(#310). 11-25: `AUTH_MODE=session` · `MAIL_SOURCE=outlook_graph` — 접속한 사람마다 자기 Outlook을 연결하고, 발표자는 `/api/session/demo`로 시연 사용자에 들어간다(#315, D58). 남은 일: 사용량 한도 · SQLite 백업(Railway 화면 설정, 레포에서 확인 불가 `[미확인]`) | BE-8 · FE-9와 합친다 `[제안]` · `deploy_decision.md` R2(프로세스 1개) · `detail.md` 위험 R3 · R4 |
| INF-12 | 로그 · 추적(로그 설정은 `infra/`): 요청 ID를 frontend → backend → ai로 넘긴다(`X-Request-ID`), 로그에 메일 본문을 남기지 않는다, 서비스별 `/health` | 문규남 | BE · AI | [미정] | 11/14 | 완료(11-12, #22 · #28): ai · backend `app/core/request_id.py` — `X-Request-ID`를 받거나(형식 검사) 새로 만들어 응답 헤더 · 로그 줄에 붙인다, 접근 로그는 메서드 · 경로 · 상태 · 시간만(쿼리 · 본문 · 헤더 없음), `/health` 접근은 DEBUG(11/7). backend → ai 전달은 BE-9 `ai_client`가 `request_id_headers()`를 넘긴다(#28, 11-12). frontend가 보내는 것은 선택(없으면 backend가 만든다). 남은 일: 로그 보관 기간(Railway) `[미확인]` | BE-6 · `ai/README.md` |

## 5. 다른 파트와의 접점

| 상대 파트 | 주는 것 | 받는 것 |
|---|---|---|
| 프론트엔드 | 버전 · 포맷 · Vite 프록시 · `VITE_` 규칙 (FE-1 골격에 반영) | `package.json` 스크립트 이름 |
| 백엔드 | 버전 · 포맷 · 설정 검사 · 워커 1개 규칙 (BE-1 골격에 반영) | 배포 요구 사항(BE-8과 합침) |
| AI | lock · 설정 검사 규칙 | `feature/AI-service`의 환경 변수 목록 · 테스트 명령 |
| 데이터 · 평가 | CRLF 재정규화 일정(INF-2) | `data/dummy/` 재생성 결과가 그대로인지 확인 |

## 6. 완료 기준 (입력 → 기대 결과)

- 새 PC에서 clone → `.env.example` 복사 → README 4절 명령 → 세 서비스가 뜨고 테스트가 통과한다(엑사원 없이). — 서버에서 확인(11/7, `run_dev.py --no-llm` + FE-1 브랜치), Windows PC 확인은 남음
- Windows에서 커밋한 `.sh` → 서버에서 바로 실행된다(LF). — 설정 완료(INF-2)
- PR을 연다 → CI가 린트 · 테스트 · 경계 검사를 돌리고, 실패하면 병합할 수 없다. — CI 완료(INF-9), '병합 막기'는 main 규칙(INF-10) 필요 → 11-27: main 보호 켜짐(세부 규칙 확인 불가)
- `frontend/`에 `anthropic`을 import한 PR → CI 실패(구조도 12절 19). — 검사 완료(INF-8 selfcheck에 같은 사례)
- 코드에 새 환경 변수를 넣고 `.env.example`에 안 넣은 PR → CI 실패. — 완료(INF-4, 11/7)
- `pyproject.toml`에 패키지를 넣고 `uv.lock`을 안 바꾼 PR → CI 실패. — 완료(INF-3, 11/7)
- 배포 서버에서 리마인더 1건 예약 → 1회만 발송된다(`deploy_decision.md` R2 · `detail.md` 위험 R3). — backend 볼륨으로 복제 1개는 플랫폼 규칙으로 지켜진다(INF-11). 배포 서버에서 1회 발송을 잰 기록은 `[미확인]`

## 7. 정할 것 `[결정 필요]`

| 질문 | 바뀌는 곳 | 정할 사람 |
|---|---|---|
| 작업 번호 접두어 `INF`를 쓸지 | `infra/` · `docs/README.md` | 팀 회의 → 11-27: 이슈 · PR 제목에 `INF`를 쓰고 있다 |
| 배포 위치 · 방식 · 비밀값 주입 방식 | INF-11 · 3-4 5번 | 인프라 · BE (11/10 수업 후) → 정함: Railway 서비스 3개 · Dockerfile · 비밀값은 Railway 서비스 변수(`deploy_decision.md`, INF-11 완료) |
| 시연 때 엑사원 서빙 위치 | INF-11 | 인프라 · AI (구조도 13절). 11/7: 최종 측정은 NVIDIA T4로 한다(`scripts/gpu/`, 마지막에 1회). 서빙 위치는 그 수치를 보고 정한다 → 정함: 엑사원 API(K-EXAONE 2.5, D51 · D53 · D58). 로컬 엑사원 · `scripts/gpu/` T4 경로는 쓰지 않는다(PR #321 · #322) |
| frontend 린터 · 테스트 도구 | 3-3 표 | FE → 11-27: 테스트는 Node 내장 `node --test`, 린터는 넣지 않았다 |
| ruff 스타일 규칙 · `ruff format`을 켤 시점 | `ruff.toml` · INF-5 | 팀 (한 번에 켜고 포맷 커밋은 따로). 11/7 main 기준 실측: 줄 길이 120 넘는 줄 817 · import 순서 19 · 버그 의심 B 12(FastAPI `Depends` 9건은 정상 패턴) · 안 쓰는 import 2, `ruff format`(120)이면 파이썬 67개 파일이 바뀐다. 11-27 코드 마감까지 켜지 않았다 |
| main 규칙 · `CODEOWNERS`를 쓰려면 저장소 소유 계정을 GitHub Pro로 올릴지(또는 공개로 바꿀지) · `CODEOWNERS` 아이디 | INF-10 | 저장소 관리자(dlwodns) · 팀. 11/7 API 확인: 비공개 + 무료 개인 계정이라 지금은 못 켠다 → 11-27: 공개로 바뀌었고 main 보호가 켜졌다. `CODEOWNERS`는 없다 |

## 8. 위험

- 11/7 P0 E2E까지 4일이다. INF-1 ~ INF-7은 골격 작업과 같이 해야 비용이 작다. 늦어지면 포맷 · 줄바꿈 변경이 기능 PR과 섞인다.
- CI를 무겁게 만들면 PR이 느려진다. 엑사원 호출 · 시간 시뮬레이션처럼 오래 걸리는 평가는 CI에 넣지 않고 `eval/`에서 따로 돌린다.
- 같은 설정 파일을 여러 브랜치에서 고치면 값이 갈라진다. 루트 설정 파일(`.gitattributes` · `.editorconfig` · `.python-version` · `.nvmrc` · CI)은 이 브랜치에서만 고치고 main에 PR로 올린다(`CONTRIBUTING.md` 2).
- 11-27(코드 마감): 첫 줄(11/7 일정) 위험은 지났다. 배포 뒤 남은 위험은 운영 쪽이다 — Railway 볼륨 백업 · 사용량 한도 `[미확인]`, 엑사원 하루 100회/키를 모든 사용자가 나눠 씀, 볼륨이 붙은 backend는 재배포 때 잠깐 끊김(`railway_setup.md` 6절, 시연 시간에는 배포하지 않는다).
