# 조사 정리 · 프론트 벤치마킹 — 화면 부품 · 피그마 · 참고 구현 (2026-11-12)

> 성격: 기록 · 작성: 문규남 · 조사일: 2026-11-12(모든 출처 이날 접속, 버전 · 날짜는 npm 레지스트리 · GitHub 원문으로 확인)
> 결론이 이어지는 곳: `../../20_frontend/decisions.md` UX-D17 · FE-D15 ~ FE-D19, `../../20_frontend/components.md`, `../../20_frontend/plan.md`
> 표시: 공식 문서 · 소스로 확인하지 못한 것은 '미확인'으로 적었다.

## 한눈에 보는 결론

1. **화면 부품은 Base UI 위에 우리 토큰으로 만든다.** 필요한 부품 15개 중 13개가 한 라이브러리에 있고, 토스트 요구를 설정만으로 맞추며, 한글 조합 중 Esc를 막아 준다.
2. **더 넣는 라이브러리는 세 개뿐이다.** React Router 8(주소 · 뒤로 가기), TanStack Query 5(불러오기 · 되돌리기), Lucide(아이콘). Tailwind · shadcn · AI 채팅 라이브러리는 넣지 않는다.
3. **한국 디자인 시스템은 그대로 쓸 수 있는 것이 없다.** 줄 간격 · 날짜 표기 같은 규칙만 빌려 온다.
4. **피그마는 무료 요금제 · 보기 좌석이라 그리기 도구를 쓸 수 없다.** 대신 구현 화면을 피그마로 캡처하는 기능은 무료이고 횟수 제한도 없다. 그래서 코드를 원본으로 두고 피그마는 확인용 사본으로 쓴다.
5. **토큰은 표준 형식(DTCG 2025.10) JSON으로 고정 기록을 남기고, 테스트로 지킨다.** 피그마에는 같은 JSON을 변수로 가져온다.

## 1. 왜 조사했나

화면 설계(UX v3.1 · v3.2)는 끝났지만 구현은 골격과 토큰에 머물러 있다. 남은 화면에는 아래 시트 · 오른쪽 패널 · 알림 센터 팝업 · 토스트 · 메뉴 · 탭이 많고, 이것들을 접근성(키보드 · 화면 읽기 · 포커스 복귀)까지 맞춰 손으로 만드는 일이 가장 오래 걸린다. 그래서 가져다 쓸 수 있는 오픈소스 부품 · 피그마 키트 · 참고 구현을 찾았다.

조건은 네 가지였다. 디자인 토큰은 고정이라 라이브러리가 자기 모양을 강요하면 안 된다. 스타일은 Tailwind 없이 순수 CSS다. React 19 · Vite 8 · TypeScript 6에서 돌아야 한다. 라이선스는 MIT · Apache-2.0 · ISC여야 하고, 2주 이상 지난 판을 고정해 쓴다.

## 2. 화면 부품 라이브러리 — Base UI를 고른 이유

아래 표는 겉모습이 없는(헤드리스) 부품 라이브러리 다섯 개를 우리 조건으로 비교한 것이다. 크기는 우리가 쓸 부품만 불러와 압축한 값이다(React 제외).

| 라이브러리 | 최신 판(날짜) | 라이선스 | 우리에게 없는 부품 | 한글 조합 중 Esc | 크기 | 관리 |
|---|---|---|---|---|---|---|
| **Base UI** | 1.9.0 (10-09), 1.0은 2025-12 | MIT | 날짜 고르기 · 칸 폭 끌기 | 막아 준다(소스 확인). 단 글자를 친 직후 첫 Esc가 무시되는 문제 #6158 열림 | 115KB(드로어 · 토스트 포함) | MUI, 1.0 뒤 거의 매달 |
| Radix | radix-ui 1.8.1 (10-12) | MIT | 드로어 · 날짜 · 칸 폭 끌기, 토스트 개수 제한 | 막지 않는다(소스에 확인 없음) | 53KB | 활발 |
| React Aria | 1.22.1 (10-09) | Apache-2.0 | 토스트가 아직 시험 단계, 시트는 10-08에 처음 나옴 | 관련 문제가 보고됐다가 모두 고쳐짐 | 101KB | Adobe |
| Ark UI | 5.40.0 (10-29) | MIT | 없음(드로어가 미리보기 단계) | 막아 준다 | 87KB | 6.0 큰 변경 진행 중 |
| Headless UI | 2.2.10 (04-07) | MIT | 토스트 · 툴팁 · 토글 그룹 · 드로어 · 날짜 | — | 49KB | 4월 이후 멈춤 |

