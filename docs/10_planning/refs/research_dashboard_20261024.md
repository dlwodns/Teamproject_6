# 조사 정리 · 대시보드 화면 레퍼런스 보강 (2026-10-24)

> 목적: `research_dashboard_20261022.md`(칸 구성 · 자동 갱신 · AI 메일 비서)를 기준으로 두고, D18 결정(상단 메뉴 분리 · 칸 카테고리 2종 · 칸 추가/편집 · 중복 표시)을 화면 배치로 옮길 근거를 보강한다.
> 방법: 조사 에이전트 2개 — ① 제품 '내 업무 홈' · 디자인 시스템(공식 도움말 16쪽) ② GitHub 오픈소스 보드(레포 9개, 파일 27개). 웹 검색은 조직 설정으로 막혀(403) 공식 페이지를 직접 열고, GitHub은 연결된 GitHub 도구로 코드를 읽었다. Dribbble · Mobbin 같은 이미지 허브는 JS 렌더링이라 내용을 읽지 못했다.
> 표시: `[사실]` 원문 · 코드 확인 · `[추론]` 해석 · `[미확인]` 확인 못 함

## 한눈에 보기

| 질문 | 결론 | 근거 |
|---|---|---|
| 기본 배치 | 요약 띠 + 가로 칸 보드 | 두 에이전트 모두 1순위. Carbon "가장 중요한 지표를 맨 위" `[사실]` |
| 모바일 | 칸 탭 대신 **세로 접이식 섹션**(모든 칸 건수가 한 화면에) | 탭은 한 번에 칸 하나만 보여 옆 칸 누락 위험 `[추론]` · Asana My tasks 섹션 `[사실]` |
| 드래그 앤 드롭 | 넣지 않음 | Vikunja는 필터로 만든 칸에서 드래그를 끈다(`ProjectKanban.vue`) `[사실]`. 필터 칸 사이 이동은 뜻이 정해지지 않음 `[추론]` |
| 칸 편집 UI | 칸 머리 ⋯ 메뉴 + 오른쪽 사이드 패널, 패널에 "지금 N건 해당" 미리 표시 | MS To Do ⋯ 메뉴 · Vikunja 인라인 제목 수정 `[사실]` / 패널 선택은 `[추론]`(모달 · 패널 실제 사례는 원문 확인 못 함) |
| 지울 수 없는 칸 | '미분류' 칸 고정 | Focalboard "No {property}" 칸 삭제 불가 · Asana 'Recently assigned' 삭제 불가 `[사실]` |
| 칸 저장 구조 | `filter_json`(필드 · 조건 · 값을 AND로 묶음) + `position`(실수) | Focalboard `filterClause.ts` · Plane `view-props.ts`(AND만) · Vikunja `project_view.go` `[사실]` |
| 기한 상태 계산 | 저장하지 않고 응답할 때 계산(KST) | Vikunja는 날짜 필터를 크론이 1분마다 재계산 `[사실]` → 계산 시점을 읽을 때로 옮기면 크론 불필요 `[추론]` |
| 필터 변경 시 | 기존 업무도 다시 평가 | Copilot Prioritize는 바꾼 기준을 지난 메일에 적용하지 않음 `[사실]` → 누락 위험이라 따르지 않음 `[추론]` |
| 일괄 처리 | 선택하면 보드 위에 일괄 처리 막대, 일괄 모드에서는 카드 개별 동작 끔 | Carbon Data table `[사실]` · shadcn tasks 예제 체크박스(일부 선택 시 중간 상태) `[사실]` |
| 빈 칸 | 다 처리한 칸 = 축하 문구, 필터 결과 0건 = 중립 문구 + [필터 수정] | Atlassian Empty state `[사실]` |
| 배지 색 | 기한 배지는 의미 색, 사용자가 고른 칸 색은 장식 색으로 분리 | Atlassian Lozenge `[사실]` |
| 카드 문구 | 제목 = 메일 제목, 상세에 [원문 열기] | MS To Do 플래그 메일 `[사실]` · inbox-zero 알림 동작 'Open in Gmail' + 'Mark done' `[사실]` |

## 1. 제품 · 디자인 시스템 (에이전트 ①)

