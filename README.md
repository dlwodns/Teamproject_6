# CNE(씨애니) · 메일 업무 누락 방지 AI 비서

> 6조 실리콘밸리 발사대 · 2026 천안형 글로벌 인재육성사업 AX 액션러닝 · LG CNS 기업 과제 04
> 서비스 이름 CNE는 **가칭**이다(팀 확정 전). 이름의 뜻과 후보는 기획 상세 명세 `docs/10_planning/detail.md` 1.4절(`feature/PL`)에 있다.
> 상태: 설계 · 문서 단계(PRD v3.1 · 구조도 v3.1). 서비스 코드는 아직 없다. 다음 마일스톤은 11/7 P0 E2E.

**놓친 업무는 찾아 주고, 끝날 때까지 챙겨 주는 메일 업무 비서.**
여러 메일 계정의 미처리 업무를 모아 보여 주고, 말로 지시하면 에이전트가 처리하며, 사용자가 완료 체크를 할 때까지 추적하고 다시 알려 준다.

> "그룹웨어를 바꾸지 않고, 쓰던 메일 위에서, 처리 완료까지. 모든 것은 사내 모델로, 외부 유출 없이."

## 1. 과제와 방향

| 단계 | 이름 | 무엇이 바뀌었나 | 근거 |
|---|---|---|---|
| 과제 (10/03) | 미처리 메일 리마인더 봇 | LG CNS 기업 과제 04 원안 | — |
| 확장 1 (10/24~10/31) | 업무 누락 방지 대시보드 | 1순위 목표를 업무 누락 0건으로. 메일이 아니라 메일에서 뽑은 '업무'를 대시보드로 관리 | D13 · D20 |
| 확장 2 (11/02) | 메일 업무 누락 방지 AI 비서 | 처리 완료까지 추적 + 리마인더, 말로 처리하는 행동형 에이전트, 무응답 확인 · 캘린더 · MCP | D35 · D37 · D43 |

- 사용자: 하루 업무 메일 100~200통을 받는 LG CNS 팀장(10/16 인터뷰).
- 성공 기준: 더미 메일 테스트셋 할 일 메일 누락 0건, 리마인더 중복 · 누락 0건, 서비스 경로 외부 LLM 호출 0건.

## 2. 주요 기능

| 기능 | 내용 | 우선순위 |
|---|---|---|
| 업무 추출 | 메일을 회신 · 요청 · 검토 · 공지 · 기타로 분류하고 할 일 · 기한 · 본인 지목을 뽑는다. 규칙 먼저, 모호한 것만 엑사원 | P0 |
| 대시보드 | 완료율 · 미처리 · 기한 임박 · 응답 대기 · 최근 행동, 우선 확인(기한 · 상급자 · 즐겨찾기) · 업무 성격 2열 칸 | P0 |
| 메일 | Outlook과 같은 3단 화면, 여러 계정 통합, 상태 버튼(완료 · 나중에 · 제외 · 되돌리기), 응답 대기 목록 | P0 |
| 처리 완료 추적 · 리마인더 | 완료 · 제외를 체크할 때까지 추적. 기한 전 · 경과 · 미룬 시각 · 하루 요약 알림, 중복 0 · 발송 직전 재확인 | P0 |
| 행동형 에이전트 · 음성 | 말 · 글 지시를 정해진 행동(T01~T14) 안에서 실행. 1건 변경은 바로 실행 + 되돌리기, 여러 건 · 설정 · 발송은 확인 | P0 |
| 요약 · 초안 | 오늘 요약, 영문 메일 한국어 요약, 회신 초안(보내지 않음) | P0 (기본 기능) |
| 캘린더 | 기한 · 나중에 업무를 월 · 주 단위로 표시. Outlook 캘린더에는 쓰지 않음 | P1 |
| 템플릿 전송 | 선택한 메일에 정해진 문구를 미리보기 + 확인 후 발송. 무응답 재촉 템플릿이 먼저 | 재촉 P1 · 일반 P2 |
| MCP 연동 | 같은 행동을 MCP 도구로 노출해 사내 에이전트 플랫폼과 연동 | P2 |

만들지 않는 것: 메일 앱 대체, 자동 발송(발송은 사용자가 확인한 답장 · 템플릿만, D48), 자동 보관, 외부 캘린더 쓰기.

## 3. 구성과 기술 스택

```
frontend (React + Vite + TS, PWA)
   │ HTTP
backend (FastAPI · APScheduler · SQLite) ── 메일: 더미 JSON / Outlook(Microsoft Graph)
   │ HTTP                                 ── 리마인더 스케줄러 · 행동 레지스트리 · MCP 서버(P2)
ai (FastAPI) ── ollama · EXAONE 3.5 7.8B Instruct GGUF Q4_K_M
eval (채점 · Claude 보조 채점 · 모델 비교) ── ai 파이프라인을 직접 import, 서비스에 포함하지 않음
```

