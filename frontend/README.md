# frontend

CNE 웹 화면이다. 대시보드 · 메일 · 캐치봇 · 캘린더 · 설정을 React + Vite + TypeScript로 만든다. 화면은 같은 출처의 `/api/...`만 부르고 ai 서비스를 직접 부르지 않는다.

← [루트 README](../README.md) · 기준 문서: [구조도](../docs/00_common/architecture.md) · [디자인 시스템](../docs/20_frontend/design_system.md) · [와이어프레임](../docs/20_frontend/wireframe.md) · [FE 결정](../docs/20_frontend/decisions.md)

<img src="../docs/assets/screenshots/mail.png" alt="메일 화면 — 메일함 · 목록 · 본문 3단, 본문 위에 업무 카드" width="800">

## 요구 사항

| 도구 | 버전 | 근거 |
|---|---|---|
| Node.js | **22.22 이상** | `package.json` engines `>=22.22.0`. 테스트가 Node의 TS 타입 제거 기능을 쓴다. 루트 `.nvmrc`는 `22`라 낮은 22.x를 막지 않으니 `node -v`로 확인한다 |
| npm | 10 | `.npmrc`의 `engine-strict=true` — 버전이 맞지 않으면 설치가 멈춘다 |

## 실행

```bash
cd frontend
npm ci                                  # package-lock.json 그대로 설치 (CI와 같다)
npm run dev -- --port <배정 포트>        # http://127.0.0.1:<포트>. 쓰이고 있으면 다른 포트로 넘어가지 않고 멈춘다(strictPort)
```

- backend · ai까지 한 번에 띄우려면 루트에서 `python scripts/run_dev.py`.
- 공용 개발 서버에서는 `--port`에 내 계정 포트(`echo $PORT`)를 넣는다. 빼면 Vite 기본값 5173을 써서 다른 사람과 겹칠 수 있다.
- 원격 서버에서 띄우면 VS Code Remote SSH의 Ports 탭에서 그 포트를 전달한다. 개발 서버는 `127.0.0.1`에만 열린다(`vite.config.ts`).

## 테스트 · 검사

```bash
npm run typecheck       # 타입 검사
npm run build           # 타입 검사 + 프로덕션 빌드(dist/)
npm test                # node --test "src/**/*.test.ts" — 집계 · 기한 · 응답 변환 · 에이전트 · 색 대비 등
npm run mock:check-v2   # 모의 데이터가 원본에서 다시 만든 결과와 같은지 (v1은 mock:check)
npm run tokens:check    # 디자인 토큰 내보내기 파일이 tokens.css와 같은지
```

- 테스트는 실행 환경 시간대와 무관해야 한다. `TZ=UTC npm test` · `TZ=Asia/Seoul npm test` 둘 다 통과해야 한다.
- CI `frontend 검사 · 빌드` 단계는 `npm ci` → lint(있으면) → build → test 순서다.

## 설정

`frontend/.env.example`을 `frontend/.env`로 복사한다. `VITE_` 값은 빌드 결과에 그대로 들어가므로 **비밀값을 넣지 않는다**.

| 변수 | 기본값 | 뜻 |
|---|---|---|
| `VITE_API_MODE` | `mock` | `mock`: 모의 데이터(`src/api/mock/`). `http`: backend를 부른다. 그 밖의 값은 설정 오류로 화면에 알린다 |
| `VITE_API_BASE` | `/api` | backend 주소 앞부분 |
| `VITE_USER_ID` | `1` | `AUTH_MODE=header`일 때 `X-User-Id`로 붙는 사용자 번호. `AUTH_MODE=session`(배포)에서는 `POST /api/session` 쿠키를 쓴다 |
| `VITE_MOCK_DATASET` | `v2` | 모의 모드 데이터 묶음(`v2` \| `v1`) |
| `VITE_STT_MODE` | (빈 값 = 브라우저) | 음성 인식 방식. 지금은 브라우저 Web Speech API만 있다(`features/voice/adapters/browserStt.ts`) |
| `BACKEND_PROXY_TARGET` | `http://127.0.0.1:8000` | 개발 서버 프록시가 `/api/...`를 넘길 backend 주소. `/api/health`만 `/health`로 바꾼다 |

- 모의 모드 상태 미리보기: 주소에 `?mock=loading` · `mock=empty` · `mock=error`를 붙인다(`/#/dashboard?mock=error`처럼 해시 안에 둬도 되고, 둘 다 있으면 해시 안 값이 이긴다). `http` 모드에서는 읽지 않는다.
- `http` 모드에서 실패하면 오류 화면을 보이고 모의 데이터로 대신하지 않는다. 오류 문구는 네트워크 · HTTP · 형식 · 설정 오류로 나눈다(`src/pages/dashboard/errorText.ts`).

## 화면

