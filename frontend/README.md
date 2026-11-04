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
| `VITE_API_MODE=mock` (기본, 비워도 mock) | `src/api/mock/dashboard.v1.json`을 읽는다. 주소에 `?mock=loading` · `?mock=empty` · `?mock=error`를 붙이면 그 상태를 볼 수 있다 |
| `VITE_API_MODE=http` | `VITE_API_BASE`(기본 `/api`) + `/dashboard`를 부른다. 실패하면 오류 화면을 보이고 모의 데이터로 대신하지 않는다 |

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

## 디자인 (FE-1 · 문규남 제안 가이드)

`src/styles/tokens.css`. D21의 LG RED(`#A50034`) 제안보다 이 가이드를 우선한다.

| 토큰 | 값 | 쓰는 곳 |
|---|---|---|
| `--color-primary` | `#FF6000` | 주요 버튼 · 선택 메뉴 · 강조 |
| `--color-surface` | `#F9F9F9` | 카드 · 목록 배경 |
| `--color-text` | `#1C1C1C` | 제목 · 본문, 오렌지 · 노랑 위 글씨 |
| `--color-background` | `#F2EDE6` | 페이지 배경 |
| `--color-accent` | `#FFE066` | 보조 강조 · 주의 표시(뜻은 ⚠ · 글자로 전한다) |

- 오렌지 위 흰 글씨, 밝은 배경 위 오렌지 글씨를 쓰지 않는다. 선택 · 포커스는 검정 밑줄 · 체크 · 검정 포커스 링을 함께 쓴다. 실제 대비는 `src/styles/contrast.test.ts`가 검사한다.
- 글꼴(모두 빌드에 포함, SIL OFL 1.1, 고지는 `public/licenses/`): 한글 제목 SUITE Variable(공식 릴리스 v2.0.4 파일), 한글 본문 Pretendard Variable(npm `pretendard`), 영문 Montserrat Variable(npm `@fontsource-variable/montserrat`, Gotham은 사용 권한 미확인).

## 후속 작업 (화면에는 작업 번호를 적지 않고 '준비 중'으로만 보인다)

| 화면 · 기능 | 작업 |
|---|---|
| 업무 완료 처리 · 되돌리기 · 일괄 처리 | FE-4 |
| 메일 화면 · 원본 메일 보기 · 답장 · 답장 후 완료 확인 팝업(D48) | FE-5 |
| 설정 화면 | FE-6 |
| 에이전트 명령 연결 · 실행 전 확인 카드 | FE-7 |
| 모의 데이터 → 실제 API 연결(대시보드 API는 BE-3, 계약 비교 `docs/20_frontend/be3_contract_comparison.md`) | FE-9 · BE-3 |
| 알림 센터 목록 · 알림 수 | 알림 API 연결 뒤(담당 미정) |

## 폴더

| 폴더 | 내용 |
|---|---|
| `src/app/` | 라우터 · 공통 레이아웃(상단 바: 대시보드 \| 메일 \| 설정, 알림 센터 진입점, ✦ 에이전트 버튼) · 전역 상태 · PWA(서비스 워커 · 웹 푸시 구독). 캘린더 메뉴는 FE-1에서 넣지 않았다 |
| `src/pages/dashboard/` | 요약 줄(완료율 · 미처리 · 기한 임박 · 응답 대기 · 최근 행동) + 세로 2열 업무 칸(우선 확인 · 업무 성격: 회신 · 요청 · 검토 · 기타) (D20 · D39 · D40) |
| `src/pages/mail/` | Outlook 3단(계정 · 즐겨찾기 메뉴, 메일 목록, 미리보기), 여러 계정 통합, 응답 대기 목록(경과일) |
| `src/pages/calendar/` `[P1]` | 월 · 주 보기. 기한 · 나중에 업무, 날짜 클릭 → 업무 목록 → 메일 미리보기 |
| `src/pages/settings/` | 내 정보 · 메일 연동(본문 읽기 on/off) · 알림(리마인드 주기 · 조용한 시간 · 무응답 기준일 · 웹 푸시, iOS 설치 안내) · 템플릿 · 화면 · AI 에이전트 |
| `src/features/tasks/` | 업무 카드 · 상태 버튼(완료 · 나중에 · 제외 · 되돌리기) · 일괄 처리 · 되돌리기 토스트 · 회신 후 완료 확인 팝업(D23) |
| `src/features/mail/` | 메일 표시 · 답장 작성 |
| `src/features/notifications/` | 알림 센터(리마인더 목록) · 웹 푸시 권한 요청 |
| `src/features/settings/` | 설정 항목별 폼, 개인정보 동의 화면 |
| `src/features/agent/` | 에이전트 패널(360px): 입력창 · 결과 카드 · 확인창(확인이 필요한 행동만, D37) · 되돌리기 알림. 선택한 메일 id를 함께 보내 "이거"를 해석하게 한다 |
| `src/features/voice/` | 음성 입력 버튼. `adapters/`에 browser(Web Speech API) · server(백엔드 STT) 두 방식(D29) |
| `src/components/` | 공용 UI (버튼 · 칩 · 토스트 · 패널 · 확인창) |
| `src/api/` | 백엔드 호출 함수 (화면에서 fetch를 직접 쓰지 않는다) · 모의 데이터 · 응답 변환 |
| `src/styles/` | 디자인 토큰 · 글꼴 · 공통 스타일 |

- 시안 원본: `docs/20_frontend/ui_reference/final_dashboard_wireframe.html`
- 음성 · 글 지시는 모두 `features/agent`로 들어간다. 음성은 글자로 바뀐 뒤 같은 길을 탄다.
- 버튼으로 바꾼 상태와 에이전트가 바꾼 상태는 같은 API · 같은 화면 갱신을 탄다. 행동 실행 직후 대시보드 숫자를 다시 불러온다.
- 웹 푸시는 HTTPS에서만 동작한다. iOS는 홈 화면에 설치했을 때만 받는다.