| 제품 | 화면 구조 | 칸 · 섹션 편집 | 가져올 것 |
|---|---|---|---|
| MS To Do · My Day | 오늘 목록, 전구 아이콘으로 추천 열기 `[사실]` | 고정 스마트 목록, 밤에 비우고 못 끝낸 일은 다음 날 추천 `[사실]` | '비우되 숨기지 않음' — 2단계 '오늘 집중' 후보 `[추론]` |
| MS To Do · 플래그 메일 | 플래그 메일이 할 일로 들어옴, 처음 켜면 최근 30일 100개 `[사실]` | — | 카드 제목 = 메일 제목, 상세에 'Open in Outlook' `[사실]` |
| MS To Do · 목록 꾸미기 | 목록 오른쪽 위 ⋯ `[사실]` | ⋯에서 색 · 배경 `[사실]` | 칸 색 편집 진입점 = 칸 머리 ⋯ |
| Outlook · My Day 창 | 일정 탭 · To Do 탭 `[사실]` | 메일을 끌어 할 일로 `[사실]` | LG CNS(M365) 사용자에게 익숙한 흐름 `[추론]` |
| Copilot in Outlook · Prioritize | 목록 안 ↑ 화살표, 높음만 필터 · 우선순위 그룹 정렬 `[사실]` | 설정에서 자연어 기준, 지난 메일 재평가 없음 `[사실]` | 카드에 '들어온 이유' 배지. 재평가 없음은 따르지 않음 |
| Asana · My tasks | 목록 · 보드 · 캘린더 보기 `[사실]` | 사용자 섹션 생성 · 순서 · 삭제, 기본 섹션 삭제 불가, 보기별 필터 · 정렬 저장 `[사실]` | 삭제 불가 시스템 칸, 안 연 업무 파란 점 |
| Atlassian · Lozenge / Empty state | 빈 상태: 그림(선택) → 제목 → 설명 → 버튼 `[사실]` | — | 의미 색 / 장식 색 분리, 다 끝낸 상태는 축하 어조 |
| Fluent 2 · Card / Badge | Header · 본문 · Footer 슬롯 `[사실]` | 선택 카드 floatingAction `[사실]` | 카드 Footer에 ✓ ⏰ ↗, 선택 체크는 오른쪽 위 |
| Carbon · Dashboard / Data table | F자 순서, KPI 위 `[사실]` | 일괄 처리 막대, 일괄 모드에서 개별 동작 끔 `[사실]` | 요약 띠 맨 위, 일괄 막대는 보드 위에 덮어 띄움 |

`[미확인]`: Planner '내 작업', ClickUp Home, monday My Work, Jira Your work(열리지 않음 · robots 차단), Material 3 · Ant Design Pro(JS 페이지), Sunsama · Akiflow · Height · Basecamp(시도 안 함)

## 2. GitHub 오픈소스 (에이전트 ②)

| 레포 | 칸 정의 구조 | 칸 편집 · 카드 | 가져올 것 |
|---|---|---|---|
| go-vikunja/vikunja | `bucket_configuration_mode(none/manual/filter)`, `bucket_configuration[{title, filter}]`, `position(float)`, 필터 칸 최대 50개 `[사실]` | 칸 제목 인라인 수정, ⋯ 메뉴(개수 제한 · 접기 · 삭제), 마지막 칸 삭제 불가, 칸 폭 300px, 태블릿 이하 가로 스냅 `[사실]` | 필터 칸 = 드래그 끔, float 순서, 칸 머리 `count` |
| mattermost-community/focalboard | `filter: {operation: and/or, filters: [{propertyId, condition, values[]}]}` `[사실]` | 칸 머리 인라인 수정 · 숨기기 · 색, 값 없는 카드를 받는 칸은 삭제 불가 `[사실]` | 필터 JSON 모양, '미분류' 칸 |
| makeplane/plane | `rich_filters`(AND만), `display_filters{group_by, order_by, show_empty_groups}`, `display_properties{…: boolean}` `[사실]` | Add view → 이름 → 레이아웃 → 필터 → Create, 저장 안 하면 변경 사라짐 `[사실]` | 카드 표시 필드를 불리언으로, 빈 칸 표시 옵션 |
| kanboard/kanboard | `custom_filters(name, filter, is_shared)` `[사실]` | `[미확인]` | 가장 단순한 저장 구조 |
| shadcn-ui/ui tasks 예제 | 표(칸 보드 아님) `id, title, status, label, priority` `[사실]` | 전체 선택(중간 상태), 행 ⋯ 메뉴 `[사실]` | 일괄 처리 체크박스 |
| Georgegriff/react-dnd-kit-tailwind-shadcn-ui | `Column{id,title}`, `Task{columnId}` — 업무 1개 = 칸 1개 `[사실]` | 모바일 `snap-x snap-mandatory` `[사실]` | 드래그가 필요해지면 @dnd-kit 참고 |
| elie222/inbox-zero | 라벨 To Reply · Awaiting Reply, 회신 시 Follow-up 자동 해제, 기준일 기본 3일 · 주말 제외 `[사실]` | 알림 동작 'Open in Gmail' · 'Mark done' `[사실]` | '3일 내'를 영업일로 셀지 결정 필요 |
| plankanban/planka · tremorlabs/tremor | React + react-beautiful-dnd + socket.io / 복사형 컴포넌트(Card · Badge · Toast) `[사실]` | `[미확인]` | 실시간은 SSE로 충분 `[추론]` |

