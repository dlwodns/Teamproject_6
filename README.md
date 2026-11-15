# CNE(See Any)

**Catch & End**

하루 100~200통의 업무 메일을 받다 보면 기존의 방식으로는 하나씩 확인하다 업무를 놓치게 됩니다.
저희 CNE는 이 누락을 막는 것을 첫 번째 목표로 합니다.

- 엑사원이 메일 속 업무를 자동으로 추출해 유형별로 나누고 관리하고 처리할 수 있는 대시보드
- 업무 누락 방지를 위한 리마인더
- 글이나 음성으로 지시하면 대신 처리하는 에이전트
- 자신만의 방식으로 설정과 템플릿을 커스텀하세요.

외부의 정보 유출 걱정이 없도록 LG CNS 사내 모델(엑사원)과 MCP로 에이전틱웍스, a:xink 브리핑, 사내 도구들을 연동할 수 있도록 설계했습니다.

> 6조 실리콘밸리 발사대 · 2026 천안형 글로벌 인재육성사업 AX 액션러닝 · LG CNS 기업 과제 04

## 1. 사용자와 목표

- 사용자: 하루 업무 메일 100~200통을 받는 LG CNS 팀장.
- 성공 기준: 더미 메일 테스트셋 할 일 메일 누락 0건, 리마인더 중복 · 누락 0건, 서비스 경로 외부 LLM 호출 0건.

## 2. 주요 기능

| 기능 | 내용 | 우선순위 |
|---|---|---|
| 업무 추출 | 메일을 회신 · 요청 · 검토 · 공지 · 기타로 분류하고 할 일 · 기한 · 본인 지목을 뽑는다. 규칙 먼저, 모호한 것만 엑사원 | P0 |
| 대시보드 | 1열 업무 건수(받은 날 기준 전체 · 처리 · 미처리) · 응답 대기 · 확인사항, 2열 긴급(기한 지남 · ASAP · 오늘 마감) · 업무 유형(회신 · 요청 · 검토 · 기타) 칸 | P0 |
| 메일 | Outlook과 같은 3단 화면, 여러 계정 통합, 상태 버튼(완료 · 나중에 · 제외 · 되돌리기), 응답 대기 목록 | P0 |
| 처리 완료 추적 · 리마인더 | 완료 · 제외를 체크할 때까지 추적. 기한 전 · 경과 · 미룬 시각 · 하루 요약 알림, 중복 0 · 발송 직전 재확인 | P0 |
| 행동형 에이전트 · 음성 | 말 · 글 지시를 정해진 행동(T01~T14) 안에서 실행. 1건 변경은 바로 실행 + 되돌리기, 여러 건 · 설정 · 발송은 확인 | P0 |
| 요약 · 초안 | 오늘 요약, 메일 요약(영문 → 한국어, 그 밖의 외국어는 실패 시 안내), 회신 초안(보내지 않음) | P0 (기본 기능) |
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
| uv | 파이썬 패키지 설치 · 실행. CI와 같은 0.13.3 권장 |
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

### 4-3. 서비스 실행

준비물에 uv(파이썬 패키지 · 실행)가 더 필요하다. 파이썬 패키지는 각 폴더의 `uv.lock` 그대로 설치된다(INF-3).

```bash
python scripts/run_dev.py              # ai · backend · frontend 한 번에, Ctrl+C로 한 번에 끈다(INF-7)
python scripts/run_dev.py --no-llm     # 엑사원 없이(규칙 결과만)
scripts/exaone-pc.sh run python scripts/run_dev.py   # 개발 서버: PC 엑사원 터널로(ai/README.md '실행')
```

- 밖에 여는 포트는 frontend 하나다. 화면의 `/api/...`는 Vite 프록시가 backend로 넘긴다. 개발 서버에서는 계정에 할당된 `$PORT`에 `0.0.0.0`으로 연다.
- ai(8001) · backend(8000) 포트가 다른 계정에서 이미 쓰이면 빈 포트를 골라 서로 이어 준다.
- 서비스는 시작할 때 설정을 검사하고, 값이 틀리면 뜨지 않는다(INF-4). 따로 띄우는 법 · 테스트는 각 폴더 `README.md` '실행'.

## 5. 환경 변수

`.env.example`을 복사해 `.env`로 쓴다. 키 · 토큰은 코드와 문서에 넣지 않는다.
모든 파트가 같은 값을 써야 하는 환경 설정은 main에 커밋한다(`CONTRIBUTING.md` 2).

개발 서버(dev-server-02)는 메모리 한도 때문에 엑사원 7.8B를 올리지 않는다. 엑사원은 PC ollama에서 돌리고, 서버는 역방향 SSH 터널(Unix 소켓)로 부른다. 실행 방법은 `ai/README.md` '실행'.

코드가 읽는 변수는 모두 `.env.example`에 있어야 한다. 기본값으로 충분한 변수는 `# NAME=기본값` 주석으로 적는다. 빠지면 CI가 막는다(INF-4).

