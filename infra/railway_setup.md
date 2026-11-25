# Railway 배포 설정 (INF-11)

> 작성: 문규남 · 2026-11-22 · 결정 근거는 `deploy_decision.md`(R1~R10)
> 이 문서에는 비밀값을 적지 않는다. 키 · 해시 · 비밀번호는 Railway 서비스 변수(Variables)에만 넣는다.

## 1. 구성

```
사용자 ── HTTPS ──▶ web  (Caddy: 화면 + /api 프록시)   ← 공개 주소 1개
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
- Start Command는 화면에 넣지 않는다(비워 둔다). Dockerfile의 `CMD`가 정한다. 넣으면 이미지 명령을 덮어쓰고 셸 없이 실행돼 `$PORT` · `cd ... &&`가 풀리지 않는다(Railway 문서 Start Command). backend는 이미 `/app/backend`에서 시작해 `cd backend`도 실패한다.
- Watch Paths는 Root Directory와 상관없이 저장소 루트 기준(`/backend/**`)으로 쓴다(Railway 문서 Build Configuration).

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
| `MAIL_SOURCE` | `outlook_graph` | 11-25 변경: 각자 설정 → 메일에서 자기 Outlook을 연결한다. 실제 메일이 엑사원 API로 가므로 D53(실제 메일은 로컬만)과 어긋난다 — 결정 기록 필요 |
| `AUTH_MODE` | `session` | 브라우저마다 사용자 하나(비밀번호 없음, `backend/app/api/session.py`). `X-User-Id`를 바꿔 남의 메일을 보는 길을 막는다 |
| `MS_GRAPH_TENANT` | `common` | 개인 Outlook.com + 회사 · 학교 계정 |
| `MS_GRAPH_REDIRECT_URI` | `https://<web 주소>/api/accounts/outlook/callback` | Entra 앱 등록의 리디렉션 URI와 같게 |
| `GRAPH_NOTIFY_URL` | `https://<web 주소>` | Graph 변경 알림. 비우면 1분 폴링 |
| `MS_GRAPH_CLIENT_ID` · `MS_GRAPH_CLIENT_SECRET` · `TOKEN_ENCRYPTION_KEY` | (비밀) | Entra 앱 등록 · Fernet 키 |
| `DEMO_SHARE_USER_ID` | 시드 사용자 번호(보통 `1`) | 발표자는 `/api/session/demo`를 한 번 열면 더미 시연 데이터로 들어간다. 이 사용자에는 실제 메일을 연결하지 않는다 |
| `DUMMY_MAIL_SOURCE` | `/data/demo.mails.json` | 시드 `--this-week`가 날짜를 옮긴 본문 사본(3-5) |
| `REMINDER_SCHEDULER` | `1` | 리마인더 1분 틱(R1) |
| `CLASSIFY_WORKER` | `0` 또는 `1` | 시드는 정답 라벨로 채우므로 꺼도 된다. 켜면 엑사원 하루 100회 한도를 쓴다 |
| `MEMORY_EXTRACT` | `1` | 문맥 기억(연락처의 맡은 일 · 소속). 분류 뒤 메일마다 ai 호출이 하나 더 늘어난다(11-23 켬) |
| `REMINDER_SIGNALS` | `1` | 리마인더 AI 신호(기한 바뀜 · 상대 약속 · 끝난 것 같아요). 받은 메일은 분류 뒤, 보낸 메일은 스케줄러 틱에서 ai를 한 번 더 부른다(11-23 켬) |
| `DEMO_TOOLS` | 비움 | 기본 인증을 뺐으므로 켜지 않는다. 켜면 누구나 서비스 시각을 바꾸고 알림을 만든다(deploy_decision.md 5절) |

`TOKEN_ENCRYPTION_KEY` · `MS_GRAPH_*`는 `MAIL_SOURCE=outlook_graph`일 때만 필요하다(`backend/app/core/config.py`). 없으면 backend가 뜨지 않는다(11-25 배포 실패 원인).

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
| `VITE_API_MODE` | 넣지 않아도 됨 | Dockerfile `ARG` 기본값이 `http` |

## 3. 왜 이렇게 했나

1. **backend는 저장소 루트에서 빌드한다.** backend가 더미 메일을 `저장소 루트/data/dummy/*.json`으로 찾는다(`app/mail/body.py:18`, `app/dev/seed.py:36`, `Path(__file__).parents[3]`). Root Directory를 `/backend`로 두면 `data/`가 빌드에 올라가지 않는다. 파일을 backend 안으로 복사하면 같은 데이터가 두 벌이 되므로, 컨텍스트를 루트로 두고 Dockerfile 위치만 `RAILWAY_DOCKERFILE_PATH`로 알려 준다(Railway 문서 Dockerfiles · Variables).
2. **세 서비스 모두 Dockerfile을 쓴다(Railpack 자동 빌드를 쓰지 않는다).** 처음 시도는 루트 폴더에서 Railpack이 앱 종류를 못 찾아 실패했다(`No start command detected`). 하위 폴더로 바꿔도 Railpack 문서 기준으로 남는 문제가 있다.
   - FastAPI 자동 시작 명령이 `uvicorn main:app --host 0.0.0.0`으로 고정이다. 우리는 `app.main:app`이다.
   - uv로 설치한 `.venv`가 실행 때 PATH에 있는지 문서에 없다.
   - 루트의 `.python-version`이 하위 폴더 빌드에서 보이지 않으면 기본 Python 3.13.2로 빌드된다. Dockerfile은 `python3.12` 이미지로 고정해 이 문제가 없다(그래서 서비스 폴더마다 `.python-version`을 두지 않았다).
   - 정적 화면의 기본 Caddyfile 내용과 덮어쓰는 파일 이름이 문서에 정확히 없다.
   Dockerfile은 이미지 · 명령 · 경로가 파일에 다 보여 위 네 가지를 추측하지 않아도 된다. `infra/README.md`의 "Dockerfile은 각 서비스 폴더" 규칙도 따른다.
3. **`--host 0.0.0.0`.** Railway 헬스체크는 IPv4로 들어오는 것으로 보인다(Railway 문서에 명시 없음, 11/22 증상으로 추론). uvicorn은 asyncio `loop.create_server`로 여는데, asyncio가 IPv6 소켓에 `IPV6_V6ONLY`를 켜므로(CPython `asyncio/base_events.py`) `--host ::`는 IPv6만 받는다. 그래서 `::`로 열면 앱은 뜨지만 헬스체크 요청이 로그에 한 줄도 없이 `service unavailable`로 실패한다(11/22 첫 배포). 내부망은 2025-10-16 이후 만든 환경에서 IPv4 · IPv6 둘 다라(Railway 문서 How Private Networking Works) `0.0.0.0`으로 backend → ai도 닿는다. 그 전에 만든 옛 환경(IPv6만)에 올리면 이 가정이 깨진다.
4. **web은 Caddy 하나로 화면 + 프록시.** backend에 CORS 설정이 없어 같은 출처의 `/api`로만 부른다(R6). `/api/health`만 backend `/health`로 바꿔 넘기는 규칙은 `frontend/vite.config.ts` 개발 프록시와 같다. 기본 인증은 11-23에 뺐다(시연용 · 주소는 팀에만 공유, deploy_decision.md 5절). HTTPS는 Railway가 앞에서 끝내므로 Caddy는 `$PORT`의 http만 받는다.
5. **DB 이름은 `demo.db`.** `APP_MODE=prod`에서는 더미가 자동으로 들어가지 않아 DB가 빈 채로 시작한다. 시드 명령은 실수로 다른 DB를 덮지 않게 `demo*.db`만 받는다(`seed.py:102`). 시연 날짜는 실제 오늘 기준이어야 하므로 `--this-week`로 넣고, 날짜를 옮긴 본문 사본을 `DUMMY_MAIL_SOURCE`로 읽게 한다.
6. **`VITE_API_MODE` 기본값을 Dockerfile에 둔다.** 이 값이 없으면 화면이 모의 데이터(`mock`)로 뜬다(`frontend/src/api/config.ts:15`). 빌드할 때 들어가는 값이라 변수 넣기를 잊으면 조용히 모의 화면이 나간다. 비밀값이 아니라 파일에 둬도 된다.
7. **볼륨은 backend에만.** 볼륨을 붙이면 복제를 켤 수 없어 프로세스 1개(`deploy_decision.md` R2, 리마인더 중복 방지)가 플랫폼 규칙으로 지켜진다. `infra/plan.md`의 "R3"은 기획 위험표(`docs/10_planning/detail.md` 15절 R3 스케줄러 중복)라 번호 체계가 다르다.
8. **개발용 패키지 · 로컬 파일을 이미지에 넣지 않는다.** `uv sync --no-dev`(uv Docker 가이드). 빌드에서 뺄 파일은 `.dockerignore`로 정한다. backend는 컨텍스트가 저장소 루트라 루트 `.dockerignore` 대신 `backend/Dockerfile.dockerignore`(Dockerfile 이름 + `.dockerignore`, BuildKit이 먼저 쓴다)에 `backend/` · `data/dummy/`만 남긴다 — 루트 `.env`가 이미지에 들어가지 않는다. ai는 `COPY . .`라 로컬 `.venv`가 이미지 `.venv`를 덮지 않게 뺀다.
9. **Caddy 응답 압축 · 캐시.** `encode zstd gzip`, 해시가 붙은 `/assets/*`는 1년 `immutable`, 나머지(`index.html`)는 `no-cache`라 재배포 직후 새 화면이 뜬다(Vite 빌드 파일 이름 규칙).
10. **`railway.json`(Config as Code)을 쓰지 않는다.** Railway 문서가 이 방식을 deprecated로 표시했고 기존 파일도 2026-12-01까지만 동작한다고 적었다. 그래서 Healthcheck · Watch Paths · `RAILWAY_DOCKERFILE_PATH`는 화면 설정과 이 문서 1 · 2 · 4절로 남긴다.

## 4. 순서

0. 이 PR(#291)이 main에 들어간 뒤에 한다. main에 Dockerfile이 없으면 Railpack으로 빌드돼 처음처럼 실패한다.
1. 프로젝트 이름: 맨 위 프로젝트 이름 → `06팀-CNE`. 프로젝트는 팀당 1개다.
2. 서비스 3개: 지금 있는 서비스 1개 + 오른쪽 위 `+ Add` → GitHub Repo → `Teamproject_6`를 2번 더. 저장소 연결은 GitHub 권한이 있는 팀원 계정으로 한다.
3. 서비스마다 Settings(1절 표 · 2절 변수):

   | | backend (지금 있는 서비스) | ai | web |
   |---|---|---|---|
   | 이름 | `backend` | `ai` | `web` |
   | Source → Root Directory | 비움 | `ai` | `frontend` |
   | Variables에 먼저 | `RAILWAY_DOCKERFILE_PATH=backend/Dockerfile` | — | — |
   | Deploy → Start Command | **비움** | **비움** | **비움** |
   | Deploy → Healthcheck Path | `/health` | `/health` | 비움 |
   | Source → Watch Paths | `/backend/**` · `/data/dummy/**` | `/ai/**` | `/frontend/**` |
   | Networking | 도메인 만들지 않음 | 도메인 만들지 않음 | Generate Domain |
   | Region | 싱가포르 | 싱가포르 | 싱가포르 |
   | Volume | 서비스 오른쪽 클릭 → Attach Volume → `/data` | — | — |

   세 서비스 모두 Source → Auto deploy를 켠다. 변수는 2절 표대로 넣고, API 키는 Railway에만 넣는다(GitHub · 단톡방에 올리지 않는다).
4. 화면의 Diagnose · Agent 버튼은 유료 AI 기능이라 누르지 않는다. 막히면 그 서비스의 Deployments → Build Logs를 캡처해 공유한다(5절 "첫 빌드 로그에서 볼 것").
5. 만드는 순서는 상관없지만, 확인은 `ai` → `backend` → `web` 순서로 한다(앞 서비스의 내부 주소를 뒤 서비스가 쓴다).
   - 헬스체크: web에는 걸지 않는다(정적 화면이라 Caddy가 뜨면 열린다). ai `/health`는 엑사원 API를 부르지 않는다(`ai/app/llm/client.py` `ExaoneApiClient.health`) — 하루 100회 한도를 쓰지 않는다. backend `/health`도 ai를 부르지 않는다.
   - 헬스체크는 배포 시작 때만 확인하고, 뜬 뒤에는 다시 부르지 않는다(Railway 문서 Healthchecks). 호스트 이름 `healthcheck.railway.app`으로 부르는데 우리 앱은 호스트를 막지 않는다.
6. 첫 시드(backend 셸, `railway ssh`):
   ```
   cd /app/backend && python -m app.dev.seed load --db /data/demo.db --this-week --source /app/data/dummy/demo_mails.json
   ```
   출력의 `added_mails`가 115(받은 100 + 보낸 15), `mail_source`가 `/data/demo.mails.json`인지 본다. 본문은 사본 파일의 수정 시각이 바뀌면 다시 읽으므로(`app/mail/body.py` `_dummy_index`) 재시작은 필요 없다. 시드 전에는 사용자가 없어 모든 요청이 401이다(`app/core/user.py`) — 정상이다.
   - `--source`를 빼면 기본값 `dummy_mails.json`(받은 100통, 보낸 메일 없음)이 들어가 답 없음 · 내 약속 · 응답 대기가 빈다(`docs/10_planning/agent_scenarios.md`). 11-23 첫 시드가 이렇게 들어가 다시 넣었다.
   - `--this-week`는 넣는 순간의 주로 날짜를 옮기고, DB에 메일이 있으면 거절한다. 주가 바뀌어 시연하면 `reset --db /data/demo.db --yes` 뒤 다시 `load ... --this-week --source ...`.
   - 시드는 정답 라벨만 넣어 요약 · 문맥 기억 · AI 신호가 비어 있다. 채우려면 시드 뒤 받은 메일을 분류 대기열에, 보낸 메일을 신호 대기열에 넣는다(`CLASSIFY_WORKER` · `MEMORY_EXTRACT` · `REMINDER_SIGNALS`=1). 정답 업무는 덮지 않는다(`jobs/classify.py` `_save`). 엑사원을 메일당 2~3회 불러 115통에 200~300회이므로 키를 여러 개 넣고 한다(`EXAONE_API_KEY=키1,키2,…`).
     ```
     cd /app/backend && REMINDER_SIGNALS=1 python -c "from sqlalchemy import select; from app.core.db import SessionLocal; from app.models import Mail; from app.jobs import classify, signals; db=SessionLocal(); [classify.enqueue(db, m) if m.direction == 'received' else signals.enqueue(db, m) for m in db.scalars(select(Mail))]; db.commit()"
     ```
   - `railway ssh`는 SSH 키가 필요하다(`ssh-keygen -t ed25519` → `railway ssh keys add`). 키에 암호가 있으면 CLI가 `No SSH keys found`로 멈춘다. PowerShell에서 `-N '""'`는 `""` 두 글자를 암호로 넣으니 `-N ''`로 만든다.
7. 사용량 한도(Usage limit)를 건다(deploy_decision.md 7절).
8. backend 볼륨 → Backups에서 자동 백업을 켜고, 시드 직후 수동 백업을 하나 만든다(Railway 문서 Volumes: 볼륨 서비스는 수동 · 자동 백업 지원). Hobby에서 되는지는 화면에서 확인한다 `[확인 필요]`.

## 5. 확인 방법

| 무엇 | 어떻게 | 기대 |
|---|---|---|
| backend 시작 | Deploy Logs | `Uvicorn running on http://0.0.0.0:8000` |
| ai 시작 | Deploy Logs | `Uvicorn running on http://0.0.0.0:8001` |
| 화면 열기 | 공개 주소를 연다 | 비밀번호 창 없이 대시보드 |
| 프록시 · 내부망 | `/api/health` | 200, `app_mode: prod`, `db` 정상 |
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
| web | Caddy 시작 로그에 설정 오류 없음 | `BACKEND_URL` 비었는지 확인 |

## 6. 알고 둔 한계

- 기본 인증이 없어 주소를 아는 사람은 누구나 화면과 `/api`를 쓴다. `AUTH_MODE=session`이라 사람마다 자기 사용자 · 자기 메일만 보이지만, 계정 로그인이 아니라 브라우저 쿠키다 — 쿠키를 지우거나 다른 브라우저 · 기기로 들어오면 새 사용자라 메일을 다시 연결한다. [요약] · 명령 · 분류는 엑사원 호출 한도(하루 100회/키)를 모두가 나눠 쓴다.
- backend · ai 시간대는 Dockerfile `TZ=Asia/Seoul`. CI와 같다(INF-6). 시간대 파일이 이미지에 없으면 빌드가 멈추도록 검사 한 줄을 넣었다.
- 볼륨이 붙은 backend는 재배포 때 잠깐 끊긴다. 시연 시간에는 배포하지 않는다.

## 7. 확인하지 못한 것

- Dockerfile 세 개는 로컬에 Docker가 없어 직접 빌드해 보지 못했다. 첫 Railway 빌드 로그가 첫 확인이다.
- `node:22-bookworm-slim`의 Node 버전이 `engines >=22.22.0`(`.npmrc` `engine-strict=true`)을 만족하는지는 빌드 때 확인한다. 안 되면 태그를 `node:22.22-bookworm-slim`처럼 고정한다.
- Root Directory를 비운 서비스의 빌드 컨텍스트가 저장소 루트라는 점은 Railway 문서에 문장으로 없다. 기본값이 저장소 루트라 그렇게 본다 `[추론]`.
- Railway가 `backend/Dockerfile.dockerignore`(Dockerfile별 ignore)를 쓰는지는 문서에 없다. GitHub에서 빌드하면 `.venv` · `node_modules` · `.env`는 애초에 저장소에 없어 결과는 같다. 로컬 `docker build` · `railway up` 대비다.

## 8. 근거

- Railway Dockerfiles · `RAILWAY_DOCKERFILE_PATH`: https://docs.railway.com/guides/dockerfiles · https://docs.railway.com/reference/variables
- Railway 내부망 IPv4 · IPv6: https://docs.railway.com/networking/private-networking/how-it-works
- Railpack Python(기본 3.13.2, FastAPI 시작 명령): https://railpack.com/languages/python
- Railpack Node(정적 화면 Caddy, 버전 결정 순서): https://railpack.com/languages/node
- uv Docker 이미지 · `uv sync --locked --no-install-project`: https://docs.astral.sh/uv/guides/integration/docker/
- Caddy `basic_auth` · `caddy hash-password`: https://caddyserver.com/docs/caddyfile/directives/basic_auth
- Railway Start Command(Dockerfile 서비스는 exec form, 변수는 `/bin/sh -c`로 감싸야 풀림): https://docs.railway.com/guides/start-command
- Railway Watch Paths(Root Directory가 있어도 `/` 기준): https://docs.railway.com/guides/build-configuration
- Railway Healthchecks(배포 시작 때만 확인, `healthcheck.railway.app`): https://docs.railway.com/reference/healthchecks
- Railway Volumes(복제 불가 · 백업 · 비 root 사용자 `RAILWAY_RUN_UID`): https://docs.railway.com/reference/volumes
- Railway Config as Code(deprecated, 2026-12-01까지): https://docs.railway.com/reference/config-as-code
- uv Docker 가이드(`--no-dev` · `.dockerignore`에 `.venv`): https://docs.astral.sh/uv/guides/integration/docker/
- Docker 빌드 컨텍스트 · Dockerfile별 `.dockerignore`: https://docs.docker.com/build/concepts/context/
- Caddy `encode` · `header`, 지시어 순서: https://caddyserver.com/docs/caddyfile/directives