Base UI를 고른 이유는 다섯 가지다.

- 필요한 15개 가운데 13개가 한 라이브러리에 있다. 다른 라이브러리는 드로어나 토스트를 따로 만들어야 한다.
- 가장 까다로운 토스트 요구(되돌리기 8초 · 최대 3개 · 마우스나 포커스가 있으면 멈춤 · 오류만 경고로 읽힘)를 설정만으로 맞출 수 있다. 최대 개수 기본값이 3이고, 포커스가 들어가면 타이머가 멈추며, 중요도를 높이면 경고로 읽힌다(소스 확인). 기본 표시 시간 5초를 되돌리기에서만 8초로 바꾸면 된다.
- 한글 조합 중 Esc를 눌러도 창이 닫히지 않게 라이브러리 안에서 막는다. Radix는 이 처리가 없어 우리가 직접 막아야 한다.
- 기본 모양이 전혀 없고, 등장 · 퇴장 상태를 속성으로 알려 줘 고정된 움직임 토큰(100 · 150 · 250 · 300ms, M3 곡선)을 그대로 쓸 수 있다.
- MUI가 운영하고 Radix · Floating UI를 만든 사람들의 후속작이다. shadcn/ui와 구름 Vapor UI가 이 위에 올라가 있어 시연 뒤에도 계속 쓸 수 있다.

차선책은 Ark UI다. 칸 폭 끌기와 날짜 고르기까지 있지만 드로어가 아직 미리보기 단계이고 6.0 큰 변경이 진행 중이다. React Aria를 Base UI와 섞어 쓰면 바깥 누르기 · Esc · 포커스를 두 라이브러리가 따로 관리해 충돌할 수 있으므로 섞지 않는다.

### 우리 환경에서 조심할 점

- Node는 `.tsx`(JSX)를 바로 실행하지 못한다(로컬 22.23.2에서 확인). 반면 `.ts`에서 Base UI를 불러오는 것은 화면 없이도 된다. 그래서 판단은 `.ts`로 떼어 시험하고 화면 동작은 점검표로 본다(FE-D18).
- 앱이 직접 다는 단축키는 라이브러리가 지켜 주지 않는다. 전역 키 처리에서 한글 조합 중인지 직접 확인해야 한다.
- 앱 바탕에 `isolation: isolate`가 필요하다(Base UI 빠른 시작 안내).
- Base UI가 React 19.3을 따로 검증했다는 기록과 TypeScript 6과의 타입 호환은 확인하지 못했다(미확인). 기반 작업 첫날 빌드로 확인한다.

## 3. 토스트 · 시트 전용 라이브러리 — 넣지 않는다

- **Sonner 2.0.8**(MIT): 불러오는 순간 전역 스타일(겹침 순서 999999999 · 0.4초 전환)을 넣고, 모양을 끄는 설정으로도 빠지지 않는다. 마우스에는 멈추지만 Tab으로 포커스가 들어갈 때는 멈추지 않는다. 알림 영역이 하나라 오류만 경고로 읽히게 할 수 없고, 기본 접근성 문구가 영어다(소스 확인).
- **Vaul**: 저장소 설명에 "This repo is unmaintained."라고 적혀 있다. 마지막 판은 1.1.2(2024-12).
- 브라우저 기본 `<dialog>` + `@starting-style`: 기술적으로는 되지만 한글 조합 중 Esc · 스크롤 잠금 · 포커스 복귀를 우리가 검증해야 해서 시간이 줄지 않는다.

## 4. shadcn/ui · Tailwind — 넣지 않는다

shadcn/ui는 공식 문서에 "Tailwind CSS를 설치해야 한다"고 적혀 있고, 모든 모양이 Tailwind 클래스 문자열이다(2026-01부터 Base UI 판 문서도 있다). Tailwind 없이 쓰려면 클래스 문자열을 전부 우리 CSS로 다시 써야 하고, 그러면 남는 것은 부품을 조합하는 방식뿐인데 그것은 Base UI 문서에도 있다. Tailwind v4로 우리 토큰을 연결하는 것 자체는 되지만, 기본 리셋이 함께 들어오고 스타일 체계가 둘로 갈라진다. 셋업 반나절~하루에 부품마다 다시 맞추는 비용이 들고 얻는 것이 거의 없다. 그래서 shadcn의 Base UI 판 문서는 조합 예시로 읽기만 한다.