| 묶음 | 변수 | 읽는 곳 |
|---|---|---|
| ai 주소 | `AI_SERVICE_URL` | backend |
| 엑사원 | `LLM_BACKEND`(기본 `exaone_api`) · `EXAONE_API_KEY` · `OLLAMA_BASE_URL` · `EXAONE_MODEL` | ai (외부 모델 키는 엑사원 API 하나, D52 · D53) |
| 엑사원 API 조정값 (주석, 코드 기본값) | `EXAONE_API_BASE_URL` · `EXAONE_API_MODEL` · `EXAONE_REASONING_EFFORT` | ai (AI-D18) |
| 엑사원 PC 터널 · 고정값 | `OLLAMA_UDS` · `EXAONE_MODEL_DIGEST` · `OLLAMA_VERSION` — 값은 `scripts/exaone-pc.env` 한 곳에 둔다 | ai · eval (AI-D9) |
| ai 조정값 (주석, 코드 기본값) | `LLAMACPP_BASE_URL` · `LLM_TIMEOUT_S` · `OLLAMA_KEEP_ALIVE` · `ROUTER_THRESHOLD` · `LLM_ENABLED` · `CLASSIFY_PROMPT` | ai |
| 메일 연동 | `MS_GRAPH_CLIENT_ID` · `MS_GRAPH_CLIENT_SECRET` · `MS_GRAPH_REDIRECT_URI` · `MAIL_SOURCE`(`dummy` \| `outlook_graph`) | backend |
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
| `scripts/` | 경계 · 비밀값 검사 · 동시 실행(`run_dev.py`) · PC 엑사원 터널 · GPU 측정 | X |
| `infra/` | 배포 설정: HTTPS 프록시 · 서비스 실행 · 배포 · 백업 `[예정]`. 할 일 · 원칙은 `infra/plan.md`, 한 일 · 쓰는 법은 `infra/status.md` | O (배포 서버) |

각 폴더의 `README.md`에 역할과 규칙이 있다.

## 7. 문서 읽는 순서

| 순서 | 문서 | 내용 |
|---|---|---|
| 1 | `docs/10_planning/refs/PRD.md` | 한 단락 PRD (v3.1) |
| 2 | `docs/00_common/architecture.md` | 구조도 · API · 데이터 · 테스트 (v3.1) |
| 3 | `docs/10_planning/detail.md` · `docs/40_ai/detail.md` | 기획 · AI 상세 명세 |
| 4 | `docs/00_common/decisions.md` | 공통 결정 D1~D49 |
| 5 | `docs/00_common/handoff.md` | 지금 상태 · 다음 할 일 · 위험 |
| — | `docs/README.md` · `docs/00_common/work_rules.md` | 문서 지도 · 작업 규칙 |

## 8. 일정

| 날짜 | 마일스톤 | 목표 |
|---|---|---|
| 11/07 | 에이전트 · 자동화 결합 E2E | P0 전체 (시연 ①~⑥) |
| 11/14 | 실배포 · 상호 QA | 서비스 URL(HTTPS), 리마인더 실발송 |
| 11/20 (금) | 발표자료 초안 (과정 제출 · 조별) | 제출 1주 전 초안, 이후 수정 · 보완 |
| 11/21 (토) | 발표 리뷰 · 고도화 | 초안 발표 리뷰, P1 (캘린더 · 근거 · 설정) |
| 11/27 (금) | 발표자료 + 코드 제출 (과정 제출 · 조별) | **코드 수정 마감**. 제출물: Repo · 배포 URL · 발표자료 |
| 11/28 (토) | IR Day | 조별 발표 10분 이내 |

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

프론트엔드 · 백엔드 · 데이터 · 평가 파트 팀장은 미정(D45). 인프라 담당은 문규남(11/7 확정). 기여도는 `docs/00_common/contribution.md`.

## 10. 지키는 규칙 (요약)

- 서비스 경로(`frontend` · `backend` · `ai`)에는 외부 LLM 호출 코드와 키를 두지 않는다. Claude · OpenRouter는 `eval/`에서만 쓴다(D26 · D41).
- 호출 방향은 `frontend → backend → ai`(HTTP). `ai`는 DB에 접근하지 않고 `backend`를 부르지 않는다(D34). 의존 방향은 `eval → ai`.
- 에이전트는 등록된 행동만 실행하고, 확인 여부는 백엔드 규칙이 정한다. 모든 상태 변경은 `action_log`에 남는다(D37).
- 답장 뒤에는 완료 여부를 묻고, 사용자가 고른 경우('예' · '오늘 하루 보지 않기')에만 완료한다. 묻지 않고 자동 완료하지 않는다(D48).
- 메일 본문 · 토큰을 로그에 남기지 않고, 메일 토큰은 암호화해 저장한다.
- 브랜치 · 커밋 · 리뷰 규칙은 `CONTRIBUTING.md`.

## 11. 데이터 · 라이선스

- 개발 · 평가는 가상 LG CNS 조직의 더미 메일(`data/dummy/`, v1 100건)로 한다. 실제 사내 메일 · 개인 메일은 어떤 폴더에도 넣지 않는다.
- 공개 데이터셋 MailEx(Enron 기반, 실명 포함)는 원재료로만 쓰고 레포에 올리지 않는다(D24). 라이선스 `[미확인]`.
- EXAONE 모델은 LG AI연구원 라이선스를 따른다. 상업적 사용 조건 `[미확인]`.
- 이 레포는 비공개이며 레포 자체의 라이선스는 정하지 않았다.
