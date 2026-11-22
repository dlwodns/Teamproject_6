# Railway 배포 설정 (INF-11)

> 작성: 문규남 · 2026-11-22 · 결정 근거는 `deploy_decision.md`(R1~R10)
> 이 문서에는 비밀값을 적지 않는다. 키 · 해시 · 비밀번호는 Railway 서비스 변수(Variables)에만 넣는다.

## 1. 구성

```
사용자 ── HTTPS ──▶ web  (Caddy: 화면 + /api 프록시 + 기본 인증)   ← 공개 주소 1개
                      ▼ http://backend.railway.internal:8000
                    backend (FastAPI · 분류 작업자 · 리마인더, 복제 1, 볼륨 /data)
                      ▼ http://ai.railway.internal:8001
                    ai  (FastAPI, 공개 주소 없음) ── HTTPS ──▶ 엑사원 API
```

| 서비스 이름 | Root Directory | 빌드 | 공개 도메인 | 볼륨 | Watch Paths |
|---|---|---|---|---|---|
| `backend` | (비움 = 저장소 루트) | `backend/Dockerfile` (`RAILWAY_DOCKERFILE_PATH`) | 열지 않음 | `/data` | `/backend/**` · `/data/dummy/**` |
| `ai` | `/ai` | `ai/Dockerfile` (자동 감지) | 열지 않음 | — | `/ai/**` |
| `web` | `/frontend` | `frontend/Dockerfile` (자동 감지) | 연다 | — | `/frontend/**` |

- 서비스 이름이 내부 주소(`<이름>.railway.internal`)가 된다. 이름을 바꾸면 `BACKEND_URL` · `AI_SERVICE_URL`도 바꾼다.
- 처음 만든 `Teamproject_6` 서비스는 이름을 `backend`로 바꿔 쓴다.
- 리전: 싱가포르(`deploy_decision.md` 5절). 처음 만든 서비스가 US East로 잡혀 있었으니 세 서비스 모두 Settings → Region에서 확인한다.
- Start Command는 화면에 넣지 않는다. Dockerfile의 `CMD`가 정한다.

## 2. 서비스 변수

값이 `(비밀)`인 칸은 Railway 화면에만 넣는다.

**backend**

| 변수 | 값 | 이유 |
|---|---|---|
| `RAILWAY_DOCKERFILE_PATH` | `backend/Dockerfile` | 루트 컨텍스트로 빌드(3-1) |
| `PORT` | `8000` | 내부 주소 포트를 고정한다 |
| `APP_MODE` | `prod` | 개발용 엔드포인트를 닫고 `X-User-Id`를 요구한다 |
| `DATABASE_URL` | `sqlite:////data/demo.db` | 볼륨 경로(슬래시 4개). 이름이 `demo*.db`여야 시드가 들어간다(3-5) |
| `AI_SERVICE_URL` | `http://ai.railway.internal:8001` | 내부망은 `http`(Railway 문서) |
| `MAIL_SOURCE` | `dummy` | 공개 운영 중 실제 메일 금지(D53) |
| `DUMMY_MAIL_SOURCE` | `/data/demo.mails.json` | 시드 `--this-week`가 날짜를 옮긴 본문 사본(3-5) |
| `REMINDER_SCHEDULER` | `1` | 리마인더 1분 틱(R1) |
| `CLASSIFY_WORKER` | `0` 또는 `1` | 시드는 정답 라벨로 채우므로 꺼도 된다. 켜면 엑사원 하루 100회 한도를 쓴다 |
| `MEMORY_EXTRACT` | 비움 | 켜면 메일마다 ai 호출이 하나 더 늘어난다 |
| `DEMO_TOOLS` | 비움 | 기본 인증이 확인된 뒤에만 켠다(deploy_decision.md 5절) |

`TOKEN_ENCRYPTION_KEY` · `MS_GRAPH_*`는 `MAIL_SOURCE=outlook_graph`일 때만 필요하다(`backend/app/core/config.py`). dummy 운영에는 넣지 않는다.

**ai**

| 변수 | 값 | 이유 |
|---|---|---|
| `PORT` | `8001` | backend `AI_SERVICE_URL`과 맞춘다 |
| `LLM_BACKEND` | `exaone_api` | 코드 기본값과 같다. 명시해 둔다 |
| `EXAONE_API_KEY` | (비밀) | 30일 만료. 만료일을 따로 적어 둔다(deploy_decision.md 7절) |

**web**

