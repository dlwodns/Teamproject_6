# 배포 서비스 선정 보고서 (INF-11)

> 상태: 제안 · 작성: 문규남 · 결정: [팀 리뷰 후] · 리뷰: 이재운(승인, 11-15) · 갱신: 2026-11-15
> 결론: **Railway**에 세 서비스(web · backend · ai)를 한 프로젝트로 올린다. 2순위 Render(유료), 3순위 Fly.io.
> 가격 · 한도는 2026-11-14 각 회사 공식 문서 기준이다. 바뀔 수 있으므로 결제 전에 공식 가격표를 한 번 더 본다.

## 1. 결론 한 줄

CNE의 backend는 **늘 켜져 있어야 하고**(리마인더 08:30 · 분류 작업자), **SQLite 파일이 남아야 하고**, **프로세스가 하나여야 한다**. 이 세 가지를 무료 · 저가로 코드 수정 없이 만족하는 곳은 Railway다. Vercel · Netlify · Cloudflare는 서버리스라 backend를 고쳐 써야 하고, Render는 무료 요금제가 15분 뒤 잠들어 리마인더가 멈춘다.

### 제출 요약 (8주차 강의 형식)

- **계정 주인**: 문규남(인프라 담당) 계정 하나로 Railway 프로젝트를 만들고 팀원을 초대한다.
- **유료 이유**: Hobby 월 $5. 리마인더 · 분류 작업자가 늘 켜져 있어야 하고(R1) SQLite를 볼륨에 남겨야 해서(R3), 잠들거나 디스크가 없는 무료 요금제로는 안 된다.
- **비용 부담**: 운영팀 부담으로 요청한다(강의 기준: 유료면 운영팀 부담 + 이유를 보고서로).
- **접근 제한**: 로그인이 생기기 전까지 사이트 전체를 Caddy 기본 인증으로 막는다(멘토 "비밀번호만으로 충분", 11-14 회의). 지금 `X-User-Id`는 헤더라 바꿔 보낼 수 있다(보안 체크 3번).

| 서비스 | 용도 | 누구 계정 | 플랜 | 데이터가 가는 곳 |
|---|---|---|---|---|
| Railway | web · backend · ai 배포, SQLite 볼륨 | 문규남(인프라) | Hobby 월 $5 | 싱가포르 리전 컨테이너 · 볼륨(`/data`) |
| LG AI연구원 K-EXAONE API | 분류 · 문맥 기억 · 에이전트 명령 | AI 담당 | 무료(하루 100회) | api.exaone.ai — 개인정보를 가린 메일(BE-6) |
| GitHub | 저장소 · 자동 배포 연결 | 팀 저장소 | 무료 | 코드만(비밀값 없음) |
| Microsoft Graph(Outlook) | 실제 메일 연동(`MAIL_SOURCE=outlook_graph`일 때만) | BE 담당 Azure 앱 | 무료 | 공개 운영 중엔 쓰지 않음(`MAIL_SOURCE=dummy`, D53) |

## 2. 우리 프로젝트가 배포에 요구하는 것

코드 · 문서에서 확인한 조건이다.

