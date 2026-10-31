# 조사 정리 · 미처리 업무 대시보드 레퍼런스 (2026-10-22)

> 목적: PRD Q5 `[가설]` "미해결 대시보드"를 와이어프레임으로 옮기기 전에 구성 근거를 모은다.
> 방법: 조사 에이전트 3개로 나눴다 — ① 할 일 처리 보드 ② 칸 구성 · 자동 갱신 ③ AI 메일 비서 · 국내 그룹웨어. 웹 검색이 막혀(403) 공식 문서 URL을 직접 열었다. 핵심 수치 2건(Superhuman 7칸 권장, FastAPI SSE 내장)은 다시 열어 원문을 확인했다.
> 표시: `[사실]` 출처에서 확인 · `[추론]` 해석 · `[미확인]` 확인 못 함

## 한눈에 보기

| 질문 | 결론 |
|---|---|
| 칸은 몇 개까지? | 7개 이하. Superhuman이 "no more than seven"을 권장한다 `[사실]`. 기본 4~5칸 권장 `[추론]` |
| 칸을 나누는 기준은 몇 개? | 한 번에 1개만 칸으로 쓴다. 두 번째 기준은 가로줄(스윔레인) 또는 카드 배지로 보여 준다(Linear 하위 그룹) `[사실]` / 3기준을 모두 칸으로 펴면 5×2×5=50칸 `[추론]` |
| 사용자가 칸을 고르게 하려면? | 칸 = 저장된 필터(제목 · 색 · 필터 · 정렬). X Pro 'Add column', Slack 섹션별 정렬 · 필터 `[사실]` |
| 새 업무가 들어오면? | 읽는 중인 칸은 움직이지 않는다. 칸 머리에 "+N 새 항목"만 띄우고 누르면 반영한다 `[추론]` (근거: web.dev CLS — 클릭 후 500ms 밖의 이동은 예상치 못한 이동 `[사실]`) |
| 서버 → 화면 전달 | SSE + 폴링 예비. FastAPI 0.135.0부터 `fastapi.sse.EventSourceResponse` 내장, 15초 keep-alive `[사실]` |
| 차별점 | 메일에서 자동 추출한 업무를 업무 유형 · 기한 칸으로 나누는 보드는 확인한 범위에 없었다. AI 메일 도구는 목록 · 라벨, 그룹웨어 보드는 사람이 직접 등록 `[사실 범위 내 추론]` |

## 1. 할 일 처리 보드 레퍼런스

| 제품 | 구조 | 칸 기준 | 처리 동작 | 우리에게 가져올 것 |
|---|---|---|---|---|
| Superhuman Split Inbox | 받은편지함 위 섹션 바, Tab으로 칸 이동 | 규칙(Important · VIP · Team · 사용자 정의) | 칸 순서 드래그, 빈 칸 숨김 | 7칸 상한, 칸마다 **전체 건수**(읽지 않은 수 아님) `[사실]` |
| Linear My Issues | 고정 순서 섹션: 긴급 → SLA → 막힌 일 | 긴급도 | 보드/목록 전환, 하위 그룹 = 가로줄 | 급한 칸을 앞에 고정, 2번째 축은 가로줄 `[사실]` |
| Linear Inbox | 목록 + Priority 탭 | 우선순위 | H 미루기(정한 시각에 다시 표시), 미룬 항목은 기본 숨김 | 미루기는 쓰되 "미룸 N건"을 따로 보이게 `[추론]` |
| GitHub Notifications | 왼쪽 필터 + 목록 | 기본 필터 + 사용자 필터 15개 | Done(3개월 보관), 일괄 선택 | 처리 = 숨김이 아니라 보관, 일괄 처리 `[사실]` |
| HEY | Imbox + 아래 고정 더미(Reply Later · Set Aside), Focus & Reply | 사용자 의도 | 회신하면 대기열에서 빠짐 | "회신 칸 몰아서 처리" 모드 `[사실]` |
| Trello | 보드 → 리스트 → 카드, 리스트 수 제한 없음 | 사용자 정의 | 체크 · 드래그 | 마감 배지 3색(노랑 24시간 내 · 빨강 지남 · 초록 완료) `[사실]` |
| Todoist 보드 · 아이젠하워 | 섹션 = 칸, 2×2 매트릭스 | 섹션 / 긴급 × 중요 | 동그라미 체크 | 2축 매트릭스 사례 `[사실]` |
| Freshdesk | 티켓 목록 | due-by 정렬 | 기한 전 알림 | 칸 안 정렬 = 마감 임박순 `[사실]` |

