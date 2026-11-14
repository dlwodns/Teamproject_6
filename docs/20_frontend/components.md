# 부품 명세 · CNE 프론트 v3.3

> 상태: 결정(FE-D15 ~ FE-D19 · UX-D17) · 작성: 문규남 · 갱신: 2026-11-12
> 무엇: 와이어프레임 13절의 화면을 어떤 부품으로, 어떤 라이브러리 위에, 어떤 토큰으로 만드는지 정한 구현 명세다. 화면을 만드는 사람은 이 문서와 와이어프레임 13절, `design_system.md`만 보면 된다.
> 화면 기준: `wireframe.md` 13절(v3.1 · v3.2) · 시안 `ui_reference/cne_v31.html` · 확인 표 13-9(V-1~V-27)
> 근거: `decisions.md` UX-D1 ~ UX-D17 · FE-D15 ~ FE-D19 · `../10_planning/refs/research_fe_benchmark_20261112.md`

## 1. 만드는 원칙

1. **겉모습은 고정 토큰으로만 칠한다.** 색 HEX · 글자 크기 · 모서리 · 그림자 · 시간을 CSS에 직접 쓰지 않는다(UX-D17, 테스트가 색 HEX를 막는다). 맞는 토큰이 없으면 가장 가까운 토큰을 쓰고, 새 토큰이 꼭 필요하면 결정부터 올린다.
2. **접근성이 까다로운 부품은 Base UI 위에 만든다**(FE-D15). 팝업 · 시트 · 토스트 · 메뉴 · 탭 · 체크 상자를 손으로 처음부터 만들지 않는다. 라이브러리 기본 테마는 없고, 열림 · 닫힘 · 선택 상태는 라이브러리가 붙여 주는 속성으로 칠한다.
3. **부품마다 CSS 모듈 하나**(FE-D17). `Button.tsx` 옆에 `Button.module.css`를 둔다. `global.css`에는 리셋 · 글꼴 · 포커스 링 · 동작 줄이기 · 화면 읽기 전용 글자만 남긴다.
4. **화면에 보이는 글자는 모두 한국어**이고 `design_system.md` 5절 문구 규칙을 따른다. 버튼은 일어날 일을 동사로("3건 완료 처리"), 결과는 과거형 한 줄("3건을 완료로 바꿨어요"), 빈 상태는 "없음", 오류는 "불러오지 못함 [다시 시도]"다. 라이브러리 기본 영어 문구(닫기 · Notifications 같은 접근성 이름)는 모두 한국어로 바꿔 넘긴다.
5. **판단은 `.ts`로 떼어 시험한다**(FE-D18). 기한 라벨, 집계, 단축키가 입력 중에 동작하지 않는지, 나중에 시각 계산, 토스트 규칙, 에이전트 응답 해석은 화면 부품 밖 `.ts` 파일에 두고 `node --test`로 시험한다.
6. **없는 기능을 있는 척하지 않는다.** 실제 서버 모드에서 아직 API가 없는 칸(응답 대기 · 리마인더 · 메일 본문 등)은 0건으로 보이지 않게 숨긴다. 서버가 응답하지 않으면 모의 데이터로 몰래 바꾸지 않고 오류를 보인다.

## 2. 폴더

```
frontend/src/
  app/            라우터 · 앱 틀(상단 바 · 패널 자리 · 토스트 자리) · 공급자(Query · 토스트)
  ui/             공통 부품(3절). 화면 지식이 없다. 이름.tsx + 이름.module.css
  lib/            화면 밖 판단(.ts, 시험 대상): 단축키 가드 · 토스트 규칙 · 나중에 시각 · 한국 시각 표시
  api/            모의 · 실제 서버 선택(있음), 응답 → 화면 모델 변환(있음), Query 훅
  features/       기능별 부품 · 판단: tasks · mail · agent · notifications · settings
  pages/          주소 하나에 화면 하나: dashboard · mail · settings
  styles/         tokens.css(고정) · global.css · 글꼴
```

## 3. 공통 부품 (`src/ui`)

이 표는 공통 부품 하나하나가 무엇을 바탕으로, 어디에 쓰이고, 어떤 모양 · 동작이어야 하는지를 보여 준다. '바탕'이 비어 있으면 HTML 요소로 직접 만든다.