| # | 조건 | 근거 |
|---|---|---|
| R1 | backend가 상시 실행된다. 앱 안의 분류 작업자(`worker.start()`)와 리마인더 스케줄러가 같은 프로세스에서 돈다 | `backend/app/main.py` lifespan · BE-12 |
| R2 | backend 프로세스는 **1개**. 2개면 리마인더가 두 번 나가고, 시연용 시간 이동(`clock.set_offset`)이 프로세스마다 갈라진다 | `infra/plan.md` INF-11 · R3 · BE-14 |
| R3 | SQLite 파일(`DATABASE_URL=sqlite:///...`)이 재배포 · 재시작 뒤에도 남는다. 설정 검사가 SQLite 주소만 받는다 | `backend/app/core/config.py` |
| R4 | 요청이 길다. backend → ai 분류는 타임아웃 130초 이상으로 정했다 | `docs/40_ai/decisions.md` (#21 리뷰) |
| R5 | HTTPS 고정 주소. 웹 푸시(PWA)와 Outlook OAuth redirect URI에 필요 | `docs/10_planning/detail.md` · BE-7 |
| R6 | 밖에 여는 주소는 하나. 화면의 `/api/...`를 backend로 넘겨 CORS를 쓰지 않는다(코드에 CORS 설정 없음). `/api/health`는 backend `/health`로 바꿔 넘긴다 | INF-7 · `frontend/vite.config.ts` |
| R7 | ai는 밖에 열 필요가 없다. backend만 부른다 | D34 |
| R8 | GPU가 필요 없다. 서비스 기본 모델은 엑사원 API(D51 · D52 · D53). 로컬 ollama는 옵션 | `docs/00_common/decisions.md` D52~D55 |
| R9 | 모노레포(`frontend/` · `backend/` · `ai/`), Python 3.12 + `uv.lock`, Node 22 + `package-lock.json` | INF-1 · INF-3 |
| R10 | 학생 팀 예산 · 11/27 코드 마감까지 2주. 설정이 적을수록 좋다 | 과정 일정 |

## 3. 후보 비교

| | Railway | Render | Fly.io | Vercel | Netlify | Cloudflare |
|---|---|---|---|---|---|---|
| 상시 실행(R1) | O (잠들지 않음) | 유료만 O. 무료는 15분 무요청 시 잠들고 깨는 데 약 1분 | O | X 함수가 요청마다 뜨고 꺼짐 | X | X (Workers) · Containers는 베타 |
| 프로세스 1개(R2) | O 볼륨을 붙이면 복제가 막혀 저절로 1개 | O | O | X 인스턴스 수 통제 불가 | X | X |
| 파일 저장(R3) | O 볼륨 $0.15/GB·월 | 유료만. 디스크 $0.25/GB·월, 무료에는 못 붙임 | O 볼륨 | X `/tmp`만, 인스턴스마다 따로 · 임시 | X | X 디스크 임시. D1 · R2로 바꿔 써야 함 |
| 긴 요청(R4) | O | O | O | Hobby 최대 300초 | 동기 함수 30~60초 | 제한 있음 |
| 스케줄러 | 앱 안 스케줄러 그대로 | 그대로(유료) | 그대로 | Hobby cron 하루 1번 | 백그라운드 함수 15분 | Cron Triggers로 재설계 |
| 내부망(R7) | O `*.railway.internal` | O (유료) | O | — | — | — |
| 모노레포 · uv(R9) | 서비스마다 루트 폴더 지정 | 서비스마다 루트 폴더 지정 | 서비스마다 Dockerfile · `fly.toml` | frontend만 자연스러움 | frontend만 | frontend만 |
| 예상 비용(R10) | Hobby $5/월(사용량 $5 포함), 우리 규모는 그 안팎 `[추정]` | 서비스 2개 유료 → 월 $14 이상 `[확인 필요]` | 무료 요금제 없음, 소형 머신 사용량 과금 | frontend만이면 무료 | frontend만이면 무료 | frontend만이면 무료 |
| backend 코드 수정 | 없음 | 없음 | 없음 | DB · 스케줄러 · 작업자 재설계 | 같음 | 같음 + D1 전환 |

### 후보별 판단

- **Vercel · Netlify · Cloudflare — 탈락.** 셋 다 정적 화면(frontend)에는 훌륭하다. 그러나 backend는 요청마다 떴다 꺼지는 함수로 돈다. 앱 안 작업자 · 스케줄러(R1)가 살아 있을 곳이 없고, 파일이 남지 않으며(R3), 인스턴스 수를 1로 묶을 수 없다(R2). 쓰려면 SQLite → 외부 DB, 스케줄러 → 플랫폼 cron(Vercel Hobby는 하루 1번)으로 바꿔야 하는데, 마감 2주 전에 되던 리마인더 · 분류 흐름을 다시 짜는 일이다.
- **frontend만 이쪽에 두는 혼합안 — 하지 않는다.** 주소가 둘로 갈라져 CORS나 재작성 규칙이 생기고(R6), 관리할 플랫폼이 둘이 된다. 얻는 것은 CDN뿐인데 사용자가 팀장 1명 · 시연용이라 이득이 작다.
- **Render — 2순위.** 조건은 모두 맞지만 유료여야 한다. 무료 요금제는 잠들어 08:30 리마인더 · 분류 작업자가 멈추고, 디스크도 못 붙인다. ai만 무료로 두면 깨어나는 1분 동안 분류 요청이 늦어진다. backend · ai 둘 다 유료라 Railway보다 비싸다.
- **Fly.io — 3순위.** 머신 + 볼륨으로 조건은 맞는다. 다만 무료 요금제가 없고, 서비스마다 Dockerfile · `fly.toml` · CLI 배포를 직접 관리해야 해 2주 안에 팀이 익히기엔 손이 많이 간다.
- **Railway — 선택.** 아래 4절.

## 4. Railway를 고른 이유

1. **backend를 고치지 않는다.** 컨테이너가 계속 떠 있으므로 lifespan의 작업자 · 스케줄러가 지금처럼 돈다(R1).
2. **프로세스 1개가 플랫폼 규칙으로 보장된다.** 볼륨을 붙인 서비스는 복제(replica)를 켤 수 없다. SQLite 볼륨을 붙이는 순간 "backend 1개"(R2 · 중복 발송 방지)가 저절로 지켜진다.
3. **SQLite가 남는다.** 볼륨을 `/data`에 붙이고 `DATABASE_URL=sqlite:////data/cne.db`로 둔다(R3). Hobby 볼륨 한도 5GB, 값은 GB당 월 $0.15.
4. **ai를 밖에 열지 않는다.** ai는 공개 주소 없이 `ai.railway.internal`로만 받는다(R7). 내부 통신은 `http`를 쓴다.
5. **HTTPS 주소가 바로 생긴다.** `*.up.railway.app` 주소에 HTTPS가 붙어 웹 푸시 · OAuth redirect URI(R5)에 쓴다. 나중에 도메인을 사도 붙일 수 있다.
6. **싸다.** Hobby는 월 $5에 사용량 $5가 포함된다. RAM GB당 월 $10 · vCPU당 월 $20을 분 단위로 매긴다. 세 서비스가 대부분 놀고 있는 시연 규모면 $5 안팎이다 `[추정: 실제 사용량은 첫 주 청구 화면으로 확인]`.
7. **모노레포 그대로.** 서비스마다 루트 폴더 · Dockerfile과 감시 경로(Watch Paths)를 지정해, `frontend/`만 바뀐 PR이 backend를 다시 배포하지 않게 한다. 감시 경로는 루트 폴더와 상관없이 저장소 루트 기준(`/backend/**`)으로 쓴다(Railway 문서 Build Configuration).

## 5. 배포 구성안

```
사용자 ── HTTPS ──▶ web (Caddy: frontend 빌드 결과 + 리버스 프록시)   ← 공개 주소 1개
                      │ /api/health → backend /health
                      │ /api/*      → backend
                      ▼ http (railway.internal)
                    backend (FastAPI · 작업자 · 스케줄러, 복제 1, 볼륨 /data)
                      │ http (railway.internal)
                      ▼
                    ai (FastAPI, 공개 주소 없음) ── HTTPS ──▶ 엑사원 API
```

| 서비스 | 루트 폴더 (Root Directory) | 빌드 · 실행 | 공개 | 볼륨 | 주요 변수 |
|---|---|---|---|---|---|
| web | `frontend` | `frontend/Dockerfile`: `npm ci && npm run build` → Caddy(`frontend/Caddyfile`)가 `dist/` 제공 · `/api` 프록시 · 기본 인증 | O | — | `BACKEND_URL` · `BASIC_AUTH_USER` · `BASIC_AUTH_HASH` |
| backend | (비움 = 저장소 루트) | `backend/Dockerfile`(`RAILWAY_DOCKERFILE_PATH`로 지정). `CMD`가 `uvicorn app.main:app --host :: --port $PORT`(워커 옵션 없이 1개) | X | `/data` | `APP_MODE=prod` · `DATABASE_URL` · `AI_SERVICE_URL=http://ai.railway.internal:8001` |
| ai | `ai` | `ai/Dockerfile`. `CMD`가 `uvicorn app.main:app --host :: --port $PORT` | X | — | `EXAONE_API_KEY` · `LLM_BACKEND=exaone_api`(D52) |

- **11/22 바꿈: Railpack + Start Command → 서비스별 Dockerfile.** 첫 빌드가 Railpack에서 실패했고(`No start command detected`), backend는 더미 메일(`data/dummy`) 때문에 저장소 루트에서 빌드해야 한다. 이유 · 변수 전체 · 설정 순서는 `railway_setup.md`.
- **Railway 화면에 Start Command를 넣지 않는다.** Dockerfile로 빌드하는 서비스에서 Start Command는 이미지 명령을 덮어쓰고, 셸 없이(exec form) 실행돼 `$PORT` · `cd ... &&`가 풀리지 않는다(Railway 문서 Start Command). backend 이미지는 이미 `/app/backend`에서 시작하므로 `cd backend`도 실패한다.
- Graph 값 · `TOKEN_ENCRYPTION_KEY`는 `MAIL_SOURCE=outlook_graph`일 때만 넣는다. 시연은 `dummy`다.

- 리전: 한국 리전이 없어 **싱가포르(`asia-southeast1-eqsg3a`)** 로 둔다. 응답은 분류 · 모델 호출 시간이 훨씬 길어 지연 차이는 작다 `[추정]`.
- 비밀값: Railway 서비스 변수(Variables)에 넣는다. 레포 · GitHub Secrets에 따로 두지 않는다. `infra/plan.md` 3-4 5번 `[결정 필요]`의 답으로 제안한다.
- 헬스 체크: backend · ai `/health`, 새 배포가 이 응답을 내야 바뀐다. web은 기본 인증(401) 때문에 걸지 않는다.
- 사이트 전체를 Caddy 기본 인증 뒤에 둔다(로그인이 생기기 전까지). 시연용 엔드포인트(`DEMO_TOOLS=true`, BE-14)는 기본 인증이 붙기 전에는 켜지 않는다 — 켜면 누구나 모든 사용자의 서비스 시각을 바꾸고 알림을 만든다(#93 리뷰).
- Caddy를 쓰는 것은 `infra/README.md`에 이미 적어 둔 리버스 프록시 계획과 같다.

## 6. 배포 전에 끝나야 하는 것

| 할 일 | 이유 | 담당 |
|---|---|---|
| ~~ai 엑사원 API 모드 구현(D52)~~ | **완료** — #64로 들어와 main 기본값이 `exaone_api`다(`ai/app/core/config.py`) | AI |
| ~~운영 모드 `X-User-Id` 헤더~~ | **완료** — #63으로 모든 요청에 붙는다(`frontend/src/api/httpClient.ts`) | FE |
| Alembic 도입 여부 | 배포 뒤 테이블을 바꾸면 볼륨의 데이터 이관이 필요하다 | BE |
| Outlook redirect URI 등록 | Railway 주소가 정해진 뒤 Azure 앱 등록에 넣는다 | BE |
| Railway 결제 계정 · 팀원 초대 방식 | 계정은 문규남, 비용은 운영팀 부담 요청(제출 요약). 팀원을 프로젝트에 넣는 방식 `[확인 필요]` | 인프라 · 팀 |
| 첫 배포 확인 | 작성자가 아닌 팀원이 작은 커밋을 push해 자동 배포가 되는지 본다(8주차 강의) | 전원 |

## 7. 위험과 대응

| 위험 | 대응 |
|---|---|
| 볼륨이 붙은 서비스는 재배포 때 잠깐 끊긴다 `[확인 필요: 공식 문서 문구]` | 시연 시간에는 배포하지 않는다. 리마인더는 재시작 복구(BE-12)로 놓치지 않는다 |
| SQLite 백업 | 볼륨 백업 기능 사용 가능 여부 `[확인 필요]`. 안 되면 하루 한 번 `sqlite3 .backup` 파일을 받아 둔다(INF-11 남은 일) |
| 사용량이 $5를 넘음 | 첫 주 청구 화면 확인. Railway에 사용량 한도(usage limit)를 걸어 둔다 |
| 엑사원 API 장애 · 한도 초과(시연 당일) | D52대로 설정 하나로 로컬로 바꾼다. 7.8B를 Railway에 올리면 RAM 약 6GB · 월 $60 수준이라 하지 않고, 기존 PC 터널(`scripts/exaone-pc.sh`) · T4 측정 경로를 쓴다 |
| 실제 메일이 API로 나감 | D53 범위대로 실제 메일은 로컬 모드만. 공개 운영 중엔 `MAIL_SOURCE=dummy` 유지 |
| 엑사원 API 키 30일 만료(#64 리뷰) | 한 달 운영 중에 만료된다. 만료일을 적어 두고 1주 전에 새 키로 바꾼다. 끊겨도 규칙 결과로 동작한다 |
| 규칙으로 안 잡히는 에이전트 명령을 연달아 보내 하루 100회 소진 | backend에서 사용자별 모델 호출 횟수를 제한한다(보안 체크 9번) |
| Railway 자체 장애 | 같은 구성이 Render 유료(2순위)로 그대로 옮겨진다. 컨테이너 · 볼륨 · 내부망 개념이 같다 |

## 8. 근거

- Railway 가격 · Hobby: https://docs.railway.com/pricing/plans · https://railway.com/pricing.md
- Railway 볼륨(서비스당 1개, 볼륨이 있으면 복제 불가): https://docs.railway.com/volumes/reference
- Railway 내부망: https://docs.railway.com/networking/private-networking
- Railway 리전: https://docs.railway.com/deployments/regions
- Render 무료 요금제 잠듦 · 디스크: https://render.com/docs/faq · https://render.com/pricing
- Vercel 함수 시간 한도 · Hobby cron: https://vercel.com/docs/functions/configuring-functions/duration · https://vercel.com/docs/limits
- Vercel FastAPI: https://vercel.com/docs/frameworks/backend/fastapi
- Netlify 백그라운드 함수: https://docs.netlify.com/build/functions/background-functions/
- Cloudflare Containers 디스크(임시): https://developers.cloudflare.com/containers/faq/
