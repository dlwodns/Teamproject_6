<div align="center">

# CNE

### Catch & End — 메일 속 할 일을 놓치지 않고 끝까지

하루 100~200통의 업무 메일에서 할 일을 뽑아 기한 · 유형별로 정리하고,<br>
끝낼 때까지 챙겨 주는 업무 메일 비서. 사내 모델 엑사원(EXAONE)만 쓴다.

[문서](docs/README.md) · [구조도](docs/00_common/architecture.md) · [평가 결과](docs/50_data_eval/scores.md) · [배포](infra/railway_setup.md) · [기여 규칙](CONTRIBUTING.md)

<img src="docs/assets/screenshots/dashboard.png" alt="CNE 대시보드 — 이번 주 받은 업무 60건을 긴급 · 즐겨찾기 · 회신 · 요청 · 검토 · 기타 칸으로 나눠 보여 준다" width="900">

</div>

> 6조 실리콘밸리 발사대 · 2026 천안형 글로벌 인재육성사업 AX 액션러닝 · LG CNS 기업 과제 04
> 화면의 메일 · 사람 · 회사는 모두 가상 LG CNS 조직의 더미 데이터다.

## 왜 만들었나

메일을 하나씩 열어 확인하는 방식으로는 하루 100~200통 속 할 일을 놓친다. CNE는 이 **누락을 막는 것**을 첫 번째 목표로 둔다.

| 대상 | 성공 기준 |
|---|---|
| 하루 업무 메일 100~200통을 받는 LG CNS 팀장 | 할 일 메일 누락 0건 · 리마인더 중복 · 누락 0건 · 서비스 경로에서 엑사원 밖 LLM 호출 0건 |

## 주요 기능

- **업무 추출** — 메일마다 할 일 · 기한 · 본인 지목 · 우선순위를 뽑고 회신 · 요청 · 검토 · 공지 · 기타로 나눈다. 판단은 엑사원이, 날짜 계산 · 우선순위 보정은 코드가 한다.
- **대시보드** — 받은 날 기준 업무 수(처리 · 미처리), 응답 대기, 긴급(기한 지남 · ASAP · 오늘 마감) · 즐겨찾기 · 업무 유형별 칸.
- **메일** — Outlook과 같은 3단 화면, 여러 계정 통합, 메일마다 업무 카드 · 근거 문장 · 요약 · 번역, 상태 버튼(완료 · 나중에 · 제외 · 되돌리기).
- **리마인더 · 브리핑** — 완료 · 제외할 때까지 추적한다. 기한 임박 · 지남, 응답 대기, 약속, 끝난 것 같은 업무를 알리고 아침 · 퇴근 · 주간 브리핑을 만든다. 같은 알림은 두 번 보내지 않는다.
- **캐치봇(에이전트)** — 말이나 글로 지시하면 등록된 행동(T01~T20) 안에서 처리한다. 1건 변경은 바로 실행 + 되돌리기, 여러 건 · 설정 · 발송은 먼저 확인한다.
- **캘린더** — 업무 기한 · 메일 속 회의 · 미룬 업무와 연결한 Outlook 일정을 월 단위로 본다.
- **Outlook 연결** — Microsoft Graph로 받은편지함 · 보낸편지함 · 일정을 가져온다. 배포 주소에서는 브라우저마다 자기 Outlook을 연결한다(D58).

<table>
  <tr>
    <td width="50%"><img src="docs/assets/screenshots/mail.png" alt="메일 3단 화면 — 왼쪽 메일함 · 분류, 가운데 메일 목록과 기한 라벨, 오른쪽 메일 본문 위 업무 카드"></td>
    <td width="50%"><img src="docs/assets/screenshots/calendar.png" alt="캘린더 — 월 보기에 업무 기한과 회의가 표시되고 오른쪽에 오늘 일정 목록"></td>
  </tr>
  <tr>
    <td align="center">메일 — 본문 위에 뽑은 업무 · 기한</td>
    <td align="center">캘린더 — 기한 · 회의 · 미룬 업무</td>
  </tr>
</table>

만들지 않는 것: 자동 발송(사용자가 [보내기]를 누른 메일만 보낸다, D48), 자동 보관, 묻지 않는 자동 완료.

## 성능

봉인한 FINAL TEST 200통(할 일 메일 90통 · 할 일 105개), 분류 프롬프트 `classify_v8.4`, 2026-11-23~24 측정.

| 모델 | 할 일 메일 찾음 | 할 일 메일 정밀도 | 모든 칸 정답 | 주 유형 | 마감 맞음 | 1통 처리 시간(중앙) |
|---|---|---|---|---|---|---|
| **K-EXAONE 2.5 (서비스 모델)** | **90/90 (놓침 0)** | 93.8% | 169/200 | 94.5% | 94/105 | 25.5초 |
| Claude Haiku 5.5 (비교용) | 89/90 | 98.9% | 180/200 | 98.5% | 95/105 | 4.8초 |
| DeepSeek V4.1 Flash (비교용) | 90/90 | 97.8% | 182/200 | 98.0% | 97/105 | 4.1초 |