## 2. 칸 구성 · 설정 방식

| 제품 | 칸 추가 · 설정 | 개수 · 폭 | 모바일 |
|---|---|---|---|
| X Pro | 'Add column' → 종류 선택, 6점 아이콘으로 순서 변경 | 제한 문서 없음 | — |
| Slack 섹션 | 이름 · 이모지, 섹션별 정렬 · 필터 | 제한 문서 없음 | 대화 헤더 → Move |
| Notion 보드 | 속성 하나로 그룹 → 값마다 칸 자동 생성, 칸 숨기기 · 순서 · 색 | 칸 수 = 옵션 수 | — |
| Grafana | 패널 추가, Auto grid | 최대 10열 | — |
| monday.com | 위젯 + 필터 | 위젯 30개 상한 | — |
| react-grid-layout / gridstack | 레이아웃 x·y·w·h 직렬화 저장 | 12열 | 768px 이하 1열 예시 |

→ 자유 배치 그리드(위젯)는 분석 대시보드용이다. 우리는 할 일 처리용이라 **고정 폭 가로 칸**(Trello · X Pro형)이 맞다 `[추론]`.

## 3. 자동 갱신 패턴

| 패턴 | 언제 | 주의 | 출처 |
|---|---|---|---|
| 칸 머리 배지 "+N" | 새 항목 도착을 조용히 알릴 때 | 사용자가 본 뒤 지움 | NN/g `[사실]` |
| "새 항목 N건" 버튼 → 눌러야 반영 | 사용자가 칸을 보는 중 | 공식 가이드 직접 근거 없음 | `[추론]` (web.dev CLS) |
| 바로 끼워 넣기 + 2~3초 강조 | 칸이 비었거나 방금 새로고침했을 때 | 보이는 카드를 밀어내지 않기 | web.dev CLS `[사실]` |
| 실행 취소 토스트 | 처리 완료 직후 | Fluent: 동작 없으면 7초, 최대 4개 | Fluent 2 `[사실]` |
| 칸 안 인라인 안내 | 동기화 실패 등 오류 | 오류는 사라지는 토스트로 쓰지 않음 | Carbon `[사실]` |
| 스크린리더 알림 | 새 항목 도착 | `role="status"` + `aria-live="polite"` | MDN `[사실]` |

전달 방식: SSE 권장 `[추론]` — 서버 → 화면 한 방향, 브라우저 자동 재연결 `[사실]`. HTTP/1.1은 도메인당 연결 6개를 모든 탭이 나눠 씀 `[사실]`. WebSocket은 양방향이라 과하고 다중 워커 시 중계 장치 필요 `[사실]`. APScheduler 저장 → 메모리 큐 → SSE, 워커 1개 기준 `[추론]`. 폴링 30~60초를 예비로 `[추론]`.

## 4. AI 메일 비서 · 그룹웨어

