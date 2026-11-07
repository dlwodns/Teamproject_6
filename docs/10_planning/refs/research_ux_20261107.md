# 조사 정리 · UX v3.1 (브랜드 · 에이전트 화면 · 모핑 · 시트 · 알림) (2026-11-07)

> 목적: 와이어프레임 13절 · `../../20_frontend/design_system.md` · UX-D4~UX-D9의 근거를 모은다.
> 방법: 조사 에이전트 3개 — ① LG · LG CNS 브랜드(공식 CI 페이지 · lgcns.com CSS · 로고 SVG를 직접 받음) ② AI 에이전트 화면 벤치마크 ③ 버튼 모핑 · 바텀시트 · 알림 · 리마인더.
> 표시: `[사실]` 원문 확인 · `[계산]` 직접 계산 · `[제안]` 해석 · 권장 · `[미확인]` 확인 못 함. m3.material.io · Apple HIG는 JS로 그려지는 페이지라 본문을 읽지 못했고, openai.com은 403이라 인용 기사로 확인했다.

## 1. 브랜드

| 항목 | 값 | 근거 |
|---|---|---|
| LG Heritage Red | #A50034 (PMS 207C) | lg.com color · LG전자 CI `[사실]` |
| LG GRAY | #6B6B6B (밝은 바탕 로고 글자) | LG전자 CI `[사실]` |
| Active Red | #FD312E (3.71:1, 글자 금지) | lg.com color `[사실]` · `[계산]` |
| LG CNS 로고 SVG | 얼굴 #A50034 · 글자 #6B6B6B · 눈 · 입 흰색 | lgcns.com logo.svg `[사실]` |
| LG CNS 사이트 주 버튼 | #9B002E (누름 #610024). #A50034는 CSS 전체에 2번뿐 | clientlib-site CSS `[사실]` |
| 사이트 글자 · 면 | 글자 #121212 · #565656 · #8E8E8E · #AFAFAF, 면 #FFFFFF · #FBFBFC · #F7F8F9 · #F0F1F3 | 같은 CSS `[사실]` |
| 사이트 상태 · 팔레트 | error #EE1000 · success #19AB57, red400 #B20C00 · yellow400 #BE5C01 · green400 #209359 · blue400 #0755B9 | 같은 CSS `[사실]` |
| 토큰 참조 수 | 구분선 59 · 본문 글자 55 · 보조 글자 49 · 흰 면 27 · 주 버튼 11 · error 6 → 무채색 위주, 빨강은 포인트 | 같은 CSS `var()` 집계 `[사실]` |
| 사이트 서체 | 제목 · 본문 `"Pretendard JP", Pretendard`, 메인 배너만 Outfit 500/600/700 | `--typo-*` 변수 `[사실]` |
| LG 전용 서체 | LG EI Headline / LG EI Text(LG Smart UI 대체, LG전자 전용). 외부 사용 조건 · 한글 포함 여부 | lg.com typography `[사실]` · 라이선스 `[미확인]` |
| 대체 서체 라이선스 | Pretendard · Outfit 모두 SIL OFL 1.1(Outfit은 라틴만) | GitHub LICENSE `[사실]` |
| 로고 규정 | 비례 · 간격 · 크기 · 색 변경 금지, 여백은 마크 X-height, GRAY는 밝은 바탕 · WHITE는 어두운 바탕. 최소 크기 · LG CNS 전용 가이드 | lg.com logo · LG전자 CI `[사실]` · 최소 크기 `[미확인]` |
| 대비 | #A50034 vs #B20C00 1.11:1, #A50034 위 흰 글자 7.93:1, #6B6B6B 5.33:1, #8E8E8E 3.28:1 | `[계산]` |

**적용 `[제안]` → UX-D4로 채택:** 60% 무채색 면 · 35% 보조 4색 · 5% #A50034. 사이트의 #9B002E는 #A50034와 1.09:1이라 로고 값 하나로 통일.

## 2. AI 에이전트 화면 벤치마크