| 부품 | 바탕 | 쓰는 곳(와이어프레임 코드) | 모양 (토큰) | 동작 · 상태 | 접근성 |
|---|---|---|---|---|---|
| Button | `<button>` | 모든 버튼 | 주: `--c-point` 채움 · 흰 글자, 마우스 올림 `brightness(0.9)`, 누름 `--c-point-press` / 보조: 흰 바탕 · `--c-input` 1px 테두리 · `--c-ink` 글자 / 투명: 테두리 없음 · 마우스 올림 `--c-fill`. 높이 36px(작게 28px) · `--r-ctl` · `--fs-14`(작게 `--fs-13`) `--fw-semibold` | 불러오는 중: 글자를 `visibility: hidden`으로 숨겨 **폭 유지** + 스피너를 위에 겹침(300ms 뒤에 보임). 끝나면 ✓(`--c-done-bar`) 0.7초. 한 영역에 주 버튼은 하나 | 불러오는 중에는 `disabled` 대신 `aria-disabled="true"`(포커스 유지), 상태 문구는 숨은 `aria-live="polite"` |
| IconButton | `<button>` | 🔔 · ✕ · ⋯ · [▥] · 🎤 | 32px 정사각 · 투명 버튼 모양 · 아이콘 20px `currentColor` | — | 접근성 이름 필수(예: "알림 센터 열기") + Tooltip |
| Chip | `<span>` | 플래그 칩(UX-D13) · 확인 사유 칩 · 분류 칩 | 높이 20px · `--r-chip` · `--fs-12` `--fw-semibold` · 좌우 6px. 플래그 · 분류: `--c-fill` 바탕 · `--c-ink` 글자 / 확인 사유: `--c-info-bg` · `--c-info` | 플래그 순서 상급자 → 즐겨찾기 → 거래처. 좁은 목록에서는 아이콘만 | 아이콘만 남길 때 `aria-label`("상급자") + Tooltip. 빨강 금지 |
| DueLabel | `<span>` | 업무 줄 `R` · 메일 줄 · 시트 | `design_system.md` 1절 기한 라벨 표(검정 · 파랑 · 초록 · 회색), 숫자 · 시각 `--font-display` · `tabular-nums` | 글자: `D+2` · `ASAP` · `오늘 18:00` · `내일 12:00` · `11/10(화)` · `기한 없음`, 메일 목록은 `완료` · `기한 지남`도. ASAP는 업무에 원문 기한(`due_raw`)이 있을 때만 | 숨은 글자로 '기한 지남 · 11/4(수) 18:00'처럼 전체를 읽힘, 마우스 올림 · 포커스 때 전체 시각 Tooltip |
| Checkbox | Base UI Checkbox | 업무 완료 ☐ · 시트 · 확인 카드 대상 | 18px · `--c-input` 테두리, 체크되면 `--c-ink` 채움 + 흰 ✓ (`--d-short`) | 업무 줄에서는 누르면 완료 요청(5절) | 이름은 업무 글자 |
| SegmentedControl | Base UI Toggle Group(하나만 선택, 비울 수 없음) | `N1` 기간 [오늘 \| 이번 주 \| 날짜] | 바탕 `--c-fill`, 선택된 칸은 흰 바탕 + `--shadow-1` + `--fw-semibold` | 즉시 바뀜(움직임 없음, UX-D9) | 선택은 색만이 아니라 굵기 · 그림자로 |
| Tabs | Base UI Tabs | `I1` [확인 \| 참고] · 알림 센터 [리마인더 \| 알림] | 분할 버튼과 같은 모양(카드 안 탭은 포인트 빨강을 쓰지 않는다) · 탭 옆 건수 | 즉시 바뀜 | 화살표 키로 탭 이동 |
| NavLink | React Router `NavLink` | 상단 바 메뉴 `T0` | 선택: `--c-ink` 글자 + `--fw-bold` + **포인트 2px 밑줄**(포인트를 쓰는 세 곳 중 하나) | — | `aria-current="page"` |
| Popover | Base UI Popover | 🔔 알림 센터 | 폭 `--popover-width` · `--r-card` · `--shadow-2` · `--z-popover`, 들어올 때 `--d-short` | 바깥 누르기 · Esc로 닫힘 | 여는 버튼으로 포커스 복귀 |
| Menu | Base UI Menu | [나중에 ▾] · ⋯ | `--r-ctl` · `--shadow-2` · `--z-menu`, 줄 높이 36px | 나중에 = 1시간 뒤 · 오늘 오후 4시 · 내일 아침(08:30) · 다음 주 월요일 09:00 · 직접 고르기(`<input type="date">` + 시각). 시각 계산은 `lib/snooze.ts` | 화살표 키 이동 · 글자로 찾기 |
| Select | Base UI Select | 답장 템플릿 · 보낸 계정 | 입력칸 모양: 높이 36px · `--c-input` 1px · `--r-ctl` | — | 이름 있는 `<label>` |
| Sheet | Base UI Drawer(모달) | 답장 후 완료 확인 `BS` | 840px 미만: 아래에 붙은 전체 폭 · 위 모서리 `--r-sheet` · 손잡이. 840px 이상: 바닥에서 24px 띄운 최대 `--sheet-max` · 손잡이 없음. 뒤 막 `--c-scrim`. 들어올 때 `--d-panel` `--e-in`, 나갈 때 `--d-exit` `--e-out` | 아니오 · Esc · 바깥 누르기 · 아래로 쓸어내리기는 모두 '아니오' 하나의 처리로 모은다 | 열리면 [예]에 포커스, Tab은 시트 안에서만, 닫히면 원래 자리로 |
| SidePanel | `<aside>` | 에이전트 `G`(폭 `--agent-width`) · 더보기 `LP`(폭 `--drawer-width`) | `--c-surface` · 왼쪽 `--c-line` 선 · `--shadow-2` · `--z-panel`, 들어올 때 `--d-panel` | **한 번에 하나만 열린다.** 1280px 이상은 본문이 밀려나고, 그보다 좁으면 본문 위에 겹치며, 720px 이하는 전체 폭. ✕ · Esc로 닫는다 | 배경 조작을 막지 않으므로 모달 속성 · 포커스 가두기를 쓰지 않는다. 열면 패널 제목으로, 닫으면 연 버튼으로 포커스 |
| Toast | Base UI Toast | 되돌리기 · 결과 · 오류 · 리마인더 | 오른쪽 아래, 최대 3개(넘으면 오래된 것부터 닫힘), `--z-toast`. 일반: `--c-ink` 바탕 · 흰 글자 · `--r-card`. 리마인더: 흰 카드 + `--c-remind` 아이콘 자리 | 정보 5초 · 되돌리기 8초 · 리마인더는 자동으로 사라지지 않음. 마우스 · 포커스가 있으면 멈춤(라이브러리 기본) | 오류만 경고(`priority: 'high'`), 나머지는 상태 알림. F6으로 토스트 영역 이동 |
| Tooltip | Base UI Tooltip | 아이콘 버튼 · 칩 · 기한 라벨 | `--c-ink` 바탕 · 흰 글자 `--fs-12` · `--z-menu` | 마우스 올림 · 포커스 때 | 보조 설명일 뿐, 이름은 버튼에 따로 |
| Collapsible | Base UI Collapsible | 에이전트 단계 목록 · '어떻게 해석했나요' | — | 진행 중 접힘, 실패하면 펼친 채 멈춤 | 여닫는 버튼에 `aria-expanded`(라이브러리) |
| StateRow | — | 모든 칸 · 카드(13-8) | 불러오는 중: 줄 모양 스켈레톤 3개(`--c-fill`), 건수 자리 '–'. 빈 상태: "없음" 한 줄. 오류: "불러오지 못함" + [다시 시도]. 분류 대기: `--c-info-bg` 안내 | 불러오기가 1초 안에 끝나면 스켈레톤을 띄우지 않는다(300ms 뒤에 보임) | 오류 줄만 `role="alert"` |
| CountBadge | `<span>` | 🔔 숫자 · 칸 제목 건수 | `--c-ink` 바탕 · 흰 글자 · `--font-display` | 10 이상은 `9+` | 버튼 이름에 숫자 포함("알림 센터, 리마인더 3개") |
| Avatar | `<span>` | 상단 바 사용자 · 보낸 사람 줄 | 32px 원 · `--c-fill` · 이름 첫 글자 | 사진 자리(사진 없음) | 장식이면 `aria-hidden` |
| Icon | lucide-react | 모든 아이콘 | 16 · 20px, `currentColor` | 상급자 계급장만 Tabler 그림 하나를 복사(고지) | 장식이면 `aria-hidden` |
| VisuallyHidden · LiveRegion | — | 숨은 설명 · 단계 문구 | — | — | 화면 읽기 전용 |

## 4. 화면 부품

### 4.1 앱 틀 — 상단 바 `T0` · 패널 자리 · 주소

- 상단 바(높이 `--topbar-height`): 로고 자리 · `CNE`(Outfit) · Catch & End · 메뉴 `대시보드 | 메일 | 에이전트 | 설정`(FE-D20, 캘린더는 FE-12에서 에이전트 앞에 더한다) · 동기화 시각 · 🔔(Popover + CountBadge) · **[✦ 에이전트]**(주 버튼, 포인트) · 사용자 Avatar. 840px 미만에서 동기화 · 로고 자리 · 브랜드 부제를 숨기고, 480px 이하에서 Avatar를 숨긴다(화면 폭 기준은 design_system 0절).
- FE-1의 왼쪽 사이드바와 오른쪽 아래 원형 에이전트 버튼은 지운다(FE-D12 · FE-D13 대체).
- 주소(해시 라우터, FE-D16):

| 주소 | 화면 |
|---|---|
| `#/dashboard` (`#/`도 여기로) | 대시보드 |
| `#/mail` · `#/mail/:box` · `#/mail/:box/:mailId` | 메일. `box`는 inbox · tasks · checks · superior · favorite · due · client · waiting · cat-회신 같은 메일함, `mailId`는 고른 메일 |
| `#/agent` | 에이전트 화면(FE-15 · FE-D20). 왼쪽 대화 · 오른쪽 결과물. 상단 바 에이전트 버튼 · 떠 있는 패널은 숨긴다 |
| `#/settings` | 설정(에이전트 버튼 · 패널 숨김) |

- 메일을 고르면 주소에 새 항목을 쌓고(뒤로 가기 대상), 필터 · 탭 같은 일시적인 바꿈은 주소를 바꾸지 않는다. 그래서 Alt+← · Alt+→ · 브라우저 뒤로 가기가 별도 코드 없이 같은 동작을 한다(UX-D12).
- 쓰던 답장이 있을 때 다른 화면으로 가면 "버릴까요? 예 / 아니오"를 묻는다(라우터의 이동 막기 기능).
- 패널 자리: 에이전트 · 더보기 중 하나만 열린다. 열린 패널 종류는 앱 상태로 두고 주소에는 넣지 않는다.

### 4.2 대시보드 (13-1 · 13-3, UX-D1 ~ UX-D3 · UX-D12)