- 비교 모델은 `eval/`에서만 부른다. 서비스는 엑사원만 쓴다(D41).
- v8.4는 직전 측정(v8.3)의 약점 묶음을 본 뒤 고친 버전이라, 이 세트가 완전히 처음 보는 세트는 아니다. 전체 표 · 조건 · 한계는 [scores.md 16절](docs/50_data_eval/scores.md).

## 구조

<img src="docs/00_common/img/architecture/01_overview.svg" alt="구조도 — 사용자는 frontend로 들어오고, 호출은 frontend → backend → ai 한 방향이며 ai만 엑사원을 부른다. eval은 서비스 밖에서 ai 파이프라인을 직접 불러 쓴다" width="900">

| 서비스 | 하는 일 | 기술 | 로컬 주소 |
|---|---|---|---|
| [frontend](frontend/README.md) | 대시보드 · 메일 · 캐치봇 · 캘린더 · 설정 화면, 음성 입력 | React 19 · Vite 8 · TypeScript · TanStack Query | `http://localhost:5173` |
| [backend](backend/README.md) | API · 메일 연동 · 업무 상태 · 행동 실행기 · 리마인더 · 분류 작업자 | Python 3.12 · FastAPI · SQLite · APScheduler | `http://localhost:8000` |
| [ai](ai/README.md) | 분류 · 근거 · 명령 해석 · 요약 · 초안 · 번역 · 신호. DB 없이 받은 입력만 처리 | Python 3.12 · FastAPI · 엑사원 API(`k-exaone_v2.5`) | `http://localhost:8001` |
| [eval](eval/README.md) | 채점 · 모델 비교. 서비스에 포함하지 않는다 | Python · Claude · OpenRouter(여기서만) | — |
| [infra](infra/README.md) | 배포 설정 · 저장소 규칙 | Railway · Caddy · Docker | — |

- 호출은 `frontend → backend → ai` 한 방향(HTTP)이다. ai는 DB에 접근하지 않고 backend를 부르지 않는다(D34). 의존 방향은 `eval → ai`.
- 자세한 API · 데이터 · 테스트는 [구조도 v3.1](docs/00_common/architecture.md).

## 빠른 시작

