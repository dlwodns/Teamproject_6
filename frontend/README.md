# frontend · React + Vite + TS

> 기준 문서: PRD v3.1 Q5 · 구조도 v3.1 2절 · wireframe 12절(v3.1 변경 미반영 — 성격 칸 · 응답 대기 · 알림 센터 · 캘린더는 FE에서 반영 예정)

## 실행 (FE-1)

**Node 22.18 이상 필요**(`package.json` engines `>=22.18.0`, 테스트가 Node의 TS 타입 제거 기능을 쓴다) · npm 10. 루트 `.nvmrc`는 `22`라 22.18 미만을 막지 않으니 `node -v`로 확인한다. `frontend/.npmrc`의 `engine-strict=true`로 버전이 맞지 않으면 설치가 멈춘다.

```bash
cd frontend
npm ci                      # package-lock.json 그대로 설치 (CI와 같음)
npm run dev -- --port <배정 포트>  # http://127.0.0.1:<배정 포트> · 쓰이고 있으면 다른 포트로 넘어가지 않고 멈춘다(strictPort)
npm run typecheck           # 타입 검사
npm run build               # 타입 검사 + 프로덕션 빌드(dist/)
npm test                    # 집계 · 기한 판정 · 응답 변환 · 색 대비 (node --test)
npm run mock:check          # 모의 데이터가 원본에서 다시 만든 결과와 같은지
```

- 테스트는 실행 환경 시간대와 무관해야 한다. `TZ=UTC npm test` · `TZ=Asia/Seoul npm test` 둘 다 통과해야 한다.
- `<배정 포트>`는 각자 계정에 배정된 값으로 바꾼다(`echo $PORT`로 확인, infra/plan.md 2절). 포트 번호를 공용 기본값으로 저장하지 않는다. `--port`를 빼면 Vite 기본값(5173)을 쓰는데, 공용 서버에서는 다른 사람과 겹칠 수 있다.
- 원격 서버에서 띄우면 VS Code Remote SSH의 Ports 탭에서 해당 포트를 전달하고, 표시된 로컬 주소로 연다. 개발 서버는 `127.0.0.1`에만 열린다(`vite.config.ts`).

## 데이터 모드

| 값 | 동작 |
|---|---|
| `VITE_API_MODE=mock` (기본, 비워도 mock) | `src/api/mock/dashboard.v1.json`을 읽는다. 주소에 `mock=loading` · `mock=empty` · `mock=error`를 붙이면 그 상태를 볼 수 있다(아래) |
| `VITE_API_MODE=http` | `VITE_API_BASE`(기본 `/api`) + `/dashboard`를 부른다. 실패하면 오류 화면을 보이고 모의 데이터로 대신하지 않는다 |

- mock 미리보기 주소: `/?mock=error#/dashboard`(일반 쿼리) · `/#/dashboard?mock=error`(해시 안 쿼리) 둘 다 된다. 둘 다 있으면 **해시 안 값을 우선**한다. 페이지를 불러올 때 한 번 읽으므로 바꾼 뒤 새로고침한다. 다른 값은 무시(정상 모의 데이터), 모르는 경로는 대시보드. `http` 모드에서는 mock 쿼리를 읽지 않는다.
- 오류 안내: 네트워크 실패('서버에 연결하지 못했습니다…') · HTTP 오류(오류 코드) · 형식 오류 · 설정 오류를 나눠 사용자용 문구로 보인다(`src/pages/dashboard/errorText.ts`). 브라우저 오류 원문은 화면에 내지 않는다.
- 응답 정합성: 업무가 가리키는 메일이 응답에 없으면 그 업무를 '메일 정보 확인 필요'로 따로 보여 준다(계약 위반 방어, `docs/20_frontend/be3_contract_comparison.md` 4절). 메일 목록 안 `mail.id` 중복 · 업무 목록 안 `task.id` 중복은 형식 오류(두 목록 사이는 같은 id여도 된다).
- 예시: `frontend/.env.example` → `frontend/.env`로 복사. `VITE_` 값은 빌드 결과에 그대로 들어가므로 비밀값을 넣지 않는다.
- 개발 서버 프록시(`vite.config.ts`): `/api/health` → backend `/health`(지금 backend에 있는 유일한 라우트), 그 밖의 `/api/...`는 경로를 바꾸지 않고 넘긴다. backend 주소는 `BACKEND_PROXY_TARGET`(기본 `http://127.0.0.1:8000`).
- **`/api/dashboard`는 backend에 아직 없다(BE-3).** 경로는 구조도 8절 `[제안]`, 응답 형식은 `src/api/provisional.ts`의 FE 임시 가정이다(구조도 8절의 요약 + 칸 형식과 다름). 화면용 모델로의 변환은 `src/api/adapter.ts` 한 곳에서 하고, 시간대가 없는 시각은 오류로 거절한다(D47 `+09:00`).
- 프론트는 ai 서비스를 직접 부르지 않는다.