| 변수 | 값 | 이유 |
|---|---|---|
| `BACKEND_URL` | `http://backend.railway.internal:8000` | Caddy 프록시 대상 |
| `BASIC_AUTH_USER` | (비밀) | 기본 인증 아이디 |
| `BASIC_AUTH_HASH` | (비밀) | `caddy hash-password`로 만든 bcrypt 해시. 평문 비밀번호는 넣지 않는다 |
| `VITE_API_MODE` | 넣지 않아도 됨 | Dockerfile `ARG` 기본값이 `http` |

## 3. 왜 이렇게 했나

1. **backend는 저장소 루트에서 빌드한다.** backend가 더미 메일을 `저장소 루트/data/dummy/*.json`으로 찾는다(`app/mail/body.py:18`, `app/dev/seed.py:36`, `Path(__file__).parents[3]`). Root Directory를 `/backend`로 두면 `data/`가 빌드에 올라가지 않는다. 파일을 backend 안으로 복사하면 같은 데이터가 두 벌이 되므로, 컨텍스트를 루트로 두고 Dockerfile 위치만 `RAILWAY_DOCKERFILE_PATH`로 알려 준다(Railway 문서 Dockerfiles · Variables).
2. **세 서비스 모두 Dockerfile을 쓴다(Railpack 자동 빌드를 쓰지 않는다).** 처음 시도는 루트 폴더에서 Railpack이 앱 종류를 못 찾아 실패했다(`No start command detected`). 하위 폴더로 바꿔도 Railpack 문서 기준으로 남는 문제가 있다.
   - FastAPI 자동 시작 명령이 `uvicorn main:app --host 0.0.0.0`으로 고정이다. 우리는 `app.main:app`이다.
   - uv로 설치한 `.venv`가 실행 때 PATH에 있는지 문서에 없다.
   - 루트의 `.python-version`이 하위 폴더 빌드에서 보이지 않으면 기본 Python 3.13.2로 빌드된다. Dockerfile은 `python3.12` 이미지로 고정해 이 문제가 없다(그래서 서비스 폴더마다 `.python-version`을 두지 않았다).
   - 정적 화면의 기본 Caddyfile 내용과 덮어쓰는 파일 이름이 문서에 정확히 없다.
   Dockerfile은 이미지 · 명령 · 경로가 파일에 다 보여 위 네 가지를 추측하지 않아도 된다. `infra/README.md`의 "Dockerfile은 각 서비스 폴더" 규칙도 따른다.
3. **`--host ::`.** Railway 내부망은 2025-10-16 이후 만든 환경에서 IPv4 · IPv6 둘 다, 그 전 환경은 IPv6만 쓴다(Railway 문서 How Private Networking Works). `0.0.0.0`은 IPv4만 받아 옛 환경에서 backend → ai가 끊긴다. `::`는 Linux에서 둘 다 받는다.
4. **web은 Caddy 하나로 화면 + 프록시 + 기본 인증.** backend에 CORS 설정이 없어 같은 출처의 `/api`로만 부른다(R6). `/api/health`만 backend `/health`로 바꿔 넘기는 규칙은 `frontend/vite.config.ts` 개발 프록시와 같다. 로그인이 생기기 전까지 사이트 전체를 기본 인증으로 막는다(멘토 11-14, deploy_decision.md 5절). HTTPS는 Railway가 앞에서 끝내므로 Caddy는 `$PORT`의 http만 받는다.
5. **DB 이름은 `demo.db`.** `APP_MODE=prod`에서는 더미가 자동으로 들어가지 않아 DB가 빈 채로 시작한다. 시드 명령은 실수로 다른 DB를 덮지 않게 `demo*.db`만 받는다(`seed.py:102`). 시연 날짜는 실제 오늘 기준이어야 하므로 `--this-week`로 넣고, 날짜를 옮긴 본문 사본을 `DUMMY_MAIL_SOURCE`로 읽게 한다.
6. **`VITE_API_MODE` 기본값을 Dockerfile에 둔다.** 이 값이 없으면 화면이 모의 데이터(`mock`)로 뜬다(`frontend/src/api/config.ts:15`). 빌드할 때 들어가는 값이라 변수 넣기를 잊으면 조용히 모의 화면이 나간다. 비밀값이 아니라 파일에 둬도 된다.
7. **볼륨은 backend에만.** 볼륨을 붙이면 복제를 켤 수 없어 프로세스 1개(`deploy_decision.md` R2, 리마인더 중복 방지)가 플랫폼 규칙으로 지켜진다. `infra/plan.md`의 "R3"은 기획 위험표(`docs/10_planning/detail.md` 15절 R3 스케줄러 중복)라 번호 체계가 다르다.
8. **개발용 패키지 · 로컬 파일을 이미지에 넣지 않는다.** `uv sync --no-dev`(uv Docker 가이드). 빌드에서 뺄 파일은 `.dockerignore`로 정한다. backend는 컨텍스트가 저장소 루트라 루트 `.dockerignore` 대신 `backend/Dockerfile.dockerignore`(Dockerfile 이름 + `.dockerignore`, BuildKit이 먼저 쓴다)에 `backend/` · `data/dummy/`만 남긴다 — 루트 `.env`가 이미지에 들어가지 않는다. ai는 `COPY . .`라 로컬 `.venv`가 이미지 `.venv`를 덮지 않게 뺀다.
9. **Caddy 응답 압축 · 캐시.** `encode zstd gzip`, 해시가 붙은 `/assets/*`는 1년 `immutable`, 나머지(`index.html`)는 `no-cache`라 재배포 직후 새 화면이 뜬다(Vite 빌드 파일 이름 규칙).
10. **`railway.json`(Config as Code)을 쓰지 않는다.** Railway 문서가 이 방식을 deprecated로 표시했고 기존 파일도 2026-12-01까지만 동작한다고 적었다. 그래서 Healthcheck · Watch Paths · `RAILWAY_DOCKERFILE_PATH`는 화면 설정과 이 문서 1 · 2 · 4절로 남긴다.