| 제품 | 할 일 표시 | 묶음 | 완료 |
|---|---|---|---|
| Viva Insights Briefing | 하루 1회 다이제스트, 상위 항목만 | Request(받은 요청) · Commitment(내 약속) · Follow-up(내가 요청) | Done · Remind me(다음 근무일) — 현재 발송 중단 `[사실]` |
| Inbox Zero (Reply Zero) | 라벨(Outlook은 범주) | To Reply · Awaiting Reply · Follow-up | 회신 오거나 보내면 자동 해제, 3일 경과 알림, Teams 알림 `[사실]` |
| Shortwave | 정리된 받은편지함 = 할 일 목록 | Bundles(한 줄로 접힘) · Splits | Done = 보관, Snooze `[사실]` |
| Spark | Smart Inbox, 홈에 "자리 비운 동안 온 메일" 개수 | People · Newsletters · Notifications | Done · Set aside · Snooze `[사실]` |
| NAVER WORKS | 메일 → Task(원본 메일 첨부) | My tasks | 완료 · 미완료 전환 `[사실]` |
| Dooray! | 메일 → 업무 등록, 보드 뷰 | 프로젝트 | 상태, 만기일 캘린더 표시 `[사실]` |
| Copilot in Outlook "Prioritize", Teams Planner, flow, JANDI, LG CNS 자체 도구 | — | — | `[미확인]` 페이지 접속 실패 |

## 5. 구성 권장안 (와이어프레임 입력값)

```
┌ D1 요약 바 ─────────────────────────────────────────────────────────────┐
│ 미처리 23 · 기한 지남 2 · 오늘 4 · 미룸 3      [보기: 기한 ▾] 15:40 ⟳ │
├ D2 칸 보드 (고정 폭 300~340px, 넘치면 가로 스크롤) ──────────────────────┤
│ 기한 지남 2 🔒 │ 오늘 4  +1 새 항목 │ 3일 내 7 │ 이후·기한 없음 10 │ + 칸 │
│ ┌──────────┐  │ ┌──────────┐      │          │                   │      │
│ │[요청] D+1 │  │ │[검토] 오늘│      │  ...     │                   │      │
│ │견적서 회신│  │ │계약서 검토│      │          │                   │      │
│ │김OO·상급자│  │ │박OO ★     │      │          │                   │      │
│ │ ✓  ⏰  ↗ │  │ │ ✓  ⏰  ↗ │      │          │                   │      │
│ └──────────┘  │ └──────────┘      │          │                   │      │
└──────────────────────────────────────────────────────────────────────────┘
   카드 클릭 → 오른쪽 미리보기(기존 wireframe R 재사용)   처리 → 토스트 [되돌리기]
```

1. **요약 바(D1):** 전체 미처리 · 기한 지남 · 오늘 · 미룸 건수를 항상 표시. 칸을 숨겨도 총계는 남아 누락을 막는다 `[추론]`.
2. **칸 = 저장된 필터:** 제목 · 색 · 필터(기한 상태 · 업무 · 발신자 등급 · 계정 · 대상자) · 정렬. 프리셋 보기 3개로 시작 `[추론]`
   - 기한 보드: 기한 지남 · 오늘 · 3일 내 · 이후/없음 (research_20261022 버킷과 같음)
   - 업무 보드: 회신 · 요청 · 검토 · 공지(접힘)
   - 사람 보드: 대상자별 칸
3. **두 번째 축:** 가로줄(핵심 발신자 / 일반) 켜기 · 끄기, 또는 카드 배지로만 표시.
4. **카드:** [업무 태그] · 요청 한 줄 · 발신자 · 기한 배지(색) · 우선순위 이유 배지(상급자 · 즐겨찾기 · 대상자) · ✓ 완료 · ⏰ 나중에 · ↗ 원문.
5. **누락 방지 안전장치:** 기한 지남 칸은 숨기기 · 삭제 불가 / 어느 칸에도 안 걸린 항목은 '미분류' 칸 자동 표시 / 읽음 ≠ 처리.
6. **자동 갱신:** SSE로 새 항목 도착 → 칸 머리 "+N 새 항목" → 누르면 반영 + 강조. 처리는 즉시 제거 + 7초 되돌리기 토스트. 동기화 실패는 칸 안 인라인 안내.
7. **모바일(768px 미만):** 칸 → 위쪽 탭(가로 스와이프), 요약 바는 한 줄로 축약.

## 6. 와이어프레임 전에 정할 것 → 2026-10-22 결정 (decisions D18)