| 코드 | 부품 | 데이터 · 규칙 |
|---|---|---|
| `N1` | CountCard | 메일을 받은 날 기준 전체 · 처리 · 미처리(= 미처리 + 나중에, 제외는 세지 않음). SegmentedControl 기간 + '날짜'일 때 ◀ 날짜 ▶. 큰 숫자 `--fs-40` Outfit. 처리 비율 막대(장식) `--c-done-bar`. 기간을 바꿔도 2열은 그대로 |
| `W1` | WaitingCard | 응답 대기(보낸 요청 메일 중 3일 이상 답 없음) + 회색 경과일 라벨 `4일`. 실제 서버 모드에서 API(BE-13)가 없으면 카드를 숨긴다 |
| `I1` | CheckItemsCard | Tabs [확인 \| 참고] + 기본 3건 + 더보기. 메일의 확인 · 참고 구분(lane)이 응답에 없으면 카드를 숨긴다 |
| `U1` | UrgentColumn | 미처리 중 기한 지남(오래된 순) → ASAP → 오늘 마감(시각 순), 기본 5건. 제목 앞 검정 점 |
| `Y1~Y4` | TypeColumn | 회신 · 요청 · 검토 · 기타, 미처리만, 기본 3건, 긴급과 중복 허용. 공지 분류인데 업무가 붙으면 기타(FE-D10) |
| `R` | TaskRow | ☐ · 업무 글자 · 새 업무 점(`--c-info-dot`, 숨은 글자 '새 업무') · 둘째 줄 발신자(긴급 칸은 + 유형) · 오른쪽 DueLabel. **줄을 누르면 메일 화면의 그 메일로**, 체크 상자는 이동하지 않는다 |
| `LP` | MoreDrawer (SidePanel) | 칸 이름 · 건수 + 그 칸 전부. 확인사항은 확인 · 참고 묶음. 안의 줄도 누르면 메일로 이동하고 패널은 닫힌다 |

**업무 완료의 움직임(UX-D9).** 체크 상자가 채워짐(`--d-short`) → 그 업무의 모든 줄(긴급 · 유형 칸에 중복된 줄 포함)이 오른쪽으로 빠지며 흐려짐(`--d-move`) → 높이가 접힘(`--d-exit`, `grid-template-rows: 1fr → 0fr`) → 건수 갱신 → 되돌리기 토스트 8초. 줄에는 `data-leaving` 속성을 붙여 CSS로만 움직인다. 동작 줄이기 설정이면 즉시 사라진다.

### 4.3 메일 (13-5 · 13-7, UX-D5 · UX-D6 · UX-D11 · UX-D13 ~ UX-D16)

| 위치 | 부품 | 규칙 |
|---|---|---|
| 왼쪽 220px | MailboxNav | 받은편지함 · 업무 · 확인사항 / 빠른 보기: 상급자 · 즐겨찾기 · 마감 · 거래처 · 응답 대기 / 분류 / 계정. 선택은 굵은 글씨 + 왼쪽 포인트 선. **Ctrl+B(⌘B) · [▥]로 열고 닫기** |
| 가운데 380px | MailList · MailRow | 위 막대: [▥] · 메일함 이름 · 건수 · [⌨ 단축키](누르거나 `?`로 단축키 도움말). 줄: 고르기 칸(안 읽음 파란 점, 마우스를 올리면 네모 상자) · 발신자 + 플래그 칩 · 시각 · 제목 · 라벨(분류 + '업무 N' / DueLabel / 초록 '완료' / 확인 사유 / 참고). 안 읽은 메일은 굵은 글씨 + 파란 점. ↑ ↓ 키로 줄 이동, Enter로 열기 |
| 목록 묶음 (FE-5d) | MailList | 고정됨(작은 핀) → 오늘 · 어제 · 이번 주 · 지난주 · 이전. 기준은 데이터 기준 시각(as_of) · KST, 주는 월요일 시작. 묶음 이름은 작은 회색 글자로 줄과 같은 왼쪽 선에 두고 굴려도 위에 붙는다(1024px 미만은 붙지 않음). 고정한 메일은 시각 앞에 핀 |
| 줄 빠른 동작 (FE-5d) | MailList QuickActions | 마우스를 올리거나 키보드 포커스가 들어오면 시각 자리 위에 아이콘만 겹쳐 보인다(자리 밀림 없음, 말풍선에 이름 · 단축키): [업무 완료](끝나지 않은 업무가 있을 때만, 2건 이상이면 완료 확인 시트) · [나중에 ▾] · [고정/고정 해제] · [읽음/안 읽음]. 그 줄에 Tab으로 이어 간다 |
| 읽음 · 고정 (FE-5d) | MailPage | 메일을 열면 읽음으로 바꾼다(Outlook 기본). 읽기 화면 ⋯ 메뉴 맨 위에 [안 읽음으로 표시] · [맨 위에 고정]. 메일함 건수 앞에 안 읽은 수(파란 숫자). 서버가 `read_at` · `pinned_at` 칸을 보내지 않거나 요청이 없으면(404 · 405 · 501) 이 동작을 모두 숨긴다 |
| 여러 통 고르기 (FE-5d) | MailList SelectionBar | 네모 상자 · Ctrl/⌘ 클릭으로 하나씩, Shift 클릭으로 범위. 하나라도 고르면 모든 줄에 상자가 보이고, 위 막대가 '☐ N통 선택 · [읽음] [안 읽음] [고정] [업무 완료 N건] [×]'로 바뀐다. 업무 완료는 2건 이상이면 완료 확인 시트를 거쳐 미리보기 → 실행(D37). 그냥 누르면 고르기를 끝내고 그 메일을 연다 |
| 오른쪽 | ReadingPane | 머리 순서(UX-D14): 제목 + [메일 요약] → 보낸 사람 줄(Avatar · 이름 · 주소 · 플래그 칩 · 받는 사람 · 날짜) → 오른쪽 위 [답장](주 버튼) · ⋯ Menu([나중에] · [제외]) → 업무 N(☐ + DueLabel, 줄을 누르면 근거 문장으로) → 본문(`--lh-mail`) → 본문 아래 [답장] [나중에 ▾] [제외]. 확인사항 메일은 [확인] [답장] |
| 요약 카드 | SummaryCard (FE-5c) | [메일 요약]을 누르면 본문 위에 요지 · 나에게 요청한 것 · 기한(원문 표현) · 원문 언어. 왼쪽 `--c-info-dot` 3px 선. 실패하면 '요약 실패 · [원문 보기] [다시 시도]'. 본문이 한국어가 아니면 버튼 강조 |
| 본문 형광펜 | EvidenceMark (FE-5b) | 근거 문장을 `<mark>`로 감싸 `--c-mark` 바탕 + `--c-mark-line` 2px 밑줄 + 숨은 글자 '업무 근거'. 업무 줄을 누르면 그 문장으로 스크롤 · 포커스, `--c-mark-strong` 0.8초 뒤 원래 색. 문장을 못 찾으면 칠하지 않고 업무 줄에 '근거 문장 없음' |
| 답장 | Compose | [보내기] · 보낸 사람 Select · 받는 사람(고정) · 제목 `RE: …` 자동 · 템플릿 Select · 내용 칸(하고 싶은 말만, 서식 막대 없음) · 미리보기(템플릿 인사 · 맺음 · 서명 사이에 쓴 내용, 쓴 부분 밑줄) · [삭제]. [보내기]는 그 자리에서 보내는 중 → 보냄 ✓(폭 유지) |
| 완료 확인 | CompleteSheet (Sheet) | 제목 "완료로 처리할까요?" · 그 메일의 미처리 업무(기본 체크) · ☐ "오늘 다시 보지 않음" · [아니오] [예]. 보낸 뒤 남은 업무가 있을 때만. 예 → 'N건을 완료로 바꿨어요 [되돌리기]', 아니오 계열 → '리마인드 유지' |

### 4.4 에이전트 패널 `G` (13-4, UX-D8 · D37)

