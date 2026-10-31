# 조사 정리 · 대시보드 v2 (브랜드 · 화면 패턴) (2026-10-24)

> 목적: 대시보드 재구성(원형 진행률 · 2열 업무 칸 · 오른쪽 위 메뉴 · 설정 · 에이전트 자리)과 LG CNS 브랜드 적용 근거를 모은다.
> 방법: 조사 에이전트 2개 — ① LG · LG CNS 브랜드(공식 CI 페이지 · LG CNS 사이트 CSS) ② 화면 패턴(도넛 · 내비게이션 · 패널 · 드래그 · 모션 · 에이전트). 웹 검색이 조직 설정으로 막혀 공식 페이지를 직접 열었다.
> 표시: `[사실]` 원문 확인 · `[계산]` 직접 계산 · `[추론]` 해석 · `[미확인]` 확인 못 함

## 1. 브랜드

| 항목 | 값 | 근거 |
|---|---|---|
| LG RED | #A50034 (RGB 165/0/52, PANTONE 207C) | lg.co.kr CI `[사실]` |
| LG GRAY | #6B6B6B (K70) | lg.co.kr CI `[사실]` |
| LG CNS 사이트 서체 | 제목 · 본문 Pretendard, 영문 · 숫자 Outfit | lgcns.com CSS 변수 `[사실]` |
| LG CNS 사이트 회색 · 의미 색 | 글자 #121212 · #565656, 배경 #F7F8F9, 위험 #B20C00, 완료 #209359, 정보 #0755B9 | lgcns.com CSS `[사실]` |
| LG CNS 전용 CI 가이드 · 로고 파일 | 찾지 못함 | `[미확인]` |
| 로고 규정 | 변형 · 재조합 금지, 여백 필요. LGE 사이트 자산은 개인 · 비상업 용도만 | lg.co.kr · lg.com/legal `[사실]` |

**적용 규칙 `[제안]`**
- 브랜드 레드 #A50034는 주 버튼 · 선택된 메뉴 · '요청' 태그 · 강조 아이콘에만 쓴다. 상태(기한 지남)는 위험 색 #B20C00만 쓴다.
- 두 빨강의 대비는 1.11:1이라 색으로 구분되지 않는다 `[계산]`. 그래서 모양으로 나눈다: 브랜드 = 채운 버튼, 위험 = 옅은 배경 칩 + ⚠ 아이콘 + 글자.
- 원형 진행률에는 브랜드 레드를 쓰지 않는다. 완료 #209359, 남은 부분은 같은 계열의 옅은 색 #E3F1E8.
- 로고는 그리지 않는다. 상단 바에 'LG CNS 로고 자리(승인 후 교체)' 점선 상자(120×32px)를 둔다. 파일과 사용 허락은 과제 담당자에게 받는다.
- 대비: 흰 배경 위 #A50034 글자 7.93:1, #B20C00 7.13:1, #565656 7.34:1 `[계산]`. Active Red #FD312E(3.71:1)는 글자에 쓰지 않는다.

## 2. 화면 패턴

| 주제 | 핵심 규칙 | 적용 | 근거 |
|---|---|---|---|
| 원형 진행률 | 부분과 전체 관계에만, 조각은 적게, 범례 대신 직접 라벨, 색만으로 의미 전달 금지 | 조각은 완료 · 미완료 2개. '새 알림'은 전체의 일부가 아니라 따로 숫자로 표시. `role="img"` 대체 문구 | GOV.UK Analysis Function `[사실]` |
| 메뉴 위치 | 세로 메뉴는 왼쪽 권장, 오른쪽은 'right-rail blindness' | 사용자 결정으로 **오른쪽 위 가로 메뉴**(세그먼트)로 둬서 화면 폭을 쓰지 않음 | NN/g Vertical Nav `[사실]` |
| 원본 메일 보기 | 맥락을 유지하며 빠르게 볼 때는 비모달 | 오른쪽 480px 비모달 패널, Esc · × 닫기, 여러 단계 작업은 "메일 화면에서 열기" | NN/g modal vs nonmodal · Fluent Drawer `[사실]` |
| 패널 개수 | 오른쪽 패널은 한 번에 하나 | 메일 패널과 에이전트 패널은 동시에 열지 않음 | Carbon UI shell right panel `[사실]` |
| 드래그 재배치 | 손잡이 · 원래 자리 opacity 0.4 · 놓은 뒤 강조 700ms · 키보드 대체 수단 필수 | 손잡이(⠿) 끌기 + 눌러서 '위로/아래로/맨 위로/맨 아래로' 메뉴 | Atlassian Pragmatic DnD `[사실]` |
| 모션 | standard (0.2,0,0,1), Medium 250~400ms · 동작 줄이기 지원 | 카드 이동 250ms, 패널 300ms, 원형 채우기 500ms, `prefers-reduced-motion` + 설정 토글 | M3 Motion · Fluent tokens · WCAG 2.3.3 `[사실]` |
| 에이전트 패널 | 오른쪽 패널 + 아래 입력창, 작업은 확인 카드 검토 후 확정 | 360px 인라인 패널(본문을 밀어냄), 제안 카드 [실행 · 수정 · 무시], 지금은 '준비 중' | Gemini in Gmail `[사실]` / 폭은 `[추론]` |

`[미확인]`: Copilot in Outlook · Teams 측면 창 폭, Outlook · Gmail 템플릿 화면, Carbon 도넛 사용 규칙, Material 3 원형 진행률

## 3. 반론 · 위험

- 원형 진행률은 남은 양을 가린다(200건 중 90%여도 20건 남음). 미완료 숫자를 같은 크기로 함께 표시했다.
- 대시보드 배치를 사용자마다 바꾸면 지원 · 설명이 어려워진다. '기본 배치로 되돌리기'를 필수로 둔다.
- 자동 분류가 틀리면 2열(업무 성격) 칸 전체를 믿지 않게 된다. 업무 태그에서 바로 '분류 고치기'가 필요하다(다음 작업).
- 더미 메일 정답 라벨에는 '문의'가 없다. 요청류 → 요청, 회신 → 보고, 공지 · 참조 → 공지로 묶는 매핑은 `[추론]`이며 평가 기준을 다시 정해야 한다.

## 출처 (실제로 연 페이지)

- https://www.lg.co.kr/about/ci/element · https://www.lg.com/global/our-identity/color/ · https://www.lg.com/global/our-identity/typography/ · https://www.lg.com/global/our-identity/logo/ · https://www.lg.com/global/legal/
- https://www.lgcns.com/etc.clientlibs/lgcns/clientlibs/clientlib-site.css
- https://analysisfunction.civilservice.gov.uk/policy-store/data-visualisation-charts/
- https://www.nngroup.com/articles/vertical-nav/ · https://www.nngroup.com/articles/modal-nonmodal-dialog/
- https://carbondesignsystem.com/components/UI-shell-right-panel/usage/ · https://fluent2.microsoft.design/components/web/react/core/drawer/usage
- https://atlassian.design/components/pragmatic-drag-and-drop/design-guidelines · https://dndkit.com/legacy/guides/accessibility/
- github material-components-android `docs/theming/Motion.md` · microsoft/fluentui `packages/tokens/src/global/durations.ts` · `curves.ts`
- https://www.w3.org/WAI/WCAG21/Understanding/animation-from-interactions.html · https://getbootstrap.com/docs/5.3/components/scrollspy/
- https://support.google.com/mail/answer/14199860 · https://ant.design/components/progress