| 구성 | 기술 | 기본 주소 |
|---|---|---|
| frontend | React · Vite · TypeScript, PWA(웹 푸시), Web Speech API | `http://localhost:5173` `[예정]` |
| backend | Python · FastAPI · APScheduler(1프로세스) · SQLite · Apprise(확장용) | `http://localhost:8000` |
| ai | Python · FastAPI, 서버 음성인식 Whisper(선택) | `http://localhost:8001` (`AI_SERVICE_URL`) |
| LLM | ollama + `hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:Q4_K_M` 하나 | `http://localhost:11434` |

자세한 구조 · API · 데이터 · 테스트는 `docs/00_common/architecture.md`(v3.1).

## 4. 시작하기

### 4-1. 준비물

| 항목 | 기준 |
|---|---|
| Python | 3.12 (루트 `.python-version`, uv가 읽는다). 채점기 · 더미 생성기는 표준 라이브러리만 써서 3.10 이상이면 돈다 |
| Node.js | 22 (루트 `.nvmrc`, `nvm use`로 맞춘다). frontend 골격을 만들 때 `package.json` `engines`에도 적는다 |
| ollama · 엑사원 | RAM 16GB에서 CPU만으로 동작 확인. 모델 파일 약 5GB `[미확인]` |

### 4-2. 지금 할 수 있는 것

```bash
git clone https://github.com/dlwodns/Teamproject_6.git
cd Teamproject_6
cp .env.example .env                              # 값은 각자 채운다. .env는 올리지 않는다
git config core.hooksPath .githooks               # 커밋 전 경계 · 비밀값 검사 켜기(클론마다 한 번, INF-8)

# 엑사원 받기 (설치 · 확인 방법: eval/README.md 2절)
ollama pull hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:Q4_K_M

# 채점기 점검 → selfcheck OK
python data/dummy/eval.py --selfcheck

# 더미 메일 다시 만들기 (검증 오류 0이어야 정상)
cd data/dummy && python build.py
```

### 4-3. 서비스 실행 `[예정]`

코드 골격(FE-1 · BE-1 · AI-9)이 생기면 이 절을 실제 명령으로 바꾼다. 예정 형태:

```bash
cd ai && uvicorn app.main:app --port 8001         # ai
cd backend && uvicorn app.main:app --port 8000    # backend (APP_MODE=dev면 더미 적재 · 시간 이동 사용 가능)
cd frontend && npm install && npm run dev         # frontend
```

## 5. 환경 변수

`.env.example`을 복사해 `.env`로 쓴다. 키 · 토큰은 코드와 문서에 넣지 않는다.
모든 파트가 같은 값을 써야 하는 환경 설정은 main에 커밋한다(`CONTRIBUTING.md` 2).

개발 서버(dev-server-02)는 메모리 한도 때문에 엑사원 7.8B를 올리지 않는다. 엑사원은 PC ollama에서 돌리고, 서버는 역방향 SSH 터널(Unix 소켓)로 부른다. 실행 방법은 `ai/README.md` '실행' (`feature/AI-service` 병합 후).

| 묶음 | 변수 | 읽는 곳 |
|---|---|---|
| ai 주소 | `AI_SERVICE_URL` | backend |
| 엑사원 | `LLM_BACKEND` · `OLLAMA_BASE_URL` · `EXAONE_MODEL` | ai (외부 LLM 키 없음, D41) |
| 엑사원 PC 터널 · 고정값 | `OLLAMA_UDS` · `EXAONE_MODEL_DIGEST` · `OLLAMA_VERSION` — 값은 `scripts/exaone-pc.env` 한 곳에 둔다 (`feature/AI-service` 병합 후) | ai · eval (AI-D9) |
| 메일 연동 | `MS_GRAPH_CLIENT_ID` · `MS_GRAPH_CLIENT_SECRET` · `MS_GRAPH_REDIRECT_URI` · `MAIL_SOURCE`(`dummy` \| `outlook_graph` \| `imap`) | backend |
| 보안 | `TOKEN_ENCRYPTION_KEY` | backend |
| 알림 · 모드 | `VAPID_PUBLIC_KEY` · `VAPID_PRIVATE_KEY` · `APP_MODE`(`dev` \| `prod`) | backend |
| MCP (P2) | `MCP_ACCESS_TOKEN` | backend |
| 음성 | `STT_MODE`(`browser` \| `server`) | frontend · backend |
| 평가 전용 | `ANTHROPIC_API_KEY` · `OPENROUTER_API_KEY` | eval만 |

## 6. 폴더 지도

