# 인프라 작업 현황

> 갱신: 2026-11-07 · 작성: 문규남 · 브랜치: `feature/INF`(main 병합), `feature/INF-p0-finish`(INF-3 · 4 · 7 · 12, main PR 전)
> 한 일 · 쓰는 법 · 확인 결과를 기능별로 모은다. 할 일 목록 · 원칙은 `plan.md`, 폴더 규칙 · 파일 위치는 `README.md`.

## 한눈에 보기

| 기능 | 상태 | 팀원이 할 일 | 파일 | 작업 |
|---|---|---|---|---|
| [버전 고정](#1-버전-고정-inf-1) | **완료** | Node 작업 전 `nvm use` (Python은 uv가 자동) | `.python-version` · `.nvmrc` | INF-1 |
| [줄바꿈 · 인코딩](#2-줄바꿈--인코딩-inf-2) | **완료** | 편집기에 EditorConfig 확장 | `.gitattributes` · `.editorconfig` | INF-2 |
| [비밀값 · 경계 검사](#3-비밀값--경계-검사-inf-8) | **완료** | 클론마다 `git config core.hooksPath .githooks` 한 번 | `scripts/check_boundaries.py` · `.githooks/pre-commit` | INF-8 |
| [서버 내부 정보 정리](#4-서버-내부-정보-정리) | **완료** | — | 아래 표 | INF-8 |
| [파이썬 검사(ruff)](#5-파이썬-검사-ruff-inf-5) | 일부 | — (CI가 돌린다) | `ruff.toml` | INF-5 |
| [CI](#6-ci-inf-9) | **완료** · GitHub 첫 실행 전 | PR을 열면 자동 | `.github/workflows/ci.yml` | INF-9 |
| [테스트 명령](#7-테스트-명령-inf-6) | **완료** | 아래 명령 | — | INF-6 |
| [저장소 설정](#8-저장소-설정-inf-10) | 막힘(요금제) | 저장소 소유자: Pro 또는 공개 결정 | `README.md` '저장소 설정' | INF-10 |
| [패키지 lock](#11-패키지-lock-inf-3) | **완료** | 패키지를 넣으면 `uv lock`도 같이 커밋 | `ai/uv.lock` · `backend/uv.lock` | INF-3 |
| [환경 변수 · 설정 검사](#12-환경-변수--설정-검사-inf-4) | **완료** | 코드에서 새 변수를 읽으면 `.env.example`에도 | `.env.example` · `app/core/config.py` | INF-4 |
| [동시 실행](#13-동시-실행-inf-7) | **완료** | `python scripts/run_dev.py` | `scripts/run_dev.py` | INF-7 |
| [요청 ID · 접근 로그](#14-요청-id--접근-로그-inf-12) | 일부 | BE-9 `ai_client`에서 `request_id_headers()` | `app/core/request_id.py` | INF-12 |
| [아직 안 한 것](#9-아직-안-한-것) | 대기 | — | — | INF-10 · 11 · 엑사원 서빙 |

### 처음 받으면

```bash
cp .env.example .env                      # 값은 각자 채운다. .env는 올리지 않는다
git config core.hooksPath .githooks       # 커밋 전 비밀값 · 경계 검사 켜기(클론마다 한 번)
nvm use                                   # frontend 작업 때. Node 22(.nvmrc)
python scripts/run_dev.py --no-llm        # 세 서비스 한 번에(엑사원 없이)
```

## 1. 버전 고정 (INF-1)

| 대상 | 고정한 곳 | 값 | 근거 |
|---|---|---|---|
| Python | 루트 `.python-version` | 3.12 | 개발 서버 3.12.3. uv가 이 파일을 읽는다 |
| Node | 루트 `.nvmrc` | 22 | 개발 서버 v22.23.2. `nvm use`가 이 파일을 읽는다 |
| 엑사원 · ollama | `scripts/exaone-pc.env` (이미 있음, AI-D9) | digest `099a498b9cbf…` · 0.34.0 | 평가 수치와 같은 조건 |
| 문서 | 루트 README 4-1 준비물 | 위와 같은 값 | 문서마다 3.10 · 3.11 · 20으로 달랐다 |

- 원칙: 버전 고정값은 **커밋하는 파일**에, `.env`에는 사람마다 다른 값 · 비밀값만 둔다(`.env`는 올리지 않아 팀원마다 값이 갈라진다, `plan.md` 3-1).
- 그대로 둔 것: `ai/pyproject.toml`의 `>=3.11`(하한이라 3.12와 어긋나지 않는다), 채점기 · 더미 생성기의 '3.10 이상'(표준 라이브러리만 쓴다).
- 남은 것: 패키지 lock(INF-3), frontend `package.json`의 `engines`(FE-1).
- 커밋: `b0665bb`

## 2. 줄바꿈 · 인코딩 (INF-2)

| 파일 | 설정 | 이유 |
|---|---|---|
| `.gitattributes` | 저장소는 LF, `*.ps1` · `*.bat` · `*.cmd`만 작업 폴더 CRLF, 이미지 · 문서 · 모델 파일은 바이너리 | Windows에서 만든 `.sh`가 CRLF로 올라오면 서버 bash에서 실패한다 |
| `.editorconfig` | UTF-8 · LF · 끝 줄바꿈 · 들여쓰기 2칸(`.py` 4칸), `.ps1`은 BOM 있는 UTF-8 · CRLF | Windows PowerShell 5.1은 BOM이 없으면 한글을 깨뜨린다 |

- CRLF로 들어가 있던 10개를 LF로 바꿨다: `data/dummy/dummy_mails.json` · `mail_list.md`, `eval/bench/exaone_20261024/` 8개.
- 확인: 줄바꿈만 바뀌고 내용은 같다(CR을 뺀 sha256 일치, `dummy_mails.json`은 JSON 비교 일치, `build.py`로 다시 만든 결과와 바이트 단위로 같음).
- 커밋: `ac486e6`(설정) · `71f0575`(재정규화, 기능 커밋과 섞지 않으려고 따로)

## 3. 비밀값 · 경계 검사 (INF-8)

`scripts/check_boundaries.py`(표준 라이브러리만)가 검사하고, `.githooks/pre-commit`이 커밋할 때마다 부른다. CI도 같은 검사를 다시 돌린다.

| 구분 | 검사 | 근거 |
|---|---|---|
| **막음** | API 키 · 토큰 · 개인키 모양의 글자(Anthropic · OpenRouter · OpenAI · GitHub · AWS · Slack · Google) | 7절 보안 |
| **막음** | 설정 파일(`.env*` · `.sh` · `.ps1` · `.yml` · `.toml` 등)에 값이 채워진 비밀 변수(`*_SECRET` · `*SECRET_KEY` · `*_API_KEY` · `*TOKEN` 등) | `.env.example`은 빈칸이어야 한다 |
| **막음** | 올리면 안 되는 파일: `.env` · 키 · 인증서 · SSH 개인키 · `data/raw/` 원본 · 실제 메일함 캡처 | D24 |
| **막음** | 서버 내부 정보: 실제 계정 홈 경로(서버 · macOS · Windows) · IP 주소(루프백 · 문서용 대역 제외) | 4절 |
| **막음** | 서비스 경계: `frontend` · `backend` · `ai`의 외부 LLM SDK · 주소 · 키, `backend` · `ai`의 `eval` import, `backend`의 `ai` 코드 import, `ai`의 DB 접근 | D26 · D34 · D41 |
| 경고 | 개인 메일 주소(gmail · naver 등). 예시 주소는 `example.com` | — |
| **막음** | 서비스 코드가 읽는 환경 변수 중 `.env.example`에 없는 것(`# NAME=` 주석도 적은 것으로 본다, `--all`만) | INF-4 (11/7 경고 → 막음) |

```bash
python scripts/check_boundaries.py --staged      # 커밋 전 훅이 부르는 것(스테이징된 파일만)
python scripts/check_boundaries.py --all         # 전체 파일 + 환경 변수 목록(CI)
python scripts/check_boundaries.py --selfcheck   # 검사 규칙 점검 → selfcheck OK
```

- 찾은 값은 앞 4글자만 보인다(CI 로그에 남지 않게).
- 막혔을 때: 진짜 비밀값이면 빼서 `.env`로 옮긴다. **이미 push했으면 지워도 기록에 남으므로 그 키를 폐기하고 새로 발급한다.** 일부러 넣은 가짜 값이면 그 줄 끝에 `boundary-ok`를 적는다. `git commit --no-verify`로 건너뛴 커밋도 PR CI가 다시 잡는다.
- 확인: `--selfcheck` 통과. 시험 저장소에서 가짜 키 파일 · `.env` 강제 추가 커밋이 모두 막혔다. `c4b14e3` 이후 이 브랜치 커밋은 모두 훅을 거쳤다.

| 브랜치 (11/3 검사) | 결과 |
|---|---|
| `feature/INF` | 통과 · 경고 0 |
| `feature/INF` + `feature/AI-service` 합친 상태 | 통과(파일 192개) · 경고 10(ai 환경 변수, INF-4) |
| main · `feature/AI` · `feature/PL` 단독 | `data/dummy/README.md` 개인 PC 경로 1건 → `feature/INF`가 병합되면 없어진다 |

- 커밋: `c4b14e3`

## 4. 서버 내부 정보 정리

비밀번호 · 키는 원래 없었다. 검사로 찾은 계정 이름 · 경로를 지웠다. 비밀값이 아니라 기록(이력)을 다시 쓰지 않고 새 커밋으로 고쳤다.

| 위치 | 있던 것 | 바꾼 것 | 커밋 |
|---|---|---|---|
| `infra/plan.md` 2절 | 개발 서버 계정 이름 · 할당 포트 번호 | "각자 `echo $PORT`로 확인" | `9d57662` |
| `data/dummy/README.md` 3절 | 개인 PC 경로(Windows 사용자 폴더) | 레포 기준 `cd data/dummy` | `c4b14e3` |
| `scripts/pc/exaone-tunnel.ps1` | `-RemoteSock` 기본값에 서버 계정 홈 경로 | 비워 두고 `exaone-pc.env`의 `OLLAMA_UDS`(`$HOME/run/exaone/ollama.sock`)를 서버 홈으로 풀어 쓴다. 서버의 `exaone-pc.sh`와 같은 파일을 읽어 경로가 어긋나지 않는다 | `feature/AI-service` `342bdc5` |
| 명령 세트 v2 D-106 | 예시 주소 gmail.com | example.com (규칙만 120/120 · 위험한 오탐 0 그대로) | `feature/AI-service` `342bdc5` |

- 남겨 둔 것: `.ps1`의 SSH 별칭 기본값(사용자 PC의 ssh 설정에서만 뜻이 있다), `feature/AI` 문서 2줄의 계정 이름(그 브랜치 작업 때 고친다), ai 설정의 로컬 전용 포트 기본값(127.0.0.1이라 밖에서 못 붙는다).
- 저장소는 비공개다(로그인 없이 GitHub API 조회 404). 11/26 제출로 공개하기 전에 `--all`을 한 번 더 돌린다.
- `.ps1`은 이 서버에 PowerShell이 없어 실행해 보지 못했다 → PC에서 한 번 켜서 터널이 붙는지 확인한다 `[확인 필요]`.

## 5. 파이썬 검사 ruff (INF-5)

| 항목 | 내용 |
|---|---|
| 설정 | 루트 `ruff.toml`: 실제 오류만 막는다 — E9(문법) · F63(잘못된 비교) · F7(잘못된 문장) · F82(정의 안 된 이름). ruff 0.17.3 |
| 확인 | main 기준 · `feature/AI-service` 모두 통과. 정의 안 된 이름을 넣으면 F821로 막힌다 |
| 왜 좁게 | ruff 기본 규칙으로는 `feature/AI-service`에서 103건(대부분 스타일)이 나온다. 스타일 규칙 · `ruff format`은 팀이 정한 뒤 한 번에 켠다(포맷만 바꾼 커밋은 기능 커밋과 섞지 않는다) |
| 실행 | `uvx ruff@0.17.3 check .` |
| 남은 것 | 스타일 규칙 · 포맷 시점 결정, frontend ESLint + Prettier(FE-1 뒤) |

- 커밋: `50e7962`

## 6. CI (INF-9)

`.github/workflows/ci.yml`. **PR → main**, main 푸시, 수동 실행(Actions 탭, main에 올라간 뒤)에 돈다.

| 작업 이름 (GitHub에 보이는 이름) | 하는 일 | 건너뛰는 조건 |
|---|---|---|
| 경계 · 비밀값 · 파이썬 검사 | `check_boundaries.py --selfcheck` · `--all`, ruff, 채점기 selfcheck | — |
| ai 테스트 | `ai/uv.lock` 그대로 설치(uv `--locked`) → pytest. 엑사원 없이 가짜 모델 | `ai/pyproject.toml` 없음 |
| backend 테스트 | `backend/uv.lock` 그대로 설치 → pytest | `backend/pyproject.toml` 없음 |
| frontend 검사 · 빌드 | `npm ci` → lint · build · test | FE-1 골격 전 |

- 고정: Python · Node 버전은 `.python-version` · `.nvmrc`를 읽는다. ruff 0.17.3 · uv 0.13.3, 액션 `checkout@v5` · `setup-python@v6` · `setup-node@v5`. 시간대 `TZ=Asia/Seoul`(러너 기본은 UTC).
- 넣지 않은 것: 엑사원을 부르는 테스트 · 평가(PC 의존 · 느림) — `eval/`에서 따로 돌린다.
- 확인: GitHub에서는 아직 돌지 않았다(이 브랜치로 PR을 열면 첫 실행). 대신 `feature/INF` + `feature/AI-service`를 합친 상태에서 같은 단계를 로컬로 돌렸다 — 경계 검사 통과, ruff 통과, 채점기 selfcheck, ai 238개 통과(새 가상환경에 설치), backend · frontend 건너뜀.
- 지킬 것: backend `pyproject.toml`도 ai처럼 `dev` extra에 pytest를 둔다. frontend는 `package-lock.json`을 커밋해야 `npm ci`가 돈다.
- 커밋: `635b33a`

## 7. 테스트 명령 (INF-6)

CI와 같은 명령이다.

| 파트 | 명령 |
|---|---|
| 공통 | `python scripts/check_boundaries.py --all` · `uvx ruff@0.17.3 check .` · `python data/dummy/eval.py --selfcheck` |
| ai | `cd ai && uv run --locked --extra dev python -m pytest` |
| backend | `cd backend && uv run --locked --extra dev python -m pytest` |
| frontend | `cd frontend && npm ci && npm run lint && npm run build && npm run test` (FE-1 뒤) |

- 11/7: lock(INF-3)이 생겨 `uv run --locked`로 바꿨다. 시간대는 backend `app/core/clock.py`가 `ZoneInfo("Asia/Seoul")`로 적는다(BE-1). ai는 시각을 backend 요청의 `now`로 받아 스스로 현재 시각을 읽지 않는다.
- 커밋: `6fc8553`

## 8. 저장소 설정 (INF-10)

GitHub 화면에서 관리자만 바꿀 수 있어 커밋으로는 못 한다. 절차는 `README.md` '저장소 설정'.

| 항목 | 상태 |
|---|---|
| main 규칙(PR 필수 · 승인 1명 · CI 통과 필수 · 강제 푸시 금지) | **지금은 못 켠다(11/7 확인).** 비공개 + 소유자 무료 개인 계정 → API 403 "Upgrade to GitHub Pro or make this repository public". 소유자가 Pro(학생 인증이면 무료)로 올리거나 공개로 바꾸면 `README.md` 절차대로 켠다 |
| `CODEOWNERS`(폴더마다 리뷰어 자동 지정) | 비공개 저장소는 Pro 이상에서만 동작. 그다음 파트 담당 GitHub 아이디가 필요하다 `[결정 필요]` |
| GitHub 비밀값 검사(push protection) | 비공개 저장소는 유료 `[확인 필요]` → 커밋 전 훅 + CI로 대신 막는다 |

## 9. 아직 안 한 것

| 작업 | 무엇이 있어야 하나 | 언제 |
|---|---|---|
| INF-10 main 보호 · `CODEOWNERS` | 소유 계정 GitHub Pro 또는 저장소 공개(소유자 dlwodns 결정) · 파트 담당 GitHub 아이디 | 11/12 |
| INF-11 배포(도메인 · HTTPS · 실행 설정 · 워커 1개 · SQLite 백업 · 비밀값 주입 · 로그 보관) | 배포 위치 · 방식 결정(11/10 수업), 리마인더 스케줄러(BE) | 11/14 |
| INF-12 남은 것 | backend → ai 전달은 BE-9 `ai_client`가 `request_id_headers()`를 쓰면 끝 | BE-9와 함께 |
| 엑사원 서빙 위치 | NVIDIA T4로 최종 측정(11/7 결정, `scripts/gpu/`, `OLLAMA_NUM_PARALLEL` 1 · 2 · 4). 수치를 보고 정한다 | 마지막에 1회, AI와 |
| frontend `package-lock.json` · ESLint | FE-1 병합(lock은 FE-1 브랜치에 있다) · FE 린터 결정 | FE-1 병합 때 |

## 10. 브랜치 · 커밋

| 브랜치 | 커밋 | 내용 |
|---|---|---|
| `feature/INF` | `915de1c` · `3804073` · `ade971e` | 할 일 정리, `infra/` 폴더, 문서를 `infra/`로 모음 |
| `feature/INF` | `9d57662` | 계정 이름 · 포트 번호 정리 |
| `feature/INF` | `b0665bb` | INF-1 버전 고정 |
| `feature/INF` | `ac486e6` · `71f0575` | INF-2 줄바꿈 설정 · 재정규화 |
| `feature/INF` | `c4b14e3` | INF-8 비밀값 · 경계 검사 · 커밋 전 훅 |
| `feature/INF` | `50e7962` | INF-5 ruff |
| `feature/INF` | `635b33a` | INF-9 CI · INF-10 절차 |
| `feature/INF` | `6fc8553` | INF-6 테스트 명령 · 진행 상태 |
| `feature/AI-service` | `342bdc5` | 터널 스크립트 소켓 경로 · 예시 주소 · `scripts/README` 맞춤 |
| `feature/INF-p0-finish` | `03e4832` | INF-3 패키지 lock · CI `--locked` |
| `feature/INF-p0-finish` | `e789f7d` | INF-4 `.env.example` 보강 · 빠진 변수 막음 · 시작 시 설정 검사 |
| `feature/INF-p0-finish` | `514490d` | INF-12 요청 ID · 접근 로그 |
| `feature/INF-p0-finish` | `31cec98` | INF-7 `scripts/run_dev.py` |

- 병합 시험(11/3): `feature/INF`를 main · `feature/AI-service` · `feature/AI` · `feature/PL`과 각각 합쳐도 충돌이 없다. 두 브랜치가 같이 고친 `scripts/README.md`는 내용을 똑같이 맞춰 두었다. 병합 순서는 상관없다.

## 11. 패키지 lock (INF-3)

| 항목 | 내용 |
|---|---|
| 파일 | `ai/uv.lock` · `backend/uv.lock` (uv 0.13.3, `requires-python >=3.11`로 풀었다) |
| 설치 | `uv sync --locked --extra dev` → 각 폴더 `.venv`에 lock 그대로 |
| CI | `uv run --locked --extra dev python -m pytest`. `pyproject.toml`을 고치고 lock을 안 바꾸면 실패한다 |
| 패키지를 넣을 때 | `pyproject.toml` 고침 → 그 폴더에서 `uv lock` → 둘을 한 커밋에 |
| frontend | `package-lock.json`은 FE-1 브랜치에 이미 있다. CI는 `npm ci`라 병합되면 바로 쓴다 |
| 확인(11/7) | 새 가상환경에 lock 그대로 설치 → ai 253 · backend 36 통과(엑사원 없이) |
| 커밋 | `03e4832` |

## 12. 환경 변수 · 설정 검사 (INF-4)

| 항목 | 내용 |
|---|---|
| `.env.example` | 빠졌던 ai 변수 6개(`LLAMACPP_BASE_URL` · `LLM_TIMEOUT_S` · `OLLAMA_KEEP_ALIVE` · `ROUTER_THRESHOLD` · `LLM_ENABLED` · `CLASSIFY_PROMPT`)를 '# NAME=기본값' 주석으로 넣었다. 주석이면 코드 기본값을 쓴다 |
| 경계 검사 | 주석 줄(`# NAME=`)도 적은 것으로 본다. 코드가 읽는데 `.env.example`에 없는 변수는 **막음**(전에는 경고) |
| 시작 시 검사 | ai · backend `app/core/config.py`의 `check_settings` → 틀리면 `RuntimeError`로 뜨지 않는다. 메시지에 비밀값은 넣지 않는다 |
| backend가 보는 것 | `APP_MODE`(dev · prod) · `MAIL_SOURCE`(dummy · outlook_graph · imap) · `DATABASE_URL`(SQLite) · `AI_SERVICE_URL`(http), `MAIL_SOURCE=outlook_graph`면 `MS_GRAPH_CLIENT_ID` · `MS_GRAPH_CLIENT_SECRET` · `TOKEN_ENCRYPTION_KEY` |
| ai가 보는 것 | `LLM_BACKEND`(ollama · llamacpp, D41) · `LLM_TIMEOUT_S` > 0 · `ROUTER_THRESHOLD` 0~1 · 숫자 형식 · 주소 형식 |
| 늘릴 곳 | 웹 푸시(VAPID) · 개인정보(BE-6) 등 기능이 들어오면 그 기능이 쓰는 값을 같은 함수에 더한다. `ROUTER_MODE`(AI-18 브랜치)도 그 브랜치가 병합될 때 |
| 커밋 | `e789f7d` |

## 13. 동시 실행 (INF-7)

```bash
python scripts/run_dev.py                    # ai · backend · frontend
python scripts/run_dev.py --no-llm           # 엑사원 없이
python scripts/run_dev.py --only ai,backend  # 고른 것만
scripts/exaone-pc.sh run python scripts/run_dev.py   # 개발 서버 + PC 엑사원 터널
```

| 항목 | 내용 |
|---|---|
| 밖에 여는 포트 | frontend 하나. 화면의 `/api/...`는 Vite 프록시가 backend로(CORS 없음). `$PORT`가 있으면(개발 서버) 그 포트 · `0.0.0.0`, 없으면 5173 · `127.0.0.1` |
| 안쪽 포트 | ai 8001 · backend 8000, `127.0.0.1`만. **개발 서버는 여러 계정이 같이 써서 8000 · 5173이 이미 잡혀 있었다(11/7)** → 사용 중이면 빈 포트를 골라 `AI_SERVICE_URL` · `BACKEND_PROXY_TARGET`으로 잇는다 |
| `.env` | 루트 `.env`를 읽어 세 서비스에 넘긴다. 셸에 이미 있는 값이 이긴다(`exaone-pc.sh run`이 넣은 터널 값) |
| 끄기 | Ctrl+C로 모두. 하나가 죽으면(설정 오류 등) 나머지도 끄고 그 종료 코드로 끝난다 |
| 확인(11/7, 개발 서버) | FE-1 브랜치와 합친 임시 폴더에서 `--no-llm`: 화면 200, 화면 포트의 `/api/health` → backend 200 · 보낸 `X-Request-ID` 그대로, 8000 사용 중이라 backend는 빈 포트로 열림. `APP_MODE=staging` → backend가 설정 오류로 멈추고 ai도 꺼짐(종료 코드 3). 끈 뒤 남은 프로세스 없음 |
| 못 한 것 | Windows PC에서 실행(`taskkill`로 끄는 길) `[확인 필요]` |
| 커밋 | `31cec98` |

## 14. 요청 ID · 접근 로그 (INF-12)

| 항목 | 내용 |
|---|---|
| 파일 | ai · backend 각각 `app/core/request_id.py`(backend는 ai 코드를 import하지 않으므로 따로, D34) |
| 요청 ID | 들어온 `X-Request-ID`가 `[A-Za-z0-9._-]` 1~64자면 그대로, 아니면 새로 만든다(32자). 응답 헤더에 돌려준다 |
| 로그 | `app.*` 로거의 모든 줄에 `[요청 ID]`. 접근 로그는 `메서드 경로 상태 시간`만 — 쿼리 · 본문 · 헤더는 남기지 않는다. `/health`는 DEBUG |
| backend → ai | `request_id_headers()`를 BE-9 `ai_client`의 `headers=`로 넘긴다(아직 `ai_client` 없음) |
| frontend → backend | 보내면 그 값을, 안 보내면 backend가 만든다. 화면이 보낼지는 FE가 정한다 |
| 로그 보관 · 회전 | 배포(INF-11) 때 `infra/` |
| 커밋 | `514490d` |