| 경로 | 화면 | 페이지 |
|---|---|---|
| `#/dashboard` | 업무 수(오늘 · 이번 주 · 날짜) · 응답 대기 · 긴급 · 즐겨찾기 · 회신 · 요청 · 검토 · 기타 칸 | `pages/dashboard/` |
| `#/mail/:box/:mailId` | 메일함 · 목록 · 본문 3단, 업무 카드 · 근거 문장 · 요약 · 번역, 답장 · 전달 · 예약 발송, 답장 뒤 완료 확인(D48) | `pages/mail/` |
| `#/agent/*` | 캐치봇: 대화 · 업무 요약 · 회고 · 기록 · 리마인더 묶음 | `pages/agent/` |
| `#/calendar` | 월 보기 — 업무 기한 · 메일 속 회의 · 미룬 업무 · Outlook 일정 | `pages/calendar/` |
| `#/settings/:section` | 내 정보 · 메일 계정(Outlook 연결) · 알림 · 근무 · 방해 금지 · 메일 · 답장 템플릿 · 화면 | `pages/settings/` |

- 라우터는 `src/app/router.tsx`(해시 라우터). 모르는 경로는 대시보드로 보낸다.
- 위쪽 바(`src/app/TopBar.tsx`): 대시보드 · 캐치봇 · 캘린더 · 메일 · 설정 · 알림 센터(`features/notifications/NotificationBell.tsx`). `Ctrl+J`는 캐치봇으로 간다.

## 폴더

```
src/
├── app/          라우터 · 공통 레이아웃 · 위쪽 바 · QueryClient
├── pages/        경로마다 한 폴더 (dashboard · mail · agent · calendar · settings)
├── features/     화면을 가로지르는 기능
│   ├── tasks/          업무 행 · 상태 변경(완료 · 나중에 · 제외 · 되돌리기) · 집계 · 기한 판정
│   ├── mail/           목록 · 본문 · 작성 · 근거 문장 · 단축키 · 답장 후 완료 확인
│   ├── agent/          캐치봇 입력 · 결과 카드 · 진행 단계 · 기록
│   ├── reminders/      리마인더 목록 · 상세 · 버튼 · 브리핑
│   ├── notifications/  알림 센터 · 브라우저 알림
│   ├── calendar/       달력 모델 · 일정 넣기
│   └── voice/          음성 입력 (adapters/browserStt.ts)
├── api/          backend 호출(화면에서 fetch를 직접 쓰지 않는다) · 응답 변환(adapter.ts) · 세션 · mock/
├── ui/           공용 컴포넌트 (Button · Chip · DueLabel · Menu · Sheet · Toast …)
├── lib/          단축키 · 미루기 시각 · 토스트 문구 · 모션
└── styles/       디자인 토큰(tokens.css) · 테마 · 대비 테스트
```

## 규칙

- **응답 변환은 `src/api/adapter.ts` 한 곳에서** 한다. 시간대가 없는 시각은 오류로 거절한다(D47 `+09:00`). 업무가 가리키는 메일이 응답에 없으면 '메일 정보 확인 필요'로 따로 보인다.
- **버튼과 캐치봇은 같은 길을 탄다.** 같은 API · 같은 화면 갱신을 쓰고, 행동 직후 대시보드 숫자를 다시 불러온다.
- **상태 변경 토스트는 `features/tasks/useTaskActions.ts` 한 곳에서** 띄운다. 문구는 `lib/toastPolicy.ts`('~해요' 체). 성공은 [되돌리기] 버튼과 함께 8초, 실패는 연결 실패 · 시간 초과 · 서버 오류일 때만 [다시 시도]. 자기 결과 줄이 있는 화면(캐치봇 카드 · 기록)은 `{ toast: false }`로 부른다.
- **색은 `src/styles/tokens.css`(`--c-*`) 한 곳에서** 관리한다. 포인트 LG Heritage Red `--c-point`(#A50034)는 채운 주 버튼 · 에이전트 버튼 · 선택 표시선에만 쓴다. 글자 4.5:1 · 상태 표시 3:1 대비는 `styles/contrast.test.ts`가 검사한다. 값 · 근거는 [design_system.md](../docs/20_frontend/design_system.md).
- **글꼴은 빌드에 포함**한다: Pretendard Variable(본문) · Outfit Variable(영문 · 숫자), 둘 다 SIL OFL 1.1. 고지는 `public/licenses/`.

## 배포

`Dockerfile`이 Node 22로 빌드(`VITE_API_MODE=http`)한 뒤 Caddy 이미지에 담는다. `Caddyfile`은 `/api/*`를 `{$BACKEND_URL}`로 넘기고 나머지는 화면 빌드 결과(SPA)로 응답한다. Railway `web` 서비스 설정은 [infra/railway_setup.md](../infra/railway_setup.md).