## 5. 한국 디자인 시스템 — 규칙만 빌려 온다

| 이름 | 최신 판 · 라이선스 | 그대로 쓰지 않는 이유 | 빌려 올 것 |
|---|---|---|---|
| 구름 Vapor UI | 1.7.0 (10-23) · MIT | Base UI 위에 vanilla-extract(CSS-in-JS)로 구름 모양을 입혔다 | 한국 회사가 Base UI를 기반으로 택했다는 점(우리 선택의 근거) |
| 당근 SEED | 3.1.0 (10-29) · Apache-2.0 | 휴대폰 앱 중심이고 8월 이후 판이 20번 바뀌었다 | — |
| KRDS(정부 디자인 시스템) | krds-uiux 1.1.0 · 오픈소스 라이선스 아님(이용약관, 행정안전부 저작권) | React 코드가 없다 | 모든 글자 스타일 줄 간격 150% 이상, 굵기 3~4종, 제목 · 본문 크기 비율 1.25~1.5배 |
| 원티드 Montage | 4.3.1 (11-10) · MIT(브랜드 자산 제외) | Emotion(CSS-in-JS) 위에 만들어졌다 | 날짜 고르기의 한국식 표기 |

- 날짜 표기: 국립국어원 문장 부호 규정은 숫자만으로 쓴 날짜를 `2026. 11. 12.`처럼 쓴다(2차 자료로만 확인). 브라우저의 한국어 날짜 기본 형식도 같다.
- 문구: 토스의 '8가지 라이팅 원칙'(다음 화면 힌트 주기 · 의미 없는 말 빼기 · 쉬운 말 · 강요 대신 제안 등)이 공개 자료로 있고, 우리 문구 규칙(design_system 5절)과 방향이 같다.

## 6. 보조 라이브러리

| 이름 | 판(날짜) | 라이선스 | 판단 |
|---|---|---|---|
| **react-router** | 8.5.1 (10-27) | MIT | **넣는다.** 해시 라우터 · 이동 막기(쓰던 답장)가 있다. 8.0은 2026-06 출시, `react-router-dom` 패키지가 없어졌고 Node 22.22 이상 · React 19.2.7 이상이 필요하다 |
| **@tanstack/react-query** | 5.105.0 (10-26) | MIT | **넣는다.** 먼저 화면을 바꾸고 실패하면 되돌리는 흐름, 실행 뒤 다시 불러오기 |
| **lucide-react** | 1.63.0 (10-28) | ISC | **넣는다.** bell · sparkles · mic · check · clock · star · building · calendar · panel-left · undo 모두 있다. 계급장 모양은 없어 Tabler의 `military-rank` 그림 하나만 복사(MIT 고지) |
| TanStack Router | 1.170.46 (10-22) | MIT | 익히는 데 시간이 들어 보류 |
| wouter | 3.13.0 (09-30) | Unlicense | 작지만 사내 라이선스 정책 확인이 필요해 보류 |
| react-resizable-panels | 4.15.1 (10-28) | MIT | 메일함 · 목록 폭이 정해져 있어 CSS 격자로 충분. 최근 2주 사이 판이 여러 번 바뀜 |
| TanStack Virtual | 3.14.23 (10-26) | MIT | 수백 통 규모라 필요 없다. 쓰면 줄 빠짐 움직임 · 키보드 이동 · 찾기가 복잡해진다 |
| cmdk | 1.1.1 (2025-03) | MIT | 선택 기능이고 마지막 판이 20개월 전 |
| FullCalendar | 7.1.3 (10-16) | 표준 보기 MIT, 타임라인 등은 유료 | 캘린더(FE-12) 때 다시 본다. 7.0이 6월에 나온 새 큰 판 |
| Schedule-X · react-big-calendar | 4.x · 1.20.0 | MIT(유료 기능 따로) | 넣지 않는다 |
| date-fns · Temporal | 4.4.0 · 브라우저 내장 | MIT | 넣지 않는다. `Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul' })`로 충분하고 한국은 서머타임이 없다. Temporal은 사파리 정식판에 아직 없다 |

## 7. 화면별 참고 구현 (동작만 빌린다)