## 모의 데이터 (FE-1)

- 원본 `data/dummy/dummy_mails.json` v1(수정하지 않음) → `npm run mock:extract`(`scripts/extract-mock.mjs`) → `src/api/mock/dashboard.v1.json`. 원본 SHA-256을 `meta`에 남긴다.
- 화면에 필요한 메일 메타데이터(발신자 · 제목 · 수신 시각 · 분류)와 정답 업무만 넣는다. 메일 본문 · 첨부 · 평가용 라벨은 넣지 않는다.
- 순서 · id · 분류는 backend 시드(`backend/app/dev/seed.py`)와 같다. 업무에는 분류 칸이 없어 **업무가 나온 메일의 `category`**로 오른쪽 칸을 정한다.
- 기준 시각 `2026-10-20T09:00:00+09:00` 고정(브라우저 현재 시각을 쓰지 않음).

## 집계 기준 (FE-1 임시 · BE-3에서 맞출 계약)

`src/features/tasks/aggregate.ts` · `deadline.ts`

- 기한 지남 `due_at < 기준 시각` · 오늘 마감(기한 남음) 같은 KST 날짜이고 `due_at >= 기준 시각` · 내일 = 다음 KST 날짜. 기한 유무는 `due_at`으로만 판단(`due_source` 안 씀).
- 미처리 = `pending`만 칸 · 미처리 수에 포함. 완료율 = 완료 ÷ (미처리 + 나중에 + 완료), 제외는 분모에서 뺀다.
- 왼쪽 '우선 확인' = 기한(지남 · 오늘 · 내일) · 상급자 · 즐겨찾기, 오른쪽 '업무 성격' = 회신 · 요청 · 검토 · 기타. 같은 업무가 여러 칸에 들어갈 수 있어 칸 건수를 더해 전체 업무 수로 쓰지 않는다.
- 공지 분류 메일에 업무가 있으면 '기타'에 넣는다(`NOTICE_TASK_POLICY`, 임시. v1에는 해당 0개).

## 디자인 (UX-D4 · UX-D10 · 작업 규칙)

`src/styles/tokens.css` 한 곳에서 관리한다(이름은 `--c-*`). 값 · 대비 · 근거는 `docs/20_frontend/design_system.md` 1 · 2 · 3절. FE-D7(오렌지) · FE-D11(LG CI · 사이트 추출값)은 UX-D4로 대체됐고 추출 기록은 decisions에 근거로 남아 있다.