준비물: Python 3.12(루트 `.python-version`) · [uv](https://docs.astral.sh/uv/) · Node.js 22.22 이상(`frontend/package.json` engines)

```bash
git clone https://github.com/dlwodns/Teamproject_6.git
cd Teamproject_6
cp .env.example .env                    # 값은 각자 채운다. .env는 올리지 않는다
git config core.hooksPath .githooks     # 커밋 전 경계 · 비밀값 검사(클론마다 한 번)

python scripts/run_dev.py --no-llm      # ai · backend · frontend를 한 번에 띄운다. Ctrl+C로 한 번에 끈다
```

- `--no-llm`은 엑사원 없이 띄운다. 분류 · 명령 해석은 503으로 실패를 알리고 화면 · 메일 · 상태 변경은 그대로 된다.
- 화면은 기본이 모의 데이터(`VITE_API_MODE=mock`)다. backend에 붙이려면 `frontend/.env`에 `VITE_API_MODE=http`([frontend/README.md](frontend/README.md#설정)).
- 엑사원을 쓰려면 `.env`에 `EXAONE_API_KEY`를 넣고 `--no-llm`을 뺀다. 로컬 ollama · PC 터널은 [ai/README.md](ai/README.md#실행).
- 더미 메일이 채워진 시연 화면은 [backend/README.md](backend/README.md#시연-데이터)의 시드 명령으로 만든다.
- `run_dev.py` 옵션: `--only ai,backend` · `--port` · `--host` · `--reload`. 포트가 이미 쓰이면 빈 포트를 골라 서로 이어 준다.

## 배포

Railway에 서비스 3개(`web` · `backend` · `ai`)로 올린다. 공개 주소는 `web`(Caddy: 화면 + `/api` 프록시) 하나이고, `backend` · `ai`는 내부망으로만 닿는다. 운영은 `APP_MODE=prod` · `AUTH_MODE=session` · `MAIL_SOURCE=outlook_graph`.
서비스 변수 · 순서 · 확인 방법은 [infra/railway_setup.md](infra/railway_setup.md), 선정 근거는 [infra/deploy_decision.md](infra/deploy_decision.md). 배포 주소는 팀에만 공유한다.

## 환경 변수

`.env.example`을 복사해 `.env`로 쓴다. 키 · 토큰은 코드와 문서에 넣지 않는다. 코드가 읽는 변수는 모두 `.env.example`에 있어야 하고, 빠지면 CI가 막는다(INF-4).

| 묶음 | 변수 | 읽는 곳 |
|---|---|---|
| 엑사원 | `LLM_BACKEND`(기본 `exaone_api`) · `EXAONE_API_KEY`(쉼표로 여러 개) · `LLM_ENABLED` | ai |
| 로컬 엑사원 (선택) | `OLLAMA_BASE_URL` · `OLLAMA_UDS` · `EXAONE_MODEL` · `EXAONE_MODEL_DIGEST` · `OLLAMA_VERSION` | ai · eval |
| 서비스 연결 | `AI_SERVICE_URL` · `DATABASE_URL` · `APP_URL` | backend |
| 모드 | `APP_MODE`(`dev` \| `prod`) · `AUTH_MODE`(`header` \| `session`) · `DEMO_TOOLS` | backend |
| 메일 | `MAIL_SOURCE`(`dummy` \| `outlook_graph`) · `MS_GRAPH_CLIENT_ID` · `MS_GRAPH_CLIENT_SECRET` · `MS_GRAPH_REDIRECT_URI` · `MS_GRAPH_TENANT` · `TOKEN_ENCRYPTION_KEY` | backend |
| 백그라운드 작업 | `CLASSIFY_WORKER` · `REMINDER_SCHEDULER` · `REMINDER_SIGNALS` · `MEMORY_EXTRACT` | backend |
| 평가 전용 | `ANTHROPIC_API_KEY` · `OPENROUTER_API_KEY` | eval만 (`run_dev.py`는 서비스에 넘기지 않는다) |

서비스별 전체 목록 · 기본값은 각 서비스 README.

## 폴더

```
.
├── frontend/   웹 화면 (React + Vite)                       → 서비스
├── backend/    API · 메일 연동 · 리마인더 · 행동 실행기 (FastAPI) → 서비스
├── ai/         엑사원 서비스 (FastAPI)                       → 서비스
├── eval/       채점 · 모델 비교. Claude · OpenRouter는 여기서만
├── data/       더미 메일 생성기 · 생성 데이터 (원본 raw는 레포 미포함)
├── docs/       공통 규칙 · 결정 · 구조도 + 파트별 계획 · 명세 · 트러블슈팅
├── scripts/    동시 실행 · 경계 · 비밀값 검사 · PC 엑사원 터널
└── infra/      배포 설정 · 저장소 규칙
```

## 문서

| 문서 | 내용 |
|---|---|
| [PRD](docs/10_planning/refs/PRD.md) | 한 단락 PRD (v3.1) |
| [구조도](docs/00_common/architecture.md) | 구조 · API · 데이터 · 테스트 (v3.1) |
| [기획 명세](docs/10_planning/detail.md) · [AI 명세](docs/40_ai/detail.md) · [리마인더 명세](docs/10_planning/reminders.md) | 상세 명세 |
| [공통 결정](docs/00_common/decisions.md) | D1~D58 |
| [문서 지도](docs/README.md) · [작업 규칙](docs/00_common/work_rules.md) · [기여 규칙](CONTRIBUTING.md) | 어디에 무엇이 있는지 · 브랜치 · 커밋 · 리뷰 |

## 지키는 규칙

- 서비스 경로(`frontend` · `backend` · `ai`)에는 엑사원 밖 LLM 호출 코드와 키를 두지 않는다. Claude · OpenRouter는 `eval/`에서만 쓴다(D26 · D41). 커밋 전 훅과 CI의 `scripts/check_boundaries.py`가 막는다.
- 에이전트는 등록된 행동만 실행하고, 확인 여부는 backend 규칙이 정한다. 모든 상태 변경은 `action_log`에 남는다(D37).
- 답장 뒤에는 완료 여부를 묻고, 사용자가 고른 경우에만 완료한다(D48).
- 메일 본문 · 토큰을 로그에 남기지 않고, 메일 토큰은 암호화해 저장한다.

## 일정

| 날짜 | 마일스톤 |
|---|---|
| 11/27 (금) | 발표자료 + 코드 제출 — **코드 수정 마감**. 제출물: 레포 · 배포 URL · 발표자료 |
| 11/28 (토) | IR Day — 조별 발표 10분 이내 |

## 팀

| 이름 | 역할 | 파트 |
|---|---|---|
| 이재운 | 팀장 | 기획(팀장) · 프론트엔드 |
| 강예은 | 데이터 | AI · 데이터 · 평가 |
| 문규남 | 테크 · 커뮤니케이터 | 기획 · AI(팀장) · 인프라 |
| 임동하 | 테크팀장 | 프론트엔드 · 백엔드 |
| 최수호 | 테크 · 커뮤니케이터 | 백엔드 · 데이터 · 평가 |
| 홍태겸 | 테크 | 백엔드 · AI |

기여도는 [contribution.md](docs/00_common/contribution.md).

## 데이터 · 라이선스

- 개발 · 평가는 가상 LG CNS 조직의 더미 메일([data/dummy](data/dummy/README.md))로 한다. 실제 사내 메일 · 개인 메일은 어떤 폴더에도 넣지 않는다.
- 공개 데이터셋 MailEx(Enron 기반, 실명 포함)는 원재료로만 쓰고 레포에 올리지 않는다(D24). 라이선스 `[미확인]`.
- EXAONE 모델 · API는 LG AI연구원 약관을 따른다. 상업적 사용 조건 `[미확인]`.
- 글꼴 · 아이콘 고지는 [frontend/public/licenses](frontend/public/licenses). 이 레포는 비공개이며 레포 자체의 라이선스는 정하지 않았다.