| 패턴 | 생김새 · 상태 | 예 |
|---|---|---|
| 작업 표시줄(Tool 카드) | 접히는 헤더(도구 이름 + 상태) → 입력 · 출력. Pending → Running → Awaiting Approval → Completed / Error / Denied | Vercel AI Elements Tool |
| 단계 기록 | 아이콘 + 단계 이름 + 짧은 설명이 세로로, 기본 접힘. complete / active / pending (+ error · retried 권장) | AI Elements ChainOfThought · Perplexity Steps · Shape of AI |
| 실행 계획 | 실행 전 단계 목록, 승인형 / 안내형 | Shape of AI Action plan · Notion |
| 할 일 체크리스트 | 하위 항목 + '완료 수 / 전체' | AI Elements Task |
| 승인 카드 | 대화 흐름 안 카드, 요청 문구 + 허용 / 거부, 응답 뒤 '승인됨' | AI Elements Confirmation · Linear elicitation · Gemini Agent |
| 초안 검토 | Keep · Discard · Regenerate | Copilot in Outlook |
| 진행 내레이션 · 끼어들기 | 지금 하는 일 문장 + 중지 · 직접 조작 | ChatGPT agent(인용) |
| 승인 수준 | 항상 묻기 / 위험한 것만(기본) / 묻지 않기. 메일 발송 · 일괄 삭제는 기본에서도 승인 | Notion Agent |

- 지연: Fluent 2는 1초 미만 표시 없음, 1~3초 스피너, 3초 넘으면 "아직 작업 중" 문구, AI 대화는 남은 시간을 추정하지 말라고 한다. NN/g는 단계 수("3/5 단계") 표시가 효과적이라고 본다. `[사실]`
- 공통: 진행 중엔 현재 단계 한 줄, 끝나면 요약 한 줄로 접힘, 오류면 펼침. 시간이 걸리는 작업엔 중지 수단. `[사실]`
- 확인: 확인한 예시 대부분이 대화 안 카드. NN/g — 되돌릴 수 없는 작업에만, 바뀌는 것을 구체적으로, 버튼은 동사, 미리 선택하지 않기, 가능하면 확인보다 되돌리기. `[사실]`
- 접근성: `role="status"` 영역 하나에 단계가 바뀔 때만 문구를 넣고 토큰 스트림은 읽히지 않는다. `[사실]`(구현 사례 · Rovo 접근성 이슈)

→ UX-D8 · wireframe 13-3.

## 3. 버튼 모핑 · 아래 시트 · 알림

| 항목 | 내용 | 근거 |
|---|---|---|
| 움직임 토큰 | M3 short 50~200 · medium 250~400 · long 450~600ms, emphasized (.2,0,0,1) · decelerate (.05,.7,.1,1) · accelerate (.3,0,.8,.15). Carbon fast-01 70 · moderate-02 240 · slow-01 400ms, 업무 화면은 productive | material-web 토큰 · Carbon motion `[사실]` |
| 로딩 표시 | 1초 미만엔 표시하지 않음, 성공 후 화면이 안 바뀌면 ✓ | Primer loading `[사실]` |
| 로딩 버튼 | `aria-disabled`(포커스 유지) + 숨긴 `aria-live` 문구 | Primer button a11y `[사실]` |
| View Transitions(같은 문서) | Chrome 111 · Safari 18 · Firefox 144 → Baseline(2025-10). React는 콜백 안 `flushSync` | Chrome docs · web.dev `[사실]` |
| `@starting-style` | Baseline 2024, dialog 진입 · 퇴장 | MDN `[사실]` |
| `interpolate-size` | Chrome · Edge 129만 | Chrome docs `[사실]` → 쓰지 않음 |
| 시트 폭 | M3 시트 최대 640dp, 큰 화면에선 최대 폭 · 떠 있는 시트 · 사이드 시트 | Compose · Flutter · material.io `[사실]` |
| 시트 사용 | 짧고 일시적인 내용만, 핸들만으로 닫게 하지 말 것, 겹쳐 쌓지 말 것, Back/Esc로 닫힘 | NN/g bottom sheet `[사실]` |
| 모달 포커스 | Tab 가두기 · Esc · 닫으면 원래 요소로, 되돌리기 어려우면 덜 파괴적인 버튼에 포커스 | WAI-ARIA APG dialog `[사실]` |
| 리마인더 벤치마크 | Outlook 리마인더 창(Dismiss · Snooze), Slack Later → To-dos(2026-10), Teams 활동 피드(읽지 않음 필터), Gmail 스누즈(오늘 나중에 · 내일 · 주말 · 다음 주 · 직접), GitHub(Done · Save) | 각 도움말 `[사실]` |
| 토스트 | 액션 없는 토스트 7초 · hover 멈춤 · 최대 4개 · 액션 1개(Fluent), 액션 있는 알림은 반응할 때까지 유지(Carbon) | Fluent · Carbon `[사실]` |
| iOS 웹 푸시 | iOS 16.4 이상, 홈 화면에 추가한 앱에서만, 사용자 동작 뒤 권한 요청 | OneSignal 문서 `[사실]` · webkit.org 원문 `[미확인]` |