**메일 3단.** shadcn/ui의 메일 예제(MIT)는 2025-10-29에 저장소에서 지워졌다. 마지막 소스에서 메일함이 접히면 아이콘 줄로 남는 구조, 안 읽은 점 표시는 참고할 만하지만, 고른 메일을 전역 상태에만 둬서 주소 · 뒤로 가기가 안 되고 줄을 ↑ ↓로 이동할 수 없다. 오픈소스 메일 앱 Zero(MIT)는 고른 메일을 주소에 담아 링크 · 뒤로 가기를 해결하고, 단축키를 영역별(전역 · 목록 · 읽기 · 쓰기)로 나눈다. 이 두 가지를 따른다. Inbox Zero는 AGPL-3.0에 상업적 이용 금지 조항이 더해져 있어 '답장할 메일과 답을 기다리는 메일을 함께 추적한다'는 생각만 참고한다.

**에이전트 패널.** Vercel AI Elements(Apache-2.0)는 단계 표시(완료 · 진행 · 대기) · 확인(요청 · 승인 · 거절) · 할 일 목록을 상태별로 나눈 구조가 우리 UX-D8과 그대로 맞는다. 다만 Tailwind · shadcn · AI SDK를 전제로 하고 2026년 11월 말 폐기 예정이라 구조만 참고한다. assistant-ui(MIT)는 스트림이 아닌 JSON 응답도 붙일 수 있지만 채팅 스레드 중심이라 우리 '명령 → 계획 → 확인 → 결과' 흐름과 맞지 않는다. prompt-kit · CopilotKit도 각각 shadcn CLI · 에이전트 백엔드를 전제로 해서 넣지 않는다. 결론적으로 단계 줄 · 확인 카드 · 결과 카드 · 예시 칩 · 마이크 버튼 다섯 개를 직접 만든다.

**업무 완료 · 되돌리기.** 할 일 앱 Vikunja(AGPL-3.0, 동작만 관찰)는 체크하는 순간 서버에 먼저 보내고 움직임만 300ms 늦춰 보여 주며, 되돌리기는 반대 요청으로 보낸다. Zero는 반대로 토스트가 닫힐 때 서버에 보내는데, 이 방식은 탭을 닫으면 동작이 사라진다. 우리 백엔드에는 되돌리기 API(BE-4)가 이미 있으므로 Vikunja 방식을 택했다.

**음성 입력.** 브라우저 음성 인식은 크롬 139 이상 · 파이어폭스 160 이상(11-10 출시)이 지원하고 사파리는 접두사 형태다. 기본 설정에서는 소리가 외부 서버로 가며, 기기 안에서 처리하는 설정의 브라우저별 지원은 확인하지 못했다(미확인). 사내 시연이라 보안 검토가 필요하다.

## 8. 피그마 — 무엇을 할 수 있고 무엇을 들일까

**이 계정으로 할 수 있는 일과 없는 일.** 계정은 무료(Starter) 요금제 · 보기(View) 좌석이다.

- 피그마 연동 도구의 읽기 호출은 한 달 20번이다(공식 문서 · 9월 직원 답변. GitHub 안내서의 '월 6회'는 옛 값). 새 파일 만들기 · 화면 캡처 · 코드 연결 등록 · 계정 확인은 횟수에 들어가지 않는다.
- 캔버스에 직접 그리는 도구(컴포넌트 · 변수 만들기)는 Professional 이상 요금제에서만 된다. 변수를 만드는 전용 도구도 없어 연동 도구로는 변수를 만들 수 없다.
- 실행 중인 화면을 피그마로 캡처하는 도구는 무료 요금제에서도 되고 횟수 제한 밖이다. 결과는 부품 연결이 없는 평평한 레이어이고, 파일에 변수가 있으면 색 · 숫자를 변수에 이어 준다.
- 커뮤니티 파일 복제는 연동 도구 · REST API 모두 안 된다. 브라우저에서 'Open in Figma'를 누르는 방법뿐이다.
- 무료 요금제에서 로컬 변수는 만들 수 있지만 변수 모드 · 라이브러리 게시 · Dev Mode · Code Connect는 안 된다. 드래프트 파일 수는 제한이 없다.
- 보기 좌석으로 내 드래프트를 고칠 수 있는지는 확인하지 못했다(미확인, 피그마 화면에서 확인 필요).

**키트 비교.** 피그마 커뮤니티 무료 파일은 기본이 CC BY 4.0(상업적 이용 가능 · 출처 표기 필수)이다.