| 부품 | 규칙 |
|---|---|
| AgentPanel (SidePanel 360px) | 소개 한 줄 + 예시 명령 칩(눌러서 바로 실행) + 대화 목록 + 아래 고정 입력 영역. 패널 안에 `role="status"` 영역을 처음부터 하나 두고 단계가 바뀔 때만 문구를 바꾼다 |
| StepLine (Collapsible) | 명령 이해 → 대상 찾기 → (확인) → 실행. 명령 이해와 대상 찾기는 서버 요청 하나가 함께 하므로, 응답이 오면 명령 이해 아래에 어떤 경로로 이해했는지(규칙 · 엑사원)를 적는다. 진행 중엔 한 줄 "지금 하는 일…(진행형) · n/전체 · 경과 초(3초부터)" + [중지]. 끝나면 "N단계 완료 · M초"로 접힘, 실패하면 펼친 채 멈춤. 단계 표시는 `<ol>`, 지금 단계에 `aria-current="step"`. 엑사원 경로에서 3초가 넘으면 "엑사원이 명령을 해석하는 중… (최대 140초)". 최대 대기는 HTTP 제한 140초와 같다(#63 리뷰) |
| ConfirmCard | 동사 질문 제목 + 대상 목록(Checkbox, 풀어서 뺄 수 있음) + [취소] [N건 완료 처리]. 미리 선택된 버튼 없음, 뜨면 포커스를 카드로. 대상 2건 이상 · 후보 여럿 · 설정 변경일 때만(D37) |
| ResultCard | 과거형 제목 + 대상 + [실행 취소](계속 남음, 누르면 '되돌렸어요') + '어떻게 해석했나요'(Collapsible, 서버가 준 설명) |
| 확인 시간 | 확인 카드는 서버가 정한 시각(`expires_at`, 5분)까지만 실행한다. 지나면 실행하지 않고 "확인 시간이 지났어요. 다시 말해 주세요"를 보인다 |
| DraftCard (T07) | 초안 미리보기 + [답장 화면에서 열기] → 메일 화면의 답장 작성 |
| SelectedMailBar | 메일 화면에서 고른 메일 제목 + [빼기]. 명령과 함께 메일 번호를 보낸다 |
| PromptInput | 여러 줄 입력. Enter = 보내기, Shift+Enter = 줄바꿈, **한글 조합 중 Enter는 보내지 않는다** |
| VoiceButton (FE-8) | 누르면 '듣는 중'(`--c-danger-bg` 바탕 + `--c-danger` 글자 + 깜빡임, 동작 줄이기면 깜빡임 없음) → 글자가 입력칸에 들어가고 사용자가 보내기를 누른다. 브라우저 음성 인식이 없으면 버튼을 숨긴다 |
| 지원하지 않는 요청 | 명령 이해 단계 실패 + "지원하지 않는 요청이에요" + 예시 명령 3개 |
| 패널 탭 (FE-11 · FE-16) | 제목 줄 아래 `대화 · 리마인더 · 기록` 분할 탭(같은 폭 세 칸). FE-16에서 '제안' 탭을 '리마인더' 탭으로 바꿨다(UX-D19). 열면 리마인더가 있을 때 리마인더, 없으면 대화. 리마인더 탭에 건수 배지. 입력은 모든 탭 아래에 그대로 있고 글을 쓰기 시작하면 대화 탭으로 옮긴다. 패널 안쪽 여백은 `--sp-4` 하나(제목 · 탭 · 카드 · 입력이 같은 선) |
| SuggestionsTab (FE-11) | 카드: 한 줄 제목 + 둘째 줄 + 버튼 한 줄(오른쪽 정렬, 보조 → 주 순서, 확인 카드와 같음) + ⋯(업무 아님 · 이 제안 숨기기). 빨강 채움 없음(확정 동작이 아님, UX-D18): 주 버튼은 테두리, 보조는 글자 버튼. [나중에]는 대시보드와 같은 시각 메뉴. 실행하면 카드 자리에 결과 한 줄 + [실행 취소]. 3장 넘으면 아래 '제안 N건 더 보기 ›' 한 곳. 없으면 "지금은 챙길 제안이 없어요" + 예시 명령 3개 |
| HistoryTab (FE-11) | '확인 기다림'(진한 테두리, 맨 위 고정)과 '최근 7일' 두 묶음. 한 줄: 한 일 / 상태 · 경로 · 상대 시각 · '자동' 칩, 오른쪽 끝에 [실행 취소] · [다시 하기] · [이어서 보기] 중 하나 |
| ReminderPeek (FE-16) | 리마인더 탭 내용. 에이전트 화면과 같은 목록의 앞쪽 3건을 카드로 보이고(제목 · 유형 · 이유 · 버튼 최대 3개 · ⋯), 아래 '리마인더 전체 보기 (N) ›' 한 곳이 에이전트 화면으로 간다. 실제 서버에 리마인더 API가 없으면 예전 SuggestionsTab을 그대로 보인다 |
| AgentMemoryView (FE-11) | 제목 줄 ⋯ → '에이전트가 아는 것'(패널 안 화면, ‹ 뒤로, 입력 숨김). 메일 기억하기 스위치 · 나(이름 · 팀 · 직책 · 배포 목록, [고치기] · 목록마다 [지우기]) · 중요한 사람(상급자 · 즐겨찾기 고르기 상자, [지우기]). 항목마다 쓰는 방식 · 쓰는 곳 · 출처 한 줄. 바꾸면 맨 위 한 줄 + [실행 취소]. 설정 화면 담당은 `<AgentMemoryView />`를 그대로 붙인다 |

| 작업 카드 (FE-15) | 단계 줄이 작업 카드다. 진행 중이면 오른쪽에 '진행 중'과 [취소], 끝나면 줄 글자가 완료 · 실패 · 취소를 말한다(화면 읽기에는 상태 낱말도 읽힌다). [취소]는 요청이 서버에 가 있는 동안만 보이고 요청을 끊는다. 서버가 이미 처리했을 수 있으므로 "요청을 취소했어요. 이미 처리됐다면 기록 탭에서 되돌릴 수 있어요"라고 쓴다. 확인을 기다리는 동안은 확인 카드의 [취소]만 둔다. 패널을 닫거나 화면을 옮겨도 작업은 계속된다 |
| 끝나면 알림 (FE-15) | 작업이 끝났을 때 사용자가 보고 있지 않으면(패널이 닫혀 있고 에이전트 화면도 아니거나, 탭이 가려짐) 토스트 하나 '결과 제목 · 시킨 말 [열기]'. [열기]는 에이전트 화면에서 그 결과를 오른쪽에 연다. 탭이 가려져 있고 사용자가 에이전트 화면에서 '작업이 끝나면 브라우저 알림 받기'를 켰으면 브라우저 알림도 띄운다. 허락은 그 상자를 켤 때만 묻는다. 판단은 `features/agent/agentNotify.ts` |
| 크게 보기 (FE-15) | 패널 제목 줄 [크게 보기] → `#/agent/chat`(대화 메뉴). 대화는 하나라 그대로 이어지고 패널은 닫힌다 |

### 4.4.1 에이전트 화면 `#/agent` (FE-15 · FE-16 · FE-D20 · UX-D19)

FE-16에서 세 칸(왼쪽 메뉴 · 가운데 목록 · 오른쪽 상세)과 아래 입력 한 줄로 바꿨다. FE-15의 두 칸(대화 · 결과물)은 '대화' 메뉴 안에 그대로 있다.

| 부품 | 규칙 |
|---|---|
| AgentPage | 한 테두리 안에 머리(에이전트 · 할 수 없는 일 한 줄), 세 칸, 아래 입력. 메일 화면처럼 화면 높이를 채우고 칸마다 따로 굴러간다. 메뉴를 옮기면 가운데 칸 제목으로 포커스가 간다 |
| 주소 | `#/agent/reminders/:묶음?/:항목 키?`(묶음 기본 all) · `#/agent/briefing` · `drafts` · `chat` · `history` · `memory`. `#/agent`와 모르는 주소는 리마인더 전체로 바꿔 쓴다. 메뉴 · 항목을 고르면 주소에 쌓여 뒤로 가기가 되돌린다 |
| AgentNav | 왼쪽 메뉴(약 220px). 위 '리마인더' 아래 전체와 여섯 묶음(건수, 0건도 보임), 구분선, 브리핑 · 회고 · 초안(건수) · 대화 · 기록 · 에이전트가 아는 것. 고른 메뉴는 `aria-current="page"` + 흰 바탕 + 왼쪽 막대. '기한 지남'이 있을 때만 '기한' 숫자를 진하게(색 신호 하나) |
| ReminderList | 가운데 목록(`role="listbox"`, 위아래 화살표로 옮기고 Enter로 고름). 한 줄 = 제목 + 회색 '유형 · 이유'. 고른 줄은 진한 테두리(선택은 네모). 맨 아래 '조용히 둔 것 N건 ⌄' 한 곳에 접힘. 빈 상태는 무엇이 여기에 보일지 한 줄 |
| ReminderDetail | 오른쪽 상세. 회색 머리(묶음 · 유형 · 상대) → 제목 → 기한 라벨 → 이유 → 근거 문장(형광펜 + '메일에서 보기 ›') → 버튼 줄(오른쪽 끝, 보조 → 주, 최대 3개, 빨강 채움 없음) + ⋯ → 원본 메일 → 이 항목 기록. 고르지 않았으면 무엇이 보일지 한 줄 |
| ⋯ 메뉴 | 내 일 아님 · 이 유형 알림 끄기(끈 유형이면 켜기) · 잘못 알아챘어요(AI가 알아챈 유형만). 버튼에 같은 동작이 있으면 빠진다 |
| 고른 리마인더 칩 | 아래 입력 위 '고른 리마인더 제목 ✕'. 리마인더 메뉴에서는 상세와 늘 같고, 다른 메뉴로 옮기면 마지막 항목을 들고 간다. 칩이 있을 때 보낸 명령에 업무 번호 · 항목 키가 함께 간다 |
| 아래 입력 | 모든 메뉴가 함께 쓰는 PromptInput 하나. 대화 메뉴가 아닌 곳에서 보낸 명령은 대화에 쌓이고 결과 한 줄 토스트만 뜬다(되돌릴 수 있으면 [실행 취소], 초안 · 확인 카드는 [열기]). 토스트는 이 입력 위로 올라간다 |
| BriefingView | 가운데: 날짜(‹ 날짜 › · 오늘) + 아침 브리핑 · 퇴근 회고 · 주간 회고 세로 탭(만드는 시각 회색). 오른쪽: 만든 시각 · 서버 문장 · 묶음별 줄(기한 라벨). 권유 문장 없음(AI-D18). 아직 만들 시각이 아니면 언제 만드는지 한 줄. 퇴근 회고 '남은 일' 줄에만 [내일 아침으로 미루기] |
| DraftsView | 가운데: 이 대화에서 나온 회신 초안 목록. 오른쪽: ResultViewer의 초안 보기(고쳐 쓰기 · [복사] · [답장 화면에서 열기]). 보내기는 없다 |
| ChatView | FE-15의 두 칸 그대로(대화 목록 · 결과물). 결과 자동 열기도 그대로 |
| ResultLinkCard | 대화 메뉴에서는 회신 초안 · 오늘 요약 · 업무 목록 · 답장 없는 메일을 짧은 카드(결과 제목 + '초안 1건' · '요약' · '업무 3건' · '메일 2건' + [열기])로만 보인다. 지금 열린 결과는 진한 테두리 + [보는 중]. 실행 결과(실행 취소) · 확인 카드 · 알림 · 실패는 그 자리에서 눌러야 하므로 그대로 둔다 |
| ResultViewer | 처음에는 "열린 결과물이 없어요". 초안: 받는 사람 · 제목 + 고쳐 쓰는 입력칸(고친 글자는 화면을 떠났다 와도 남음) + [복사] [답장 화면에서 열기]. 요약: 건수 줄 · 그 밖에 줄 → 브리핑 문장 → 업무 줄. 업무 · 메일 줄을 누르면 그 메일로 가고 메일 화면 맨 위에 [← 에이전트]가 붙는다. 제목 줄 오른쪽에 '작업이 끝나면 브라우저 알림 받기' |
| 기록 · 에이전트가 아는 것 | FE-11 HistoryTab과 AgentMemoryView를 넓은 칸 하나에 그대로 붙인다 |
| 좁은 화면 | 1024px 미만: 왼쪽 메뉴는 위쪽 고르기 상자, 목록과 상세는 한 칸씩(상세 위 ‹ 뒤로) |

데이터: 패널이 서버에 묻는 길은 `POST /api/agent/command` 하나다(BE-11, PR #50). 명령 해석, 대상 업무 찾기, 확인이 필요한지 판단(D37), 1건이면 바로 실행까지 모두 백엔드가 하고, 패널은 돌려받은 결과의 종류(`kind`)에 따라 카드만 고른다. 그래서 프론트에는 대상을 찾거나 확인 여부를 정하는 코드가 없다. 확인 카드의 실행은 `POST /api/actions/execute`에 체크를 남긴 업무만 실어 보내고, 결과 카드의 [실행 취소]는 되돌리기 요청을 쓴다. 상태가 바뀐 뒤에는 대시보드 원자료를 다시 불러온다.

모의 모드에서는 같은 요청을 `api/mockClient.ts`가 흉내 낸다. 규칙 해석(`api/mock/agentPlanner.ts`)과 백엔드 실행기를 옮긴 코드(`api/mock/agentExecutor.ts`)가 실제 서버와 같은 제목 · 되묻기 문구 · 확인 판정으로 결과를 만든다. 모의와 실제는 클라이언트만 다르고 패널 코드는 같다. 시연 문장 ①②③⑥(handoff 시연 대본)과 V-16 · V-17이 모의 모드에서 돈다.

오늘 요약(T01) · 답장 없는 메일(T06) · 회신 초안(T07)은 백엔드에서 아직 준비 중이다. 백엔드 결과에 이 카드에 맞는 종류가 없어서, 프론트가 결과 종류 `summary` · `awaiting` · `draft`와 그 내용 칸을 먼저 제안했다(5.1 표). 지금은 모의만 이 결과를 만들고, 실제 서버는 이 명령에 "'오늘_요약'은(는) 아직 준비 중이에요"처럼 답한다. 패널은 그 답을 숨기지 않고 그대로 보이며, 서버에 기능이 아직 없다고 안내한다.

### 4.5 알림 센터 · 토스트 (13-6, UX-D7 · UX-D19 · FE-D26)

FE-10은 이재운 담당이었고 FE-16에서 문규남이 넘겨받아 만들었다(리뷰 이재운).

- 🔔 숫자 = 아직 읽지 않은 리마인더 알림 수(새 업무 · 작업 완료 알림은 세지 않음, 10 이상 `9+`). 버튼 이름에도 숫자가 들어간다.
- 알림 센터(Popover 400px): 제목 줄 '알림' + [모두 읽음], Tabs [리마인더 N \| 알림 N]. 리마인더 탭: 건수가 있는 묶음 칩만(넘치면 마지막 칩이 ›), 줄 최대 5개(안 읽음 점 · 제목 · 유형 · 이유 · 버튼 최대 2개), 맨 아래 '리마인더 전체 보기 (N) ›'(팝업 안이 굴러가도 바닥에 붙어 있음). 줄을 누르면 에이전트 화면의 그 항목, 아침 묶음 알림은 브리핑 메뉴. 알림 탭: 리마인더가 아닌 서버 알림과 앱 안 알림(에이전트 작업 완료) · 안 읽은 점.
- 리마인더 토스트는 흰 카드로 자동으로 사라지지 않는다(닫아도 알림 센터에 남음). 앱을 처음 열 때 이미 있던 알림은 토스트로 띄우지 않는다.
- 토스트 자리: 오른쪽 아래. 에이전트 화면처럼 아래에 고정 입력이 있으면 그 높이만큼 올린다(`--toast-lift`).
- 리마인더 API(BE-12)가 없으면 실제 서버 모드에서 🔔 숫자와 리마인더 탭을 비워 두지 않고 숨긴다. 모의 모드에서는 `api/mock/reminders.v1.json`을 쓴다.

### 4.6 설정 (FE-6 최소판)

아침 알림 시각 · 무응답 기준일 · 상급자 · 즐겨찾기만. 나머지 메뉴(템플릿 · 화면 · 접근성)는 이번에 만들지 않는다.

## 5. 데이터 흐름

- **모의 · 실제 선택**은 지금 구조(`api/selectApi.ts`, 환경 변수 `VITE_API_MODE`)를 그대로 쓴다. 실제 서버가 실패하면 오류 상태를 보이고 모의 데이터로 바꾸지 않는다.
- **모의 데이터 v2**: 와이어프레임 13-9 확인 표가 시안의 시연 데이터(메일 22통 · 업무 21건 · 기준 11/6(금) 10:42)를 기준으로 하므로, 시안 데이터를 지금 응답 형식(`as_of · contacts · mails · tasks`)으로 옮긴 모의 데이터 v2를 만든다. 지금 계약에 없는 칸(메일 확인 · 참고 구분, 받는 사람, 본문, 언어, 거래처 여부, 업무 원문 기한 · 근거 문장 · 유형)은 **있어도 되고 없어도 되는 칸**으로 화면 모델에 더하고, 없으면 그 부분을 숨긴다. 기존 v1(더미 100통)은 집계 테스트용으로 남긴다.
- **불러오기**: TanStack Query. 대시보드 원자료 하나(`['dashboard']`)를 불러와 대시보드 · 메일 목록이 같은 데이터를 나눠 쓴다. 메일 한 통 본문(`['mail', id]`)은 BE에 API가 생기기 전까지 모의 모드에서만 보인다.
- **업무 상태 바꾸기**(FE-D16): 체크하면 즉시 BE-4 `PATCH /api/tasks/{id}`를 보내고 화면은 먼저 바꾼다. 실패하면 원래대로 돌리고 "바꾸지 못함 [다시 시도]". 되돌리기 토스트의 [되돌리기]는 받은 `action_id`로 `POST /api/actions/{action_id}/undo`. 성공하면 `['dashboard']`를 다시 불러온다. 모의 모드는 같은 동작을 메모리에서 흉내 낸다.
- **여러 건(일괄)**: BE-4 미리보기(`/api/tasks/bulk/preview`) → 확인 → 실행(`/api/actions/execute`) → [되돌리기]는 undo. 에이전트는 미리보기를 명령 요청이 대신 만들어 주므로(`preview_id`) 확인 카드에서 바로 실행한다.
- **API가 없는 것**: 응답 대기(BE-13) · 리마인더(BE-12) · 메일 본문 · 요약(BE 메일 한 통 API). 생기면 모의 → 실제 연결만 바꾼다.

### 5.1 화면이 부르는 API (계약)

아래 표는 프론트가 부르는 서버 요청 전부와 지금 상태다. '있음'은 백엔드에 이미 있는 것이고, 'FE 제안'은 백엔드 DB에 칸은 있지만 요청이 아직 없어서 프론트가 형식을 먼저 제안한 것이다. FE 제안 형식은 DB 칸 이름을 그대로 써서 백엔드가 그대로 옮기기 쉽게 했다. 프론트는 이 형식으로 모의 응답을 먼저 만들고, 백엔드와 합의되면 실제 연결로 바꾼다. 코드에서는 `src/api/contract.ts` 한 파일에 함수 이름과 입출력 타입을 모은다.

| 쓰는 화면 | 요청 → 응답 | 상태 |
|---|---|---|
| 대시보드 · 메일 목록 | `GET /api/dashboard` → `{as_of, contacts[], mails[], tasks[]}` | BE-3 PR #47(리뷰 중). 화면에 더 필요한 칸(메일 `lane` · `reasons` · `to`, 업무 `due_raw` · `type`, 맨 위 `awaiting[]`)은 있어도 되고 없어도 되는 칸으로 받는다 |
| 업무 상태 1건 | `PATCH /api/tasks/{id}` `{status, snoozed_until?}` → `{action_id, tasks[{id, status, done_at, snoozed_until}]}` | 있음(BE-4) |
| 업무 상태 여러 건 | `POST /api/tasks/bulk/preview` `{task_ids, status, snoozed_until?}` → `{preview_id, targets[]}` 다음 `POST /api/actions/execute` `{preview_id, task_ids?}` → `{action_id, tasks[]}` | 있음(BE-4). `task_ids`는 확인 카드에서 체크를 남긴 업무이고, 빼면 미리보기 대상 전부를 실행한다 |
| 되돌리기 | `POST /api/actions/{action_id}/undo` → `{action_id, undone_action_id, tasks[]}` | 있음(BE-4) |
| 알림 센터 | `GET /api/notifications` → `{items: [{id, kind: 'reminder' \| 'reply_confirm' \| 'new_tasks', title, body?, task_ids[], rule?, scheduled_at?, read_at, answered_at, created_at}]}`, `PATCH /api/notifications/{id}` `{read?: true, answer?: 'yes' \| 'no'}` | FE 제안(DB `notifications` · `reminders` 칸 그대로, BE-12). 알림 탭의 '새 업무 N건'에 `new_tasks` 종류와 둘째 줄 `body`가 더 필요하다(DB 종류 제약에 추가 요청) |
| 리마인더 (FE-16) | `GET /api/reminders?group=` → `{as_of, counts{due, waiting, promise, revisit, prepare, cleanup, all}, muted_types[], items[{key, type, group, title, reason, evidence, task_id, task_ids[], mail_id, commitment_id, due_at, counterpart{name, position}, created_at, state, notify_count, actions[{id, label, action, primary, params}]}]}`, `POST /api/reminders/{key}/dismiss` `{reason: hide \| not_mine \| wrong_signal \| keep \| stop_waiting}` → `{key, action_id}`, `POST /api/reminders/{key}/apply` → `{key, action_id}`, `PATCH /api/reminders/types/{type}` `{notify}` → `{type, notify}` | FE 제안 · BE-12가 만드는 중(`../10_planning/reminders.md` 7.2절, FE-D27). 모르는 유형 항목은 뺀다. 숨김 이유는 버튼 `params.reason`. 알림 칸에 `type` · `group` · `reminder_key`, 종류에 `digest`를 더하고, `POST /api/notifications/read-all` → `{updated}` |
| 브리핑 · 회고 (FE-16) | `GET /api/briefings/{morning \| evening \| weekly}?date=YYYY-MM-DD` → `{kind, date, as_of, summary, sections[{id, label, count, items[{title, reason, task_id, mail_id, reminder_key, due_at}]}]}` | FE 제안 · BE-12가 만드는 중. 아직 만들 시각이 아님을 알리려면 `scheduled_at` · `generated_at`(선택)이 더 필요하다 |
| 에이전트 명령 — 고른 리마인더 (FE-16) | 위 명령 요청에 `task_ids?` · `reminder_key?`를 더한다(고른 리마인더가 있을 때만) | FE 요청. 서버가 아직 읽지 않는다 |
| 설정 | `GET · PATCH /api/settings` `{remind_time, awaiting_reply_days, quiet_start, quiet_end, reduce_motion, stt_mode, templates?}` | FE 제안(DB `settings` 칸 그대로, 답장 템플릿은 DB `templates`) |
| 완료 확인 시트 '오늘 다시 보지 않음' | 위 설정 요청의 `reply_confirm_skip_until?`(+09:00 ISO · `null` = 꺼짐). [예]와 함께 고르면 다음 아침 알림 시각(`remind_time`)을 넣고, 그 시각 전까지는 답장을 보내면 시트 없이 바로 완료(D48 `reply_auto`). 칸이 오지 않으면 체크 상자를 숨긴다 | FE 제안(DB `settings.reply_confirm_skip_until` 칸 그대로, FE-5) |
| 상급자 · 즐겨찾기 | `PATCH /api/contacts/{email}` `{is_superior?, is_favorite?}` | FE 제안(DB `contacts` 칸 그대로) |
| 응답 대기 | `GET /api/awaiting` → `[{mail_id, subject, to, sent_at, days}]` | FE 제안(BE-13) |
| 메일 한 통 | `GET /api/mails/{id}` → 목록 칸 + `{to[], body, lang, lane, reasons[], tasks[{…, due_raw, type, evidence_text}]}` | FE 제안(본문 저장 정책 결정 필요) |
| 메일 요약 | `POST /api/mails/{id}/summary` → `{lang, gist, asks[], due_text}` | FE 제안(AI-13 v2 #34 형식) |
| 답장 보내기 | `POST /api/mails/{id}/reply` `{account, subject, content, template_key}` → 저장된 보낸 메일 `{id, sent_at}`. `content`는 미리보기에 보인 본문 전체(템플릿 인사 · 맺음 · 서명 + 쓴 말), `template_key`는 기록용. 사용자가 [보내기]를 눌렀을 때만 부른다(D48) | FE 제안(FE-5). 모의 모드는 메모리에 저장만 하고 실제로 보내지 않는다. 실제 모드에서 404 · 405 · 501이면 보내지 못했다고 알린다 |
| 에이전트 명령 | `POST /api/agent/command` `{text, selected_mail_ids?, last_result_ids?}` → `{kind, action, action_name, source, title, targets[{id, mail_id, text, status, snoozed_until}], notes[], action_id, preview_id, expires_at}` | 있음(BE-11 PR #50). `kind`는 `done` · `confirm` · `query` · `ask` · `empty` · `unsupported`. 고른 메일과 직전 결과는 업무 id가 아니라 **메일 id**로 보낸다. AI를 쓸 수 없으면 503이고 상태는 바뀌지 않는다(화면 문구 "지금은 명령을 처리할 수 없어요. 잠시 뒤 다시 말해 주세요"). 빈 글자 · 500자 초과는 422 |
| 메일 읽음 · 고정 (FE-5d) | `PATCH /api/mails/{id}` `{read?: boolean, pinned?: boolean}` → 바뀐 메일 한 통(목록 칸 + `read_at` · `pinned_at`). 읽음은 이미 읽었으면 처음 읽은 시각을 그대로 두고, 안 읽음은 `read_at`을 비운다. 고정은 `pinned_at`에 시각, 해제는 `null`. 여러 통은 이 요청을 한 통씩 보낸다. 대시보드 응답의 메일에 `pinned_at?`(+09:00 ISO · `null`)를 더한다 | FE 제안(FE-5d). 백엔드 DB에 메일 읽음 · 고정 칸이 아직 없다. 실제 모드에서 칸이 오지 않으면 화면이 읽음 · 고정을 숨기고, 404 · 405 · 501이면 그 자리에서 숨긴다. 모의 모드는 메모리에서 바꾼다 |
| 에이전트 명령 — 오늘 요약 · 답장 없는 메일 · 회신 초안 | 위 응답에 `kind`: `summary` · `awaiting` · `draft`를 더하고, 내용 칸 `summary: {items[{task_id, mail_id, text, due_at, due_raw}], hint}` · `awaiting: [{mail_id, subject, to, sent_at, days}]` · `draft: {mail_id, to, subject, text}`를 싣는다. 오늘 요약에는 조율 중인 선택 칸 `summary.text`(모델이 쓴 브리핑 문장, 못 쓰면 null) · `summary.refreshing`(새로 정리 중이면 true)을 더한다(FE-15, T01 백엔드와 맞춤) | FE 제안. 백엔드 레지스트리에서 T01 · T06 · T07이 아직 준비 중이라 지금은 모의만 만든다. 실제 서버는 이 명령에 `unsupported`('…아직 준비 중이에요')로 답하고, 화면은 그대로 보인다 |
| 에이전트 패널 — 제안 카드 | `GET /api/suggestions?limit=3` → `{suggestions[{key, rule, via, created_at, title, detail[], task_ids[], mail_ids[], buttons[{label, kind, action, primary, params, target{task_ids, mail_ids}}], menu[…]}], more, total, generated_at}` | 있음(PL-16 #44, `docs/30_backend/agent_api_contract.md` 3.1). 접힌 목록은 3장, '제안 N건 더 보기'를 누르면 50장. 버튼 → 행동은 `features/agent/agentPanelPlan.ts`(T03 · T10 · T05 → `useTaskActions` + 카드 `via`, T07 · T01 · T06 → 에이전트 명령, `open_mail` → 메일 화면, 모르는 행동은 그리지 않음). 모의는 `api/mock/agentPanelRules.ts`가 backend 규칙 그대로 계산(일정 참석 카드는 데이터가 없어 띄우지 않음) |
| 제안 숨기기 | `POST /api/suggestions/{key}/hide` → `{key, hidden_until}` | 있음(PL-16). 다음 R-아침까지 |
| 업무 상태 1건 · 여러 건의 `via` | 위 BE-4 요청 본문에 `via?`(`suggestion:<종류>` · `history`) | 있음(BE-4 Via 칸). `useTaskActions`의 `opts.via`로 넘긴다 |
| 에이전트 패널 — 기록 탭 | `GET /api/actions/history?days=7` → `{days, items[{id, state: 'waiting' \| 'done' \| 'undone', action, action_id, preview_id, text, via, via_label, auto, at, expires_at, can_undo, redo_action_id}]}` | 있음(PL-16, 계약 3.2). [실행 취소]는 `action_id`, [다시 하기]는 `redo_action_id`를 같은 되돌리기 요청으로. [이어서 보기]는 그 확인 카드가 대화에 열려 있을 때만(미리보기를 다시 받는 요청이 없음) |
| 에이전트가 아는 것 | `GET /api/agent/memory` → `{learn_from_mail, me{name, department, position, mailing_lists[{address, kind}], uses, used_by[], origin{at, text}}, people[{contact_id, name, email, position, is_superior, is_favorite, facts[], uses, used_by[], origin}]}`, `PATCH /api/agent/memory/me` `{department?, position?, mailing_lists?}` · `PATCH /api/agent/memory/people/{contact_id}` `{is_superior?, is_favorite?, facts?}` → `{action_id, memory}` | 있음(PL-16, 계약 3.3). 되돌리기는 업무와 같은 `POST /api/actions/{id}/undo`. 화면은 `features/agent/AgentMemoryView.tsx`(설정 화면에도 그대로 붙일 수 있음) |
| 메일 기억하기 | `GET · PATCH /api/agent/settings` `{learn_from_mail}` | 있음(PL-16, 계약 3.4). 기본 켜짐 |

**업무 상태 바꾸기 함수(모든 화면이 같은 것을 부른다).** 대시보드 · 메일 · 시트 · 에이전트는 서버를 직접 부르지 않고 `useTaskActions()`가 돌려주는 함수만 부른다. 그래야 되돌리기 토스트 · 실패 처리 · 다시 불러오기가 한곳에서 같게 동작한다.

| 함수 | 하는 일 |
|---|---|
| `complete(taskIds, {source, toast})` | 1건이면 PATCH, 2건 이상이면 미리보기 → 실행. 결과 `{actionId, tasks}`를 돌려준다. `toast`가 참(기본)이면 '완료로 바꿨어요 [되돌리기]' 토스트 8초 |
| `snooze(taskIds, until, opts)` · `exclude(taskIds, opts)` | 같은 방식으로 나중에 · 제외 |
| `undo(actionId, opts)` | 되돌리기. 성공하면 '되돌렸어요' |

에이전트 결과 카드처럼 자기 [실행 취소] 버튼이 있는 곳은 `toast: false`로 부른다. `source`(`button` · `sheet` · `agent`)는 지금은 화면 쪽 구분용이다. BE-4 요청에는 아직 이 칸이 없고 BE-4 기록값(`ui` · `agent_rule` · `agent_model` · `mcp`)과 이름도 달라 서버로 보내지 않는다. 맞추는 것은 BE와 협의한다.

## 6. 키보드 · 확인 방법

**단축키** — 모두 `lib/shortcuts.ts`의 가드를 거친다. 입력칸 · 여러 줄 입력 · 편집 가능한 영역에 포커스가 있거나 한글 조합 중(`isComposing` 또는 keyCode 229)이면 동작하지 않는다. 메일 화면 단축키는 확인 시트 · 도움말이 열려 있거나 대화상자(`role="dialog"`) 안에서 누른 키도 무시한다(#59 리뷰: 시트를 연 채 Delete가 뒤 메일의 업무를 제외하던 문제).

| 키 | 동작 | 어디서 |
|---|---|---|
| Ctrl+B · ⌘B | 메일함 열고 닫기 | 메일 화면 |
| Ctrl+J · ⌘J | 에이전트 패널 열고 닫기. 에이전트 화면에서는 입력칸으로 이동(FE-D21) | 설정을 뺀 모든 화면 |
| Alt+← · Alt+→ | 이전 · 다음 화면 | 어디서나(브라우저 기본 동작, 주소에 항목이 쌓여서 됨) |
| Esc | 가장 위에 열린 것 하나 닫기: 메뉴 → 알림 센터 → 패널. 시트에서는 '아니오' | 어디서나 |
| ↑ ↓ · Enter | 메일 줄 이동 · 열기 | 메일 목록 |
| Ctrl+. · Ctrl+, | 다음 · 이전 메일 열기(Outlook과 같음) | 메일 화면 |
| R · Ctrl+R | 답장 쓰기. 메일 화면에서 Ctrl+R은 입력칸 안이든 밖이든 늘 막아 새로고침되지 않는다. 답장을 쓰는 중에는 F5 · 탭 닫기 때 한 번 묻는다(`beforeunload`) | 메일 화면(메일이 열려 있을 때) |
| Ctrl+Q · Ctrl+U | 읽음 · 안 읽음으로 표시(골라 둔 메일이 있으면 그것들, 아니면 열린 메일) | 메일 화면 |
| Insert | 고정 · 고정 해제. Outlook에서는 플래그 키지만 우리는 기한 라벨이 플래그 역할을 해서 고정에 맞췄다(도움말에 적음) | 메일 화면 |
| Delete | 업무 제외(끝나지 않은 업무가 있는 메일만) + '업무 N건을 제외했어요 [되돌리기]'. 여러 통을 골랐으면 '제외할까요?' 확인 시트를 먼저 띄운다(D37 덧붙임) | 메일 화면 |
| Shift 클릭 · Ctrl/⌘ 클릭 · Esc | 범위 고르기 · 하나 고르기 · 고른 것 해제 | 메일 목록 |
| ? | 메일 단축키 도움말 | 메일 화면 |
| Enter · Shift+Enter | 보내기 · 줄바꿈 | 에이전트 입력 |
| F6 | 토스트 영역으로 이동 | 토스트가 있을 때 |

**자동 확인**: `npm test`(판단 시험 · 토큰 고정 · 대비) · `npm run build`(타입 검사). 화면 부품 테스트 도구는 들이지 않는다(FE-D18).

**키보드 점검표**(PR마다 해당 화면만, 결과를 PR 본문에 적는다)

1. 마우스 없이 Tab만으로 업무 체크 → 되돌리기 → 메일 이동 → 답장 → 보내기 → 시트 예/아니오까지 갈 수 있다.
2. 모든 버튼 · 줄 · 칩에 포커스 링(`--c-ink` 2px + 2px 띄움)이 보인다.
3. 패널 · 알림 센터 · 시트를 닫으면 포커스가 연 버튼으로 돌아간다.
4. 입력칸에서 한글을 치는 중에 Enter · Esc · Ctrl+B · Ctrl+J가 엉뚱하게 동작하지 않는다.
5. 동작 줄이기 설정을 켜면 줄 빠짐 · 패널 등장 · 깜빡임이 모두 없어지고 결과만 바뀐다.
6. 화면 읽기 프로그램에서 토스트 · 에이전트 단계 문구가 한 번씩만 읽힌다.

**브라우저 점검**: 단계가 끝날 때마다 wireframe 13-9 확인 표(V-1~V-27) 중 그 단계에 해당하는 줄을 크롬으로 돌리고 PR에 맞음 · 틀림을 적는다. 작업 환경에서는 브라우저를 띄울 수 없으므로 이 점검은 사람이 한다.

**피그마 캡처**(FE-14): 단계가 끝나면 구현 화면을 피그마 드래프트 '화면' 페이지로 캡처해 시안과 나란히 둔다.

## 7. 하지 않는 것

- 라이브러리 기본 테마 · Tailwind · CSS-in-JS(FE-D15 · FE-D17)
- 칸 끌어서 순서 바꾸기 · 메일함 폭 끌기 · 긴 목록 가상화 · 명령 팔레트
- 설정의 템플릿 · 화면 · 접근성 메뉴, 기록 탭 · '에이전트가 아는 것' 화면(P1)
- 서버에 API가 없는 칸을 0건으로 보이기, 서버 실패를 모의 데이터로 감추기

## 8. 작업 경계 — 누가 어느 폴더를 고치나

여러 사람이 동시에 만들어도 같은 파일을 고치지 않게 폴더로 나눈다. 화면 기반(FE-13)이 모든 자리와 계약을 먼저 만들고, 그 뒤에는 각자 자기 폴더만 고친다. 남의 폴더를 고쳐야 하면 그 담당에게 PR로 보낸다.

| 담당 | 작업 | 고치는 곳 | 화면 기반(FE-13)이 미리 만들어 두는 것 |
|---|---|---|---|
| 문규남 | FE-13 기반 | `app/` · `ui/` · `lib/shortcuts.ts` · `api/`(계약 · 모의 v2) · `styles/` | — |
| 문규남 | FE-3 대시보드 · 줄 빠짐 | `pages/dashboard/` · `features/tasks/`(아래 `useTaskActions` 제외) | — |
| 문규남 | FE-5 메일 · 답장 · 완료 시트 | `pages/mail/` · `features/mail/` | — |
| 문규남 | FE-7 · FE-8 에이전트 · 음성 | `features/agent/` · `features/voice/` | 상단 바 ✦ 버튼 · 패널 자리 |
| 문규남(넘겨받음, 원래 이재운 · 리뷰 이재운) | FE-10 알림 센터 · 리마인더 토스트 · 🔔 숫자 | `features/notifications/` · `api/mock/notifications*.json` | 상단 바의 🔔 자리(`features/notifications/NotificationBell.tsx` 빈 틀: 버튼 + 빈 팝업), 알림 API 계약과 모의 응답 |
| 문규남 | FE-16 리마인더 · 에이전트 화면 세 칸 | `features/reminders/` · `pages/agent/` · `api/reminders.ts` · `api/mock/reminder*` · 계약 네 파일(`contract` · `adapter` · `httpClient` · `provisional`)의 맨 끝 '리마인더' 블록 | — |
| 이재운 | FE-6 설정 | `pages/settings/` · `features/settings/` | `#/settings` 주소와 빈 화면, 설정 · 연락처 API 계약과 모의 응답 |
| 이재운 | FE-4 완료 · 되돌리기 토스트 | `features/tasks/useTaskActions.ts` · `lib/toastPolicy.ts` | 공통 부품 Toast(모양 · 자리 · 띄우는 함수)와 `useTaskActions` 계약 + 토스트 없는 기본 구현(서버 요청 · 다시 불러오기만) |
| 임동하 | FE-9 실제 서버 연결 | `api/httpClient.ts` · `api/adapter.ts` | 모의 · 실제 선택 구조(있음) |

- 공통 부품 Toast의 모양(`ui/Toast`)은 기반 작업에서 3절 명세대로 만든다. 문구 · 시간 · 되돌리기 동작은 FE-4 담당이 정한다. 모양을 바꿔야 하면 기반 담당에게 알린다.
- 대시보드 · 메일 · 에이전트 화면은 FE-4가 끝나기 전에도 `useTaskActions`의 기본 구현으로 돌아간다. FE-4가 같은 함수 안에 토스트 · 되돌리기를 붙이면 화면 쪽은 고칠 것이 없다.

## 참고 위치

- 토큰: `frontend/src/styles/tokens.css` · `cne.tokens.json` · `scripts/tokens-export.mjs` · `src/styles/tokens.test.ts`
- 지금 화면 모델 · 계약: `frontend/src/api/types.ts` · `provisional.ts` · `adapter.ts` · `be3_contract_comparison.md` · BE-3 PR #47
- 업무 상태 API: `backend/app/api/actions.py`(BE-4)
- 시안 데이터 · 모양: `docs/20_frontend/ui_reference/cne_v31.html`