## 4. 순서

1. `ai` → `backend` → `web` 순서로 만든다(앞 서비스의 내부 주소를 뒤 서비스가 쓴다).
2. backend 볼륨: 서비스 → Volumes → Mount path `/data`.
3. backend · ai Settings → Healthcheck Path `/health`. web에는 걸지 않는다(기본 인증 때문에 401).
   - ai `/health`는 엑사원 API를 부르지 않는다(`ai/app/llm/client.py` `ExaoneApiClient.health`) — 하루 100회 한도를 쓰지 않는다. backend `/health`도 ai를 부르지 않는다.
   - Railway는 배포 시작 때만 확인하고, 뜬 뒤에는 다시 부르지 않는다(Railway 문서 Healthchecks). 호스트 이름 `healthcheck.railway.app`으로 부르는데 우리 앱은 호스트를 막지 않는다.
4. 첫 시드(backend 셸, `railway ssh`):
   ```
   cd /app/backend && python -m app.dev.seed load --db /data/demo.db --this-week
   ```
   출력의 `mail_source`가 `/data/demo.mails.json`인지 보고, backend를 재시작해 `DUMMY_MAIL_SOURCE`를 읽게 한다. 시드 전에는 사용자가 없어 모든 요청이 401이다(`app/core/user.py`) — 정상이다.
   - `--this-week`는 넣는 순간의 주로 날짜를 옮긴다. 주가 바뀌어 시연하면 `reset --db /data/demo.db --yes` 뒤 다시 `load ... --this-week`.
5. 사용량 한도(Usage limit)를 건다(deploy_decision.md 7절).
6. backend 볼륨 → Backups에서 자동 백업을 켜고, 시드 직후 수동 백업을 하나 만든다(Railway 문서 Volumes: 볼륨 서비스는 수동 · 자동 백업 지원). Hobby에서 되는지는 화면에서 확인한다 `[확인 필요]`.

## 5. 확인 방법

| 무엇 | 어떻게 | 기대 |
|---|---|---|
| backend 시작 | Deploy Logs | `Uvicorn running on http://[::]:8000` |
| ai 시작 | Deploy Logs | `Uvicorn running on http://[::]:8001` |
| 기본 인증 | 공개 주소를 비밀번호 없이 연다 | 401 |
| 프록시 · 내부망 | 로그인 뒤 `/api/health` | 200, `app_mode: prod`, `db` 정상 |
| backend → ai | 분류 · 명령 한 번 | ai Deploy Logs에 요청 줄 |
| 화면 모드 | 상단 바 | 모의 데이터 표시가 없음(`TopBar.tsx`) |
| 압축 · 캐시 | 브라우저 개발자 도구 Network | `/assets/*.js`에 `Content-Encoding: zstd` 또는 `gzip`, `Cache-Control: ... immutable`. `index.html`은 `no-cache` |

**첫 빌드 로그에서 볼 것** (머지 뒤 리뷰어와 같이 확인)