`[미확인]`: 스타 수 전부(검색 결과에 없음), Plane 연산자 목록 · 드래그 라이브러리, Focalboard 카드 필드, wekan · AppFlowy · Huly

## 3. 후보 비교와 선정

| 기준 (가중) | A 요약 띠 + 가로 칸 | B '오늘 집중' 고정 칸 + 보드 | C 섹션 목록 ↔ 보드 전환 |
|---|---|---|---|
| D13 누락 0 (×3) | ○ 요약 띠 총계 + 미분류 칸 | △ 하루 지나면 비우는 규칙이 숨김처럼 보임 | ○ 모든 섹션 건수 한 화면 |
| D18 확정 사항 (×3) | ○ 1:1 일치 | △ 시스템 칸이 하나 늘어 '사용자 칸 편집'과 범위 조정 필요 | △ 기본을 목록으로 두면 '칸 보드'와 어긋남 |
| 구현 비용 · MVP 10/31 (×2) | ○ 중간(flex + 가로 스크롤) | × 추천 로직 추가 | ○ 낮음(리스트 반복) |
| 모바일 (×1) | × 칸 하나씩만 보임 | × | ○ |
| 익숙함 · M365 (×1) | ○ | ○ My Day | ○ |

**선정: A를 데스크톱 · 태블릿 기본으로, 768px 미만은 C의 세로 섹션으로 같은 데이터를 다시 그린다.** B의 '오늘 집중 · 추천'은 2단계로 미룬다. 판단은 `[추론]`이며 근거는 위 표다.

## 4. 이 문서가 틀릴 수 있는 지점

- 칸 편집을 모달이 아닌 사이드 패널로 둔 근거는 원칙(보드를 가리지 않음)뿐이다. 실제 제품 사례는 확인하지 못했다.
- 모바일 세로 섹션은 칸이 많으면(7개 이상) 스크롤이 길어진다. 접기 상태 기억으로 대응하지만 사용성은 검증 전이다.
- 서버에서 칸마다 메모리 필터링을 하는 방식이 업무 1,000건(D11) 규모에서 충분히 빠르다는 것은 `[추론]`이다. 테스트로 확인해야 한다.
- M365(Planner · Copilot) 쪽 겹치는 기능은 이번에도 일부만 확인했다.

## 출처 (실제로 연 페이지 · 파일)

- Microsoft: https://support.microsoft.com/en-us/ToDo/my-day-and-suggestions · https://support.microsoft.com/en-us/todo/using-microsoft-to-do-with-flagged-email-from-outlook · https://support.microsoft.com/en-us/todo/customize-your-lists · https://support.microsoft.com/en-us/topic/6de6ee52-751b-4405-b389-850572b15306 · https://support.microsoft.com/en-us/Outlook/copilot-outlook/prioritize-my-inbox
- Asana: https://help.asana.com/s/article/my-tasks
- Atlassian: https://atlassian.design/components/lozenge/usage · https://atlassian.design/components/empty-state/usage
- Fluent 2: https://fluent2.microsoft.design/components/web/react/core/card/usage · https://fluent2.microsoft.design/components/web/react/core/badge/usage
- Carbon: https://carbondesignsystem.com/patterns/empty-states-pattern/ · https://carbondesignsystem.com/data-visualization/dashboards/ · https://carbondesignsystem.com/components/data-table/usage/
- Vikunja: `pkg/models/project_view.go` · `pkg/models/saved_filters.go` · `frontend/src/components/project/views/ProjectKanban.vue` · `frontend/src/components/tasks/partials/KanbanCard.vue` · https://vikunja.io/docs/filters
- Focalboard: `webapp/src/blocks/boardView.ts` · `filterClause.ts` · `filterGroup.ts` · `webapp/src/components/kanban/kanbanColumnHeader.tsx`
- Plane: `packages/types/src/views.ts` · `view-props.ts` · https://docs.plane.so/core-concepts/views
- Kanboard: `app/Model/CustomFilterModel.php` · Planka: `client/package.json`
- shadcn-ui: `apps/v4/app/(app)/examples/tasks/data/schema.ts` · `components/columns.tsx`
- Georgegriff/react-dnd-kit-tailwind-shadcn-ui: `BoardColumn.tsx` · `TaskCard.tsx` · `package.json`
- inbox-zero: `docs/essentials/reply-zero.mdx` · Tremor: `src/components/`