- 색 60 · 35 · 5: 무채색 면(`--c-surface` #FFFFFF · `--c-canvas` #F7F8F9) · 보조 4색(`--c-ink` #121212 · `--c-gray` #6B6B6B · `--c-line` #E5E5E5 · `--c-fill` #F0F1F3) · 포인트 LG Heritage Red `--c-point` #A50034는 채운 주 버튼 · 에이전트 버튼 · 선택 표시선에만(글자 · 배지 · 아이콘 · 차트 금지).
- 선택 = 채움 바탕 + 포인트 선 + 굵은 글씨 + `aria-current`, hover = `--c-fill`, 포커스 = 2px `--c-ink` 링 + 2px 띄움.
- 기한 라벨(UX-D10): 기한 지남 `D+2` 검정 · 오늘 `오늘 18:00` 파랑 · 남음 `내일 12:00` / `11/10(화)` 초록 · 없음 `기한 없음` 회색. ⚠ · '기한 지남' 글자는 붙이지 않고, 화면 읽기용으로만 '기한 지남 · 전체 시각'을 덧붙인다(`deadline.ts` `dueLabel`). ASAP는 FE 계약에 `due_raw`가 없어 아직 표시하지 않는다(스타일 `data-state='asap'`만 준비).
- 위험 빨강(#B20C00)은 포인트 빨강과 1.11:1이라 음성 '듣는 중'에만 쓴다. 안내 · 모의 데이터 배지는 정보색(#003374 / #DDF3FB).
- 대비: 글자 4.5:1, 상태 표시 · 포커스 링 · 입력칸 테두리 3:1 — `src/styles/contrast.test.ts`가 실제 토큰 값과 design_system 문서 수치를 함께 검사한다.
- 글꼴(모두 빌드에 포함 · SIL OFL 1.1 · 고지 `public/licenses/`): 국문 · 영문 본문 Pretendard Variable(npm `pretendard` 1.3.9), 영문 표시 · 숫자 Outfit Variable(npm `@fontsource-variable/outfit` 5.3.0, 라틴 글자만 있어 한글은 Pretendard로 넘어감). 건수 · 시각은 `tabular-nums`. 못 불러오면 시스템 한글 글꼴 → sans-serif.

## 화면 틀 (FE-D12 · FE-D13)

- 왼쪽 접이식 주 메뉴(대시보드 · 메일 · 설정): `src/app/Sidebar.tsx`. 720px 이하는 접힌 채 시작, 펼치면 본문 위에 겹친다. 전역 단축키 없음.
- 에이전트: 설정 화면을 뺀 모든 화면 오른쪽 아래 원형 버튼 → 오른쪽 패널(지금은 '준비 중'만). 닫기 버튼 · Esc. 이름 · 아이콘은 `src/features/agent/agentBrand.tsx`에서 교체.

## 업무 상태 토스트 (FE-4)

- 완료 · 나중에 · 제외 · 되돌리기의 토스트는 `src/features/tasks/useTaskActions.ts` 한 곳에서 띄운다. 문구와 규칙은 `src/lib/toastPolicy.ts`(wireframe 13-6, '~해요' 체).
  - 성공: `업무 N건을 완료로 바꿨어요 [되돌리기]`(8초). 이미 그 상태라 바뀐 것이 없으면 정보 토스트(`이미 완료된 업무예요`).
  - 되돌리기: `되돌렸어요`.
  - 실패: `완료로 바꾸지 못했어요` + 이유 한 줄. 연결 실패 · 시간 초과 · 서버 오류에만 [다시 시도]. 409 · 404 · 401 · 422처럼 다시 보내도 같은 실패에는 붙이지 않는다. 실패해도 대시보드는 다시 불러와 서버 값으로 맞춘다.
- 부르는 화면은 실패 안내를 따로 띄우지 않는다. 자기 결과 줄 · [실행 취소]가 있는 화면(에이전트 카드 · 제안 카드 · 기록)은 `{ toast: false }`로 부르고, 그때는 성공 · 실패 토스트를 모두 띄우지 않는다.
- `useToast`는 `src/ui/toastApi.ts`에 있다(로직 시험이 .tsx를 읽지 못해 `ui/Toast.tsx`에서 떼어 냄, 모양 · 자리는 그대로 `Toast.tsx`).
- 훅의 몸통은 보통 함수 `createTaskActions({ api, queryClient, toast })`다. `useTaskActions.test.ts`가 가짜 api · 토스트로 토스트가 언제 · 몇 번 뜨는지(`toast: false`, [다시 시도], [되돌리기] 누르면 닫기)를 시험한다.

## 후속 작업 (화면에는 작업 번호를 적지 않고 '준비 중'으로만 보인다)

| 화면 · 기능 | 작업 |
|---|---|
| 메일 화면 · 원본 메일 보기 · 답장 · 답장 후 완료 확인 팝업(D48) | FE-5 |
| 설정 화면 | FE-6 |
| 에이전트 입력창 · 결과 카드 · 실행 확인창(패널 틀은 FE-1) | FE-7 |
| 음성 입력 버튼 | FE-8 |
| 전역 단축키 · 설정의 단축키 칸, 미니 대시보드 · 시작 화면 설정 | 작업 배정 미정 |
| 모의 데이터 → 실제 API 연결(대시보드 API는 BE-3, 계약 비교 `docs/20_frontend/be3_contract_comparison.md`) | FE-9 · BE-3 |
| 알림 센터 목록 · 알림 수 | 알림 API 연결 뒤(담당 미정) |

## 폴더

| 폴더 | 내용 |
|---|---|
| `src/app/` | 라우터 · 공통 레이아웃(왼쪽 접이식 메뉴: 대시보드 · 메일 · 설정, 상단 바: 앱 이름 · 알림 센터 진입점) · 전역 상태 · PWA(서비스 워커 · 웹 푸시 구독). 캘린더 메뉴는 FE-1에서 넣지 않았다 |
| `src/pages/dashboard/` | 요약 줄(완료율 · 미처리 · 기한 임박 · 응답 대기 · 최근 행동) + 세로 2열 업무 칸(우선 확인 · 업무 성격: 회신 · 요청 · 검토 · 기타) (D20 · D39 · D40) |
| `src/pages/mail/` | Outlook 3단(계정 · 즐겨찾기 메뉴, 메일 목록, 미리보기), 여러 계정 통합, 응답 대기 목록(경과일) |
| `src/pages/calendar/` `[P1]` | 월 · 주 보기. 기한 · 나중에 업무, 날짜 클릭 → 업무 목록 → 메일 미리보기 |
| `src/pages/settings/` | 내 정보 · 메일 연동(본문 읽기 on/off) · 알림(리마인드 주기 · 조용한 시간 · 무응답 기준일 · 웹 푸시, iOS 설치 안내) · 템플릿 · 화면 · AI 에이전트 |
| `src/features/tasks/` | 업무 카드 · 상태 버튼(완료 · 나중에 · 제외 · 되돌리기) · 일괄 처리 · 되돌리기 토스트 · 회신 후 완료 확인 팝업(D23) |
| `src/features/mail/` | 메일 표시 · 답장 작성 |
| `src/features/notifications/` | 알림 센터(리마인더 목록) · 웹 푸시 권한 요청 |
| `src/features/settings/` | 설정 항목별 폼, 개인정보 동의 화면 |
| `src/features/agent/` | 오른쪽 아래 원형 버튼 · 에이전트 패널(360px, FE-1은 틀만): 입력창 · 결과 카드 · 확인창(확인이 필요한 행동만, D37) · 되돌리기 알림. 선택한 메일 id를 함께 보내 "이거"를 해석하게 한다 |
| `src/features/voice/` | 음성 입력 버튼. `adapters/`에 browser(Web Speech API) · server(백엔드 STT) 두 방식(D29) |
| `src/components/` | 공용 UI (버튼 · 칩 · 토스트 · 패널 · 확인창) |
| `src/api/` | 백엔드 호출 함수 (화면에서 fetch를 직접 쓰지 않는다) · 모의 데이터 · 응답 변환 |
| `src/styles/` | 디자인 토큰 · 글꼴 · 공통 스타일 |

- 시안 원본: `docs/20_frontend/ui_reference/final_dashboard_wireframe.html`
- 음성 · 글 지시는 모두 `features/agent`로 들어간다. 음성은 글자로 바뀐 뒤 같은 길을 탄다.
- 버튼으로 바꾼 상태와 에이전트가 바꾼 상태는 같은 API · 같은 화면 갱신을 탄다. 행동 실행 직후 대시보드 숫자를 다시 불러온다.
- 웹 푸시는 HTTPS에서만 동작한다. iOS는 홈 화면에 설치했을 때만 받는다.