| 키트 | 라이선스 | 변수 | 대응하는 React 코드 | 우리 토큰과 맞춤 |
|---|---|---|---|---|
| Obra shadcn/ui 커뮤니티판 | CC BY 4.0(키트 라이선스 11절) | 있음 | shadcn/ui(Tailwind) | 중상 — 부품 55개, 메일 화면 블록은 유료판에만 |
| Radix Themes(비공식) | CC BY 4.0 | 미확인 | @radix-ui/themes | 중 |
| Untitled UI 무료판 | 상업 이용 가능, 경쟁 키트 제작 금지 | 최신 변수는 유료판에만 | Untitled UI React(Tailwind) | 중하 |
| Material 3 · Fluent 2 · Carbon | 각 공개 조건 | 있음 | 각자 라이브러리 | 하 — 자기 모양이 강하다 |
| KRDS | 명시 없음(미확인) | 미확인 | 없음 | 글자 규칙만 참고 |
| 원티드 Montage | MIT | 미확인 | montage-web | 중상 — 패턴 참고 |

**결론.** 키트를 통째로 들여도 무료 요금제에서는 라이브러리 게시 · 모드 · 코드 연결이 막혀 얻는 것이 거의 없고, 우리 코드는 shadcn이 아니라 이름을 결국 다 바꿔야 한다. 그래서 고정 토큰으로 우리 파일을 하나 만들고(기초 · 부품 · 화면 세 페이지), 부품 · 화면은 구현한 것을 캡처해 채운다. 피그마 쪽 부품이 꼭 필요하면 Obra 커뮤니티판에서 그 부품만 복사해 출처를 적고 우리 변수로 다시 칠한다.

**토큰 형식.** 디자인 토큰 표준 형식(DTCG)이 2025-10-28 첫 안정판(2025.10)으로 나왔다. 색은 `{색 공간 · 성분 · hex}` 객체, 길이는 px · rem, 시간은 ms · s로 쓴다. 피그마는 이 JSON을 변수로 가져오고 내보낼 수 있는데, 색 · px 길이 · 초 단위 시간 · 글꼴 이름 하나 · 숫자만 받고 곡선 · 그림자 · 글자 묶음은 받지 않는다. 이 기능이 무료 요금제에서 되는지는 확인하지 못했다(미확인). 안 되면 피그마 공식 예제 플러그인(variables-import-export)이나 손 입력으로 넣는다. Style Dictionary 5.8.0(11-03)은 이 형식을 읽어 CSS를 만들 수 있지만, 지금은 CSS를 원본으로 두는 편이 단순해 미룬다. Tokens Studio는 저장소 동기화가 유료라 택하지 않았다.

그래서 이렇게 한다. tokens.css를 원본으로 두고, 의존성 없는 스크립트가 표준 형식 고정 기록(`cne.tokens.json`)과 피그마용 파일(`cne.figma.tokens.json`, 시간은 초로 바꾸고 곡선 · 그림자는 뺌)을 만든다. 테스트가 세 파일이 같은지와 고정 기록의 해시가 design_system.md에 적힌 값과 같은지를 본다.

## 9. 라이선스 메모

- AGPL · GPL 계열(Inbox Zero · Vikunja · Plane · Twenty 핵심 · Mailspring)은 코드 조각도 복사하지 않고 동작만 관찰한다.
- Apache-2.0(AI Elements · React Aria · SEED)을 복사하면 고지와 변경 표시가 필요하다. 이번에는 복사하지 않는다.
- MIT · ISC(Base UI · React Router · TanStack · Lucide · Tabler 그림 하나)는 고지를 남긴다. 빌드에 들어가는 고지는 지금처럼 `frontend/public/licenses/`에 모은다.
- 피그마 커뮤니티 파일(CC BY 4.0)에서 가져온 것은 피그마 파일 안에 출처를 적는다.

## 출처 (모두 2026-11-12 접속)