| 폴더 | 내용 | 실서비스에 포함 |
|---|---|---|
| `frontend/` | 웹 화면(대시보드 · 메일 · 캘린더 · 설정 · 에이전트 패널 · 알림 센터), 음성 입력 | O |
| `backend/` | API · 메일 연동 · 업무 상태 · `action_log` · 행동 실행기 · 리마인더 · 개인정보 처리 · MCP(P2) | O |
| `ai/` | 엑사원 서비스: 분류 · 명령 해석 · 요약 · 초안 · 음성인식. 백엔드가 HTTP로 부른다 | O |
| `eval/` | 채점 · 벤치. **Claude · OpenRouter는 이 폴더에서만** | X |
| `data/` | 더미 메일 생성기 · 생성 데이터 · 원본(raw, 레포 미포함) | X |
| `docs/` | 공통 규칙 · 결정 · 구조도 + 파트별 구현계획 · 상세 명세 · decisions · 트러블슈팅 | X |
| `scripts/` | 경계 검사 · 동시 실행 스크립트 `[예정]` | X |
| `infra/` | 배포 설정: HTTPS 프록시 · 서비스 실행 · 배포 · 백업 `[예정]`. 할 일 · 원칙은 `infra/plan.md`, 한 일 · 쓰는 법은 `infra/status.md` | O (배포 서버) |

각 폴더의 `README.md`에 역할과 규칙이 있다.

## 7. 문서 읽는 순서

| 순서 | 문서 | 내용 |
|---|---|---|
| 1 | `docs/10_planning/refs/PRD.md` | 한 단락 PRD (v3.1) |
| 2 | `docs/00_common/architecture.md` | 구조도 · API · 데이터 · 테스트 (v3.1) |
| 3 | `docs/10_planning/detail.md` · `docs/40_ai/detail.md` | 기획 · AI 상세 명세 (`feature/PL` · `feature/AI` 병합 후) |
| 4 | `docs/00_common/decisions.md` | 공통 결정 D1~D46 |
| 5 | `docs/00_common/handoff.md` | 지금 상태 · 다음 할 일 · 위험 |
| — | `docs/README.md` · `docs/00_common/work_rules.md` | 문서 지도 · 작업 규칙 |

## 8. 일정

| 날짜 | 마일스톤 | 목표 |
|---|---|---|
| 11/07 | 에이전트 · 자동화 결합 E2E | P0 전체 (시연 ①~⑥) |
| 11/14 | 실배포 · 상호 QA | 서비스 URL(HTTPS), 리마인더 실발송 |
| 11/21 | 고도화 · IR Deck 초안 | P1 (캘린더 · 근거 · 설정) |
| 11/26 | 최종 리허설 | 제출물: Repo · 배포 URL · Deck |
| 11/28 | IR Day | 피칭 20분 + Q&A 5분 |

P0 완료 전에는 P1 · P2를 시작하지 않고, 밀리면 P2부터 뺀다.

## 9. 팀

| 이름 | 역할 | 파트 |
|---|---|---|
| 이재운 | 팀장 | 기획(팀장) · 프론트엔드 |
| 강예은 | 데이터 | AI · 데이터 · 평가 |
| 문규남 | 테크 · 커뮤니케이터 | 기획 · AI(팀장) |
| 임동하 | 테크팀장 | 프론트엔드 · 백엔드 |
| 최수호 | 테크 · 커뮤니케이터 | 백엔드 · 데이터 · 평가 |
| 홍태겸 | 테크 | 백엔드 · AI |

프론트엔드 · 백엔드 · 데이터 · 평가 파트 팀장과 인프라 담당은 미정(D45). 기여도는 `docs/00_common/contribution.md`.

## 10. 지키는 규칙 (요약)

- 서비스 경로(`frontend` · `backend` · `ai`)에는 외부 LLM 호출 코드와 키를 두지 않는다. Claude · OpenRouter는 `eval/`에서만 쓴다(D26 · D41).
- 호출 방향은 `frontend → backend → ai`(HTTP). `ai`는 DB에 접근하지 않고 `backend`를 부르지 않는다(D34). 의존 방향은 `eval → ai`.
- 에이전트는 등록된 행동만 실행하고, 확인 여부는 백엔드 규칙이 정한다. 모든 상태 변경은 `action_log`에 남는다(D37).
- 답장 뒤에는 완료 여부를 묻고, 사용자가 고른 경우('예' · '오늘 하루 보지 않기')에만 완료한다. 묻지 않고 자동 완료하지 않는다(D48, D36 대체).
- 메일 본문 · 토큰을 로그에 남기지 않고, 메일 토큰은 암호화해 저장한다.
- 브랜치 · 커밋 · 리뷰 규칙은 `CONTRIBUTING.md`.

## 11. 데이터 · 라이선스

- 개발 · 평가는 가상 LG CNS 조직의 더미 메일(`data/dummy/`, v1 100건)로 한다. 실제 사내 메일 · 개인 메일은 어떤 폴더에도 넣지 않는다.
- 공개 데이터셋 MailEx(Enron 기반, 실명 포함)는 원재료로만 쓰고 레포에 올리지 않는다(D24). 라이선스 `[미확인]`.
- EXAONE 모델은 LG AI연구원 라이선스를 따른다. 상업적 사용 조건 `[미확인]`.
- 이 레포는 비공개이며 레포 자체의 라이선스는 정하지 않았다.