| 서비스 | 볼 줄 | 실패하면 |
|---|---|---|
| backend · ai | `uv sync --locked ... --no-dev`가 `Installed N packages`로 끝남 | `--locked` 실패 = `uv.lock`이 `pyproject.toml`과 안 맞음 → 로컬 `uv lock` 뒤 다시 커밋 |
| backend | `ZoneInfo('Asia/Seoul')` 검사 줄이 통과 | 시간대 파일 없음 → 이미지에 `tzdata` 설치 |
| backend | `COPY data/dummy/` 성공 | 빌드 컨텍스트가 루트가 아님 → Root Directory 비웠는지 · `RAILWAY_DOCKERFILE_PATH` 확인 |
| web | `npm ci`에 `EBADENGINE` 없음 | Node 버전 부족 → 7절 태그 고정 |
| web | Caddy 시작 로그에 설정 오류 없음 | `BASIC_AUTH_*` · `BACKEND_URL` 비었는지 확인 |

## 6. 알고 둔 한계

- web의 `BASIC_AUTH_USER` · `BASIC_AUTH_HASH`가 비어 있으면 Caddy가 설정 오류로 뜨지 않는다. 인증 없이 열리는 것보다 낫다(막힌 쪽으로 실패).
- 기본 인증은 Microsoft가 부르는 주소(`/api/graph/notify` 변경 알림, Outlook 로그인 뒤 돌아오는 주소)도 막는다. 지금은 `MAIL_SOURCE=dummy`라 쓰지 않는다. `outlook_graph`로 바꿀 때 그 경로만 인증에서 빼야 한다.
- backend · ai 시간대는 Dockerfile `TZ=Asia/Seoul`. CI와 같다(INF-6). 시간대 파일이 이미지에 없으면 빌드가 멈추도록 검사 한 줄을 넣었다.
- 볼륨이 붙은 backend는 재배포 때 잠깐 끊긴다. 시연 시간에는 배포하지 않는다.

## 7. 확인하지 못한 것

- Dockerfile 세 개는 로컬에 Docker가 없어 직접 빌드해 보지 못했다. 첫 Railway 빌드 로그가 첫 확인이다.
- `node:22-bookworm-slim`의 Node 버전이 `engines >=22.22.0`(`.npmrc` `engine-strict=true`)을 만족하는지는 빌드 때 확인한다. 안 되면 태그를 `node:22.22-bookworm-slim`처럼 고정한다.
- Root Directory를 비운 서비스의 빌드 컨텍스트가 저장소 루트라는 점은 Railway 문서에 문장으로 없다. 기본값이 저장소 루트라 그렇게 본다 `[추론]`.
- Railway가 `backend/Dockerfile.dockerignore`(Dockerfile별 ignore)를 쓰는지는 문서에 없다. GitHub에서 빌드하면 `.venv` · `node_modules` · `.env`는 애초에 저장소에 없어 결과는 같다. 로컬 `docker build` · `railway up` 대비다.
- `BASIC_AUTH_HASH`에 `$`가 들어가는데 Railway 변수 → Caddy `{$VAR}` 치환에서 그대로 전달되는지 첫 배포 때 401 → 로그인 성공으로 확인한다.

## 8. 근거

- Railway Dockerfiles · `RAILWAY_DOCKERFILE_PATH`: https://docs.railway.com/guides/dockerfiles · https://docs.railway.com/reference/variables
- Railway 내부망 IPv4 · IPv6: https://docs.railway.com/networking/private-networking/how-it-works
- Railpack Python(기본 3.13.2, FastAPI 시작 명령): https://railpack.com/languages/python
- Railpack Node(정적 화면 Caddy, 버전 결정 순서): https://railpack.com/languages/node
- uv Docker 이미지 · `uv sync --locked --no-install-project`: https://docs.astral.sh/uv/guides/integration/docker/
- Caddy `basic_auth` · `caddy hash-password`: https://caddyserver.com/docs/caddyfile/directives/basic_auth
- Railway Healthchecks(배포 시작 때만 확인, `healthcheck.railway.app`): https://docs.railway.com/reference/healthchecks
- Railway Volumes(복제 불가 · 백업 · 비 root 사용자 `RAILWAY_RUN_UID`): https://docs.railway.com/reference/volumes
- Railway Config as Code(deprecated, 2026-12-01까지): https://docs.railway.com/reference/config-as-code
- uv Docker 가이드(`--no-dev` · `.dockerignore`에 `.venv`): https://docs.astral.sh/uv/guides/integration/docker/
- Docker 빌드 컨텍스트 · Dockerfile별 `.dockerignore`: https://docs.docker.com/build/concepts/context/
- Caddy `encode` · `header`, 지시어 순서: https://caddyserver.com/docs/caddyfile/directives