→ UX-D6 · UX-D7 · UX-D9 · design_system 4절 · wireframe 13-4 · 13-5.

## 출처

- LG 색 https://www.lg.com/global/our-identity/color/ · 서체 https://www.lg.com/global/our-identity/typography/ · 로고 https://www.lg.com/global/our-identity/logo/ · LG전자 CI https://www.lge.co.kr/company/info/ci
- LG CNS 로고 https://www.lgcns.com/etc.clientlibs/lgcns/clientlibs/clientlib-site/resources/image/common/logo.svg · CSS https://www.lgcns.com/etc.clientlibs/lgcns/clientlibs/clientlib-site.lc-61a6c5029889d52e699821edd7e6ba1b-lc.min.css
- Pretendard https://github.com/orioncactus/pretendard/blob/main/LICENSE · Outfit https://github.com/google/fonts/tree/main/ofl/outfit
- Fluent 2 Wait UX https://fluent2.microsoft.design/wait-ux · Toast https://fluent2.microsoft.design/components/web/react/core/toast/usage · Motion https://fluent2.microsoft.design/motion
- Vercel AI Elements https://elements.ai-sdk.dev/components/tool · /confirmation · /task · /chain-of-thought
- Shape of AI https://shapeof.ai/patterns/action-plan · https://www.shapeof.ai/patterns/stream-of-thought
- NN/g https://www.nngroup.com/articles/progress-indicators/ · https://www.nngroup.com/articles/confirmation-dialog/ · https://www.nngroup.com/articles/bottom-sheet/
- Linear https://linear.app/developers/agent-interaction · Notion https://www.notion.com/help/choose-how-notion-agent-asks-for-your-approval
- Copilot in Outlook https://support.microsoft.com/outlook/copilot-pages/draft-an-email-message-with-copilot-in-outlook · Gemini Agent https://support.google.com/gemini/answer/16596215
- Atlassian Rovo https://atlassian.design/rovo-ui/ai-interaction-guidelines · 접근성 https://jira.atlassian.com/browse/ROVO-978
- M3 토큰 https://raw.githubusercontent.com/material-components/material-web/main/tokens/versions/v0_192/_md-sys-motion.scss · Carbon https://carbondesignsystem.com/elements/motion/overview/ · https://carbondesignsystem.com/components/notification/usage/
- Primer https://primer.style/ui-patterns/loading/ · https://primer.style/product/components/button/accessibility
- View Transitions https://developer.chrome.com/docs/web-platform/view-transitions/same-document · https://web.dev/blog/same-document-view-transitions-are-now-baseline-newly-available
- @starting-style https://developer.mozilla.org/en-US/docs/Web/CSS/@starting-style · height auto https://developer.chrome.com/docs/css-ui/animate-to-height-auto
- M3 시트 https://developer.android.com/reference/kotlin/androidx/compose/material3/BottomSheetDefaults · https://material.io/components/sheets-bottom · APG https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/
- Outlook https://support.microsoft.com/en-us/outlook/turn-off-or-postpone-a-reminder · Slack https://slack.com/help/articles/55757634348435 · Teams https://support.office.com/en-us/article/91c635a1-644a-4c60-9c98-233db3e13a56 · GitHub https://docs.github.com/en/enterprise-server@3.21/subscriptions-and-notifications/concepts/about-notifications
- iOS 웹 푸시 https://documentation.onesignal.com/docs/web-push-for-ios