- npm 레지스트리(판 · 날짜 · 라이선스 · 의존성): https://registry.npmjs.org/ 아래 `@base-ui/react` · `radix-ui` · `react-aria-components` · `@ark-ui/react` · `@headlessui/react` · `sonner` · `vaul` · `react-router` · `@tanstack/react-query` · `lucide-react` · `@tabler/icons-react` · `react-resizable-panels` · `@tanstack/react-virtual` · `cmdk` · `@fullcalendar/react` · `date-fns` · `@vapor-ui/core` · `@seed-design/react` · `@montage-ui/core` · `style-dictionary`
- 압축 크기: 필요한 부품만 불러와 esbuild 0.28.2로 직접 측정 · https://bundlephobia.com/
- Base UI: https://base-ui.com/react/overview/releases · https://base-ui.com/react/components/drawer · https://base-ui.com/react/components/toast · https://base-ui.com/react/overview/quick-start · https://github.com/mui/base-ui/issues/6158
- Radix: https://www.radix-ui.com/primitives/docs/overview/releases
- React Aria: https://react-aria.adobe.com/Toast · https://react-aria.adobe.com/Sheet · https://github.com/adobe/react-spectrum/issues/5921
- Ark UI: https://ark-ui.com/docs/components/drawer
- Sonner · Vaul: https://github.com/emilkowalski/sonner · https://github.com/emilkowalski/vaul
- shadcn/ui: https://ui.shadcn.com/docs/installation/manual · https://ui.shadcn.com/docs/changelog/2026-01-base-ui · https://ui.shadcn.com/docs/figma · 지워진 메일 예제 https://github.com/shadcn-ui/ui/tree/e7f8cd4566/apps/www/app/(app)/examples/mail
- Tailwind: https://tailwindcss.com/docs/theme
- 한국 디자인 시스템: https://github.com/goorm-dev/vapor-ui · https://github.com/daangn/seed-design · https://github.com/KRDS-uiux/krds-uiux · https://www.krds.go.kr/html/site/style/style_03.html · https://montage.wanted.co.kr/docs/getting-started/terms-of-use
- 문구 · 날짜: https://toss.tech/article/8-writing-principles-of-toss · https://sgsg.hankyung.com/article/2022032514861(2차 자료)
- React Router: https://reactrouter.com/api/data-routers/createHashRouter · https://reactrouter.com/api/hooks/useBlocker · https://github.com/remix-run/react-router/blob/main/packages/react-router/CHANGELOG.md
- TanStack Query: https://tanstack.com/query/latest/docs/framework/react/guides/optimistic-updates
- Lucide · Tabler: https://github.com/lucide-icons/lucide · https://github.com/tabler/tabler-icons
- 캘린더 · 날짜: https://fullcalendar.io/pricing · https://schedule-x.dev/premium · https://github.com/date-fns/tz · https://github.com/mdn/browser-compat-data(Temporal)
- 참고 구현: https://github.com/Mail-0/Zero · https://github.com/elie222/inbox-zero · https://github.com/go-vikunja/vikunja · https://github.com/vercel/ai-elements · https://elements.ai-sdk.dev/components/confirmation · https://github.com/assistant-ui/assistant-ui · https://www.prompt-kit.com/docs · https://docs.copilotkit.ai/
- 음성: https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API/Using_the_Web_Speech_API
- 피그마 연동: https://developers.figma.com/docs/figma-mcp-server/rate-limits-access/ · https://developers.figma.com/docs/figma-mcp-server/write-to-canvas · https://developers.figma.com/docs/figma-mcp-server/code-to-canvas/ · https://developers.figma.com/docs/figma-mcp-server/tools-and-prompts/ · https://help.figma.com/hc/en-us/articles/39252411778583-Figma-MCP-server-FAQs · https://forum.figma.com/ask-the-community-7/i-m-on-a-starter-plan-view-seat-and-reached-the-figma-mcp-tool-call-limit-when-does-my-mcp-allowance-reset-and-how-many-calls-have-i-used-58440
- 피그마 요금제 · 변수: https://help.figma.com/hc/en-us/articles/360040328273-Figma-plans-and-features · https://help.figma.com/hc/en-us/articles/15343816063383-Modes-for-variables · https://help.figma.com/hc/en-us/articles/15339657135383-Guide-to-variables-in-Figma · https://developers.figma.com/docs/rest-api/variables/ · https://help.figma.com/hc/en-us/articles/360042296374-Figma-Community-copyright-and-licensing
- 키트: https://shadcn-ui-kit.pages.dev/license · https://www.untitledui.com/legal/license · https://www.radix-ui.com/themes/docs/overview/resources · https://carbondesignsystem.com/designing/kits/figma/ · https://fluent2.microsoft.design/get-started/design
- 토큰 형식: https://www.w3.org/community/design-tokens/2025/10/28/design-tokens-specification-reaches-first-stable-version/ · https://www.designtokens.org/tr/2025.10/format/ · https://www.figma.com/blog/schema-2025-design-systems-recap/ · https://github.com/style-dictionary/style-dictionary/releases · https://tokens.studio/pricing · https://github.com/figma/plugin-samples/tree/main/variables-import-export