| # | 질문 | 선택지 |
|---|---|---|
| Q1 | 기존 3단 메인과의 관계 | 새 홈 화면 / 3단 메인의 보기 전환(목록 ↔ 보드) |
| Q2 | 기본 보기의 칸 기준 | 기한 상태 / 업무 유형 |
| Q3 | 칸 설정 범위(1단계) | 프리셋 선택 + 숨김 · 순서만 / 칸 추가 · 편집까지 |
| Q4 | 한 항목이 여러 칸 조건에 맞을 때 | 앞 칸 하나만 / 모두 표시 |

결정: Q1 상단 메뉴 `대시보드 | 메일`로 나누고 대시보드 먼저 · Q2 기한 상태와 업무 유형 모두 칸 카테고리로 선택 · Q3 칸 추가 · 편집까지 · Q4 맞는 칸 모두에 표시.

## 7. 이 문서가 틀릴 수 있는 지점

- Microsoft To Do · Planner · Copilot "Prioritize" · Zendesk · Jira 가젯 페이지가 열리지 않았다. LG CNS 사용 환경(M365)과 겹치는 기능이 있는지 확인이 필요하다.
- "새 항목 N건 버튼" 패턴은 공식 가이드 근거 없이 원칙(CLS · 사용자 통제)에서 끌어낸 `[추론]`이다.
- 차별점("업무 유형별 자동 칸 보드 없음")은 확인한 제품 범위 안의 결론이다.

## 출처 (실제로 연 페이지)

- Superhuman Split Inbox: https://help.superhuman.com/hc/en-us/articles/38458392810643-Split-Inbox
- HEY: https://www.hey.com/features/reply-later/ · https://www.hey.com/features/set-aside/ · https://www.hey.com/features/reply-mode/
- GitHub: https://docs.github.com/en/account-and-profile/managing-subscriptions-and-notifications-on-github/viewing-and-triaging-notifications/managing-notifications-from-your-inbox
- Linear: https://linear.app/docs/inbox · https://linear.app/docs/my-issues · https://linear.app/docs/display-options
- Todoist: https://www.todoist.com/help/articles/use-the-board-layout-in-todoist-AiAVsyEI · https://todoist.com/productivity-methods/eisenhower-matrix
- Trello: https://support.atlassian.com/trello/docs/adding-dates-to-cards/ · Kanban WIP: https://www.atlassian.com/agile/kanban/wip-limits
- Freshdesk: https://support.freshdesk.com/support/solutions/articles/37626-understanding-ticket-views
- X Pro: https://help.x.com/en/using-x/how-to-use-x-pro · Slack: https://slack.com/help/articles/360043207674
- Notion: https://www.notion.com/help/boards · Grafana: https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/create-dashboard/
- monday.com: https://support.monday.com/hc/en-us/articles/360002187819-The-Dashboards
- react-grid-layout: https://github.com/react-grid-layout/react-grid-layout · gridstack: https://github.com/gridstack/gridstack.js
- NN/g: https://www.nngroup.com/articles/indicators-validations-notifications/
- Fluent 2 Toast: https://fluent2.microsoft.design/components/web/react/core/toast/usage · Carbon: https://carbondesignsystem.com/patterns/notification-pattern/ · Atlassian Flag: https://atlassian.design/components/flag/usage
- web.dev CLS: https://web.dev/articles/cls
- MDN SSE: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events · Live regions: https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Guides/Live_regions
- FastAPI SSE: https://fastapi.tiangolo.com/tutorial/server-sent-events/ · WebSockets: https://fastapi.tiangolo.com/advanced/websockets/
- Viva Briefing: https://learn.microsoft.com/en-us/viva/insights/personal/briefing/be-tasks
- Inbox Zero: https://docs.getinboxzero.com/essentials/reply-zero · Shortwave: https://www.shortwave.com/docs/guides/method/
- Spark: https://sparkmailapp.com/help/set-up-focus/home-screen
- NAVER WORKS: https://help.worksmobile.com/en/use-guides/mail/check-mail/mail-send-to-task/ · Dooray: https://dooray.com/main/service/project
