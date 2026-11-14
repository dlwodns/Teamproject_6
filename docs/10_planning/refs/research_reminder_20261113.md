# 메일 기반 업무 리마인더·에이전트 — 실제 제품·가이드라인 근거 조사

이 문서는 메일에서 업무와 기한을 뽑아 알려 주는 앱의 기능 27가지가 실제 제품이나 공신력 있는 가이드라인에서 뒷받침되는지 정리한 것입니다. 모든 확인일은 2026-11-13입니다.

확인 수준은 세 가지로 표시했습니다.

- 표시 없음: 페이지를 직접 열어 내용을 확인했습니다.
- `[부분 확인]`: 공식 도메인의 검색 결과 요약으로만 확인했습니다. 페이지가 403을 돌려주거나 다른 주소로 옮겨져 본문을 직접 읽지 못했습니다.
- `[미확인]`: 근거를 찾지 못했거나 확인하지 못했습니다. 추측으로 채우지 않았습니다.

---

## 1. 메일에서 뽑은 기한이 다가올 때 알림

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| Microsoft Outlook — 후속 조치 플래그 | 메일에 플래그를 달 때 시작일·기한과 알림 시각을 지정할 수 있습니다. 플래그를 단 메일은 To-Do 바, 작업, 일정의 일일 작업 목록에 나타나고, 알림은 팝업으로 뜹니다. | https://support.microsoft.com/en-us/outlook/flag-email-messages-for-follow-up | 2026-11-13 |
| Google 캘린더 — Gmail에서 가져온 일정 | 항공·숙박·식당 예약과 티켓 확인 메일을 읽어 캘린더 일정을 자동으로 만듭니다. 메일 링크 목록, 참조(CC)로만 받은 메일, 전달된 메일, 확인 메일이 아닌 메일에서는 일정을 만들지 않습니다. | https://support.google.com/calendar/answer/6084018 | 2026-11-13 |
| Microsoft To Do / Outlook My Day | 기한이 오늘인 미완료 작업으로 My Day를 매일 자동으로 채웁니다. 추천 창에는 기한이 지났거나 다가오는 작업을 보여 줍니다. | https://support.microsoft.com/en-us/outlook/create-and-manage-task-lists-with-my-day-in-outlook | 2026-11-13 |

참고로, 업무 요청 메일의 본문에서 기한을 자유롭게 뽑아 알려 주는 기능을 그대로 문서화한 주류 제품 페이지는 찾지 못했습니다 `[미확인]`. 위 출처들은 사람이 단 기한(Outlook)이나 예약 확인 메일(Google)을 다룹니다.

## 2. 처리하지 않은 요청을 N일 뒤 다시 알림 (Gmail Nudges)

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| Gmail 고객센터 — 중요한 이메일 알림(Nudges) | '답장할 이메일 제안'을 켜면 답장을 잊은 메일이 받은편지함 맨 위에 다시 나타납니다. 설정 > 일반 > Nudges에서 켜고 끌 수 있고, 대화 보기가 켜져 있어야 동작합니다. | https://support.google.com/mail/answer/6585?hl=en | 2026-11-13 |

Gmail 공식 페이지는 며칠이 지나야 다시 띄우는지 정확한 일수를 밝히지 않습니다 `[미확인]`.

## 3. 다시 알림(스누즈) 후 되살리기

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| Gmail — 이메일 다시 알림 | 고른 날짜·시각까지 메일을 받은편지함에서 숨겼다가, 그 시각이 되면 받은편지함 맨 위로 되돌려 놓습니다. 숨긴 메일은 '다시 알림' 폴더나 `in:snoozed` 검색으로 찾을 수 있습니다. | https://support.google.com/mail/answer/7622010 | 2026-11-13 |
| Microsoft Outlook — 다시 알림 | 새 Outlook과 웹용 Outlook에서는 메일을 다시 알림으로 보낼 수 있지만, 클래식 Outlook에서는 이 기능을 쓸 수 없습니다. | https://support.microsoft.com/en-us/article/6c5aa4d4-147a-4a0b-831b-eafc041e6028 `[부분 확인]` | 2026-11-13 |
| Superhuman — Remind Me | 메일을 지정한 시각에 다시 받은편지함으로 가져옵니다. '답장이 없으면' 조건으로 걸어 두었다가 답장이 오면 그 답장이 받은편지함에 들어오고 알림은 취소됩니다. | https://help.superhuman.com/hc/en-us/articles/43822934607251-Remind-Me `[부분 확인: 403]` | 2026-11-13 |
| Linear — Inbox 다시 알림 | 다시 알림을 걸면 선택한 시각까지 Inbox에서 알림을 숨겼다가 그 시각에 되돌려 놓습니다. | https://linear.app/docs/inbox | 2026-11-13 |

## 4. 내가 보낸 요청에 답이 없을 때 후속 조치 알림

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| Gmail Nudges — 후속 조치 제안 | '후속 조치할 이메일 제안'을 켜면 후속 조치가 필요할 수 있는 보낸 메일이 받은편지함 맨 위에 나타납니다. | https://support.google.com/mail/answer/6585?hl=en | 2026-11-13 |
| Boomerang for Gmail | 보낸 메일에 '답장이 없으면' 조건으로 알림을 걸면, 정한 시각까지 답장이 없을 때 메일을 받은편지함으로 되돌려 놓습니다. | https://help.boomeranggmail.com/article/241-how-to-track-responses | 2026-11-13 |
| SaneBox — SaneReminders | 보내는 메일의 숨은참조(BCC)에 `1week@sanebox.com` 같은 알림 주소를 넣으면, 상대가 그 전에 답하지 않았을 때 메일이 받은편지함으로 돌아옵니다. | https://sanebox.com/help/431-how-to-use-sanereminders | 2026-11-13 |
| Superhuman — Auto Reminders | 답장을 받지 못한 메일을 자동으로 다시 알려 주며, 어떤 메일을 지켜볼지는 설정에서 고릅니다. | https://help.superhuman.com/hc/en-us/articles/45270478397203-Reminders-on-Autopilot `[부분 확인: 403]` | 2026-11-13 |

## 5. 내가 보낸 메일 속 약속(commitment) 찾기

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| Microsoft Viva Insights — Briefing 일시 중지 안내 | 미처리 작업 알림은 최근 14일 동안 내가 보낸 메일과 동료가 메일로 보낸 요청을 바탕으로 만들어집니다. Briefing 메일 발송은 현재 멈췄고, 같은 기능은 Outlook 추가 기능의 '미처리 작업 보기'로 옮겨졌습니다. | https://learn.microsoft.com/viva/insights/personal/reference/briefing-pause | 2026-11-13 |
| Microsoft Learn — Briefing 개요(구 페이지) | '약속'은 내가 메일에서 다른 사람에게 하겠다고 한 일, '요청'은 다른 사람이 메일로 내게 부탁한 일, '후속 조치'는 내가 메일로 다른 사람에게 부탁한 일로 정의합니다. | https://learn.microsoft.com/en-us/Briefing/be-overview `[부분 확인: 현재 다른 주소로 이동]` | 2026-11-13 |

## 6. 다른 사람이 내게 약속한 일 추적

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| Microsoft Viva Insights — Briefing 일시 중지 안내 | Outlook 추가 기능에 '내 요청 후속 조치' 영역이 있어, 내가 동료에게 한 요청이 어떻게 되었는지 확인하도록 돕습니다. | https://learn.microsoft.com/viva/insights/personal/reference/briefing-pause | 2026-11-13 |

상대가 메일로 "제가 하겠습니다"라고 약속한 문장 자체를 뽑아 추적하는 기능을 공식 문서로 확인하지는 못했습니다 `[미확인]`. Viva의 정의는 '내가 한 부탁'을 기준으로 합니다.

## 7. 후속 메일에서 기한 변경 감지

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| Google 캘린더 — Gmail에서 가져온 일정 | 일정은 원본 메일과 동기화되어, 예약이 바뀌면 캘린더 일정도 함께 바뀝니다. | https://support.google.com/calendar/answer/6084018 | 2026-11-13 |

예약 확인 메일이 아닌 일반 업무 메일에서 기한 변경을 감지하는 제품은 확인하지 못했습니다 `[미확인]`.

## 8. 답장이 오거나 해결되면 알림 자동 해제

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| SaneBox — SaneReminders | 알림 시각 전에 상대가 답하면 알림을 취소합니다. 주소에 `.keep`을 붙이면 답장이 와도 알림을 남겨 둡니다. | https://sanebox.com/help/431-how-to-use-sanereminders | 2026-11-13 |
| Boomerang for Gmail | '답장이 없으면' 조건으로 예약한 후속 메일은, 답장이 오면 보내지 않고 취소 알림을 줍니다. 취소된 메일은 Boomerang-Outbox의 Cancelled 라벨에 보관됩니다. | https://help.boomeranggmail.com/article/241-how-to-track-responses | 2026-11-13 |
| Superhuman — Remind Me | '답장이 없으면' 조건으로 건 알림은 답장이 오면 취소됩니다. | https://help.superhuman.com/hc/en-us/articles/43822934607251-Remind-Me `[부분 확인: 403]` | 2026-11-13 |
| Android 알림 디자인 가이드 | 더 이상 의미가 없어진 알림은 사용자가 보지 않도록 직접 없애라고 권합니다. | https://developer.android.com/design/ui/mobile/guides/home-screen/notifications | 2026-11-13 |

## 9. 마지막 메일이 내게 던진 질문으로 멈춘 스레드

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| Gmail Nudges — 답장 제안 | 답장을 잊은 받은 메일을 받은편지함 맨 위로 다시 올립니다. 다만 '마지막 메일이 질문인지'를 기준으로 삼는다는 설명은 공식 문서에 없습니다. | https://support.google.com/mail/answer/6585?hl=en | 2026-11-13 |

'마지막 메시지가 나에게 묻는 질문'을 명시적인 기준으로 쓰는 제품은 확인하지 못했습니다 `[미확인]`.

## 10. 회의 전 준비 알림

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| Microsoft Viva Insights — Briefing 일시 중지 안내 | Briefing은 그날 처음 세 회의 가운데 관련 문서 검토 같은 제안이 있는 회의를 보여 주었습니다. 지금은 Outlook 추가 기능의 '회의 준비' 카드가 앞으로 7일의 회의를 보여 줍니다. Outlook 알림은 보통 일정 15분 전에 뜨고, 공유 문서 같은 사전 자료가 있으면 함께 보여 줍니다. | https://learn.microsoft.com/viva/insights/personal/reference/briefing-pause | 2026-11-13 |
| Microsoft Viva Insights in Outlook | '회의 준비' 카드에서 참석자 응답, 일정 충돌, 첨부 파일을 확인하고 15분이나 30분의 준비 시간을 예약할 수 있습니다. | https://support.microsoft.com/en-US/viva/insights/use-microsoft-viva-insights-in-outlook | 2026-11-13 |

Google 캘린더의 기본 알림 시각은 출처마다 10분과 30분으로 엇갈리고 공식 페이지를 찾지 못했습니다 `[미확인]`.

## 11. 기한 몰림·업무량 경고

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| Motion — 작업 상태 | 기한 뒤로 밀려 잡힌 작업을 '기한 초과(Past Due)'로 보고 빨간 느낌표를 붙입니다. 경고는 미리 떠서, 늦기 전에 일정을 바꾸거나 끝낼 수 있게 합니다. | https://www.usemotion.com/help/project-management/task/reference-tasks/task-states-and-task-types | 2026-11-13 |
| Sunsama — 주간 계획 | 주간 계획 단계의 'What remains' 카드로 계획한 일이 한 주 안에 들어가는지 확인합니다. | https://help.sunsama.com/docs/weekly-planning | 2026-11-13 |

Reclaim이 '위험' 경고를 띄운다는 공식 문서는 찾지 못했습니다 `[미확인]`. 검색된 자료는 겹친 일정을 조용히 다시 배치한다는 설명뿐이었습니다.

## 12. 반복 업무 예측

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| Todoist — 반복 날짜 | "every Monday"처럼 사용자가 입력한 반복 문구를 알아듣고 반복 일정으로 바꿉니다. 그러나 과거 행동에서 반복을 예측하는 기능은 문서에 없습니다. | https://todoist.com/help/articles/introduction-to-recurring-dates-YUYVJJAV | 2026-11-13 |
| SaneBox — SaneReminders | `every.monday@` 같은 주소로 반복 알림을 걸 수 있지만, 이것도 사용자가 직접 정합니다. | https://sanebox.com/help/431-how-to-use-sanereminders | 2026-11-13 |

메일 이력에서 반복 업무를 스스로 찾아 제안하는 주류 제품은 확인하지 못했습니다 `[미확인]`.

## 13. 맡긴 일(대기 중) 추적

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| Todoist — 팀 작업 관리 | 작업마다 담당자를 한 명 지정할 수 있습니다. `assigned by: me` 필터로 내가 맡긴 작업만 모아 진행 상황을 볼 수 있습니다. | https://todoist.com/help/articles/manage-team-tasks-in-todoist-S99543QzY | 2026-11-13 |
| Microsoft Viva Insights | Outlook 추가 기능의 '내 요청 후속 조치'로 동료에게 한 요청을 확인합니다. | https://learn.microsoft.com/viva/insights/personal/reference/briefing-pause | 2026-11-13 |
| Microsoft To Do / Outlook | '나에게 할당됨' 목록은 Planner에서 내게 맡겨진 작업을 모아 보여 줍니다. | https://support.microsoft.com/en-us/outlook/create-and-manage-task-lists-with-my-day-in-outlook | 2026-11-13 |

## 14. 참조(CC) 메일 중 나를 언급한 것

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| Microsoft Outlook — @멘션 | 본문에 @이름을 쓰면 그 사람이 받는 사람 줄에 추가됩니다. 받는 쪽은 '@ 나를 멘션함' 필터로 자신이 언급된 메일만 볼 수 있고, 메일 목록에는 @ 표시가 붙습니다. | https://support.microsoft.com/en-US/Outlook/mail/use-mentions-to-get-someone-s-attention-in-outlook | 2026-11-13 |
| GitHub — 알림 필터 | 알림 이유를 `mention`(직접 언급), `team-mention`(팀 언급), `assign`, `review-requested`처럼 나누고, 이 이유로 걸러 볼 수 있습니다. | https://docs.github.com/en/enterprise-cloud@latest/subscriptions-and-notifications/reference/inbox-filters | 2026-11-13 |
| Google 캘린더 | 참조로만 받은 메일에서는 일정을 자동으로 만들지 않습니다. 참조 메일을 낮게 다루는 제품 사례입니다. | https://support.google.com/calendar/answer/6084018 | 2026-11-13 |

## 15. 알림 피로 줄이기: 상한, 간격 늘리기, 묶어 보내기

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| NN/g — Push Notifications (2018-11-18) | 알림이 너무 많으면 사용자가 알림을 끄거나 앱을 지운다고 경고합니다. 한 번에 보낼 알림이 다섯 개를 넘으면 하나로 합치라고 권하고, 사용자와 관계없는 알림은 보내지 말라고 합니다. | https://www.nngroup.com/articles/push-notification/ | 2026-11-13 |
| Android 알림 디자인 가이드 | 같은 종류의 알림이 여럿이면 묶어서 요약 알림 하나로 보여 주라고 권합니다. 중요도를 HIGH·DEFAULT·LOW·MIN으로 나누고, 업무 알림은 DEFAULT(소리만 내고 화면에 끼어들지 않음)의 예로 듭니다. 덜 중요한 알림을 급한 것처럼 꾸미지 말라고도 합니다. | https://developer.android.com/design/ui/mobile/guides/home-screen/notifications | 2026-11-13 |
| Apple iPhone 사용 설명서 — 알림 요약 예약 | 고른 앱의 알림을 정한 시각에 모아 요약으로 받습니다. 요약은 우선순위 순으로 정렬되고, 요약 시각을 여러 개 둘 수 있습니다. | https://support.apple.com/en-asia/guide/iphone/iph6534c01bc/15.0/ios | 2026-11-13 |
| Linear — 알림 | 이메일 요약은 급한 정도에 따라 시간을 두고 보내며, 사용자가 이미 Linear 안에서 읽은 알림은 메일로 보내지 않습니다. | https://linear.app/docs/notifications | 2026-11-13 |

Slack에서 알림을 요약으로 묶어 보내는 기능은 공식 문서로 확인하지 못했습니다 `[미확인]`.

## 16. 방해 금지 시간·근무 시간 존중

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| Slack — 알림 일시 중지 | 알림 일정을 정하면 고른 요일과 시간에만 알림이 오고, 그 밖의 시간에는 멈춥니다. 다른 사람은 내 이름 옆의 표시로 알림이 멈춘 것을 알 수 있고, 급하면 하루 한 번 DM으로 이를 뚫을 수 있습니다. | https://slack.com/help/articles/214908388 | 2026-11-13 |
| Microsoft Teams — 모바일 조용한 시간 | 정한 시간이나 요일에는 모바일 알림을 끕니다. 메시지는 앱을 열면 그대로 볼 수 있고, 다른 사람에게는 알리지 않으며, 기기 현지 시각을 따릅니다. | https://support.microsoft.com/teams/platform/quiet-time-in-microsoft-teams-for-mobile-devices | 2026-11-13 |
| Apple — 집중 모드 | 집중 모드에서 특정 사람과 앱의 알림만 허용할 수 있습니다. | https://support.apple.com/en-asia/guide/iphone/iph21d43af5b/16.0/ios `[부분 확인: 본문 로드 실패]` | 2026-11-13 |

## 17. 부재 중 알림 멈춤과 복귀 후 따라잡기

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| 웹용 Outlook — 자동 회신 | 기간을 정해 자동 회신을 보내고, 그동안 캘린더를 막거나 새 초대를 자동으로 거절할 수 있습니다. | https://support.microsoft.com/en-US/Outlook/send-automatic-out-of-office-replies-from-outlook-com-or-outlook-on-the-web | 2026-11-13 |
| Microsoft Viva Insights in Outlook — 부재 계획 | 부재 일정 등록, 자동 회신 설정, 동료에게 알리기, 회의 거절, 부재 전후 집중 시간 예약을 점검 목록으로 안내합니다. | https://support.microsoft.com/en-US/viva/insights/use-microsoft-viva-insights-in-outlook | 2026-11-13 |
| Slack — 읽지 않은 메시지와 Catch up | 자리를 비운 동안 놓친 메시지를 모아 봅니다. 데스크톱의 '읽지 않음' 화면은 정렬과 필터를 지원하고, 모바일의 'Catch up'은 스와이프로 하나씩 읽음 처리합니다. | https://slack.com/help/articles/226410907 | 2026-11-13 |

## 18. 알림 안에서 바로 처리하기

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| Android 알림 디자인 가이드 | 펼친 알림에 추천 답장, 강조 버튼, 텍스트 버튼을 합쳐 최대 세 개까지 넣을 수 있습니다. 알림을 눌렀을 때와 똑같이 동작하는 버튼은 넣지 말라고 합니다. | https://developer.android.com/design/ui/mobile/guides/home-screen/notifications | 2026-11-13 |
| Gmail Android 앱 설정 | 펼친 알림 아래쪽의 기본 동작을 '삭제'나 '보관'으로 정할 수 있습니다. | https://support.google.com/mail/answer/2819492?hl=en | 2026-11-13 |
| Apple — 알림 사용 | 잠금 화면 알림을 길게 누르면 앱이 제공하는 빠른 동작을 쓸 수 있습니다. 왼쪽으로 밀면 그 앱의 알림을 1시간이나 하루 동안 끌 수 있습니다. | https://support.apple.com/108781 | 2026-11-13 |

## 19. 왜 표시했는지 설명하기

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| Gmail — 중요 표시 | 누구와 얼마나 자주 메일을 주고받는지, 어떤 메일을 열고 답하고 별표를 달고 보관하는지, 자주 읽는 메일의 키워드를 보고 중요 여부를 정합니다. 중요 표시에 마우스를 올리면 그 이유가 나옵니다. | https://support.google.com/mail/answer/186543?hl=en | 2026-11-13 |
| Microsoft HAX 가이드라인 G11 | 지침 11 "시스템이 왜 그렇게 했는지 분명히 하라(Make clear why the system did what it did)"입니다. | https://www.microsoft.com/en-us/haxtoolkit/library/ | 2026-11-13 |
| Google PAIR — 설명 가능성과 신뢰 | 사용자가 AI를 무조건 믿지 않고 적절한 만큼 믿도록 도와야 한다고 말합니다. 위험이 큰 상황에서는 결과만이 아니라 이유도 보여 주고, 전부가 아니라 판단에 영향을 주는 부분만 설명하라고 권합니다. | https://pair.withgoogle.com/chapter/explainability-trust/ | 2026-11-13 |
| GitHub 알림 | 알림마다 `mention`, `review requested` 같은 '이유' 라벨을 붙입니다. | https://docs.github.com/en/subscriptions-and-notifications/concepts/about-notifications | 2026-11-13 |

## 20. "내 일 아님 / 틀림" 피드백으로 조정하기

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| Gmail — 중요 표시 | 표시를 눌러 고치면 사용자가 무엇을 중요하게 여기는지 Gmail이 배운다고 안내합니다. | https://support.google.com/mail/answer/186543?hl=en | 2026-11-13 |
| Microsoft HAX 가이드라인 | 지침 8 "빠르게 무시할 수 있게", 지침 9 "빠르게 고칠 수 있게", 지침 13 "사용자 행동에서 배우라", 지침 15 "세분화된 피드백을 받으라"가 있습니다. | https://www.microsoft.com/en-us/haxtoolkit/library/ | 2026-11-13 |
| Google PAIR — 피드백과 제어 | 명시적 피드백의 선택지는 서로 겹치지 않아야 한다고 말합니다. 사용자가 이전 피드백을 고치고 시스템을 초기화할 수 있어야 한다는 문장도 있습니다("Allow users to adjust their prior feedback and reset the system."). | https://pair.withgoogle.com/chapter/feedback-controls/ | 2026-11-13 |

## 21. 아침 브리핑과 하루 마감 점검

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| Microsoft Viva Insights — Briefing | 매일 보내던 Briefing 메일에는 회의 준비, 미처리 작업, 집중 시간 예약이 들어 있었습니다. 지금은 발송을 멈췄고, 같은 기능은 Outlook 추가 기능과 Teams 앱으로 옮겨졌습니다. | https://learn.microsoft.com/viva/insights/personal/reference/briefing-pause | 2026-11-13 |
| Sunsama — 하루 마감 | 오늘 쓴 시간, 한 일, 못 끝낸 일을 보여 주는 화면을 거쳐 AI가 쓴 하루 요약을 고친 뒤 '오늘 끝'으로 마감합니다. 못 끝낸 일은 다음 날로 넘어갑니다. | https://help.sunsama.com/docs/daily-shutdown | 2026-11-13 |
| Microsoft To Do — My Day | 매일 그날 기한인 작업으로 목록을 자동으로 채웁니다. | https://support.microsoft.com/en-us/outlook/create-and-manage-task-lists-with-my-day-in-outlook | 2026-11-13 |

## 22. 주간 점검

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| Sunsama — 주간 계획·점검 | 주간 점검에서는 목표별 소요 시간과 진행, 끝낸 일, 하루별 생산성 차트를 본 뒤 AI가 쓴 요약을 고쳐 공유합니다. 기본 알림은 계획이 월요일 오전 8시, 점검이 금요일 오후 3시이고 설정에서 바꿀 수 있습니다. | https://help.sunsama.com/docs/weekly-planning | 2026-11-13 |

## 23. 유형별로 묶고 필터가 있는 알림함, 그리고 전체 페이지

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| GitHub — 받은편지함에서 알림 관리 | 오른쪽 위 아이콘으로 알림함 페이지를 엽니다. 왼쪽 사이드바에 '저장됨', '완료', 기본 필터(할당, 참여, 리뷰 요청, 멘션)가 있고, 직접 만든 필터를 15개까지 더할 수 있습니다. 항목마다 완료, 저장, 구독 해제를 할 수 있습니다. | https://docs.github.com/en/subscriptions-and-notifications/how-tos/viewing-and-triaging-notifications/managing-notifications-from-your-inbox | 2026-11-13 |
| Linear — Inbox | 알림 목록에서 항목을 고르면 관련 이슈가 Inbox 안에서 열립니다. 주의가 필요한 알림을 모은 'Priority' 탭이 있고, 다시 알림, 읽음 전환, 삭제를 단축키로 처리합니다. | https://linear.app/docs/inbox | 2026-11-13 |
| Atlassian Cloud — 앱 내 알림 | 'Direct' 탭은 내가 보고자·담당자이거나 멘션된 알림만 보여 주며, 종 아이콘 숫자는 이것만 셉니다. 'Watching' 탭은 내가 지켜보는 항목의 알림이고 기본적으로 숫자에 넣지 않습니다. | https://support.atlassian.com/atlassian-cloud/kb/overview-of-in-app-notifications-in-atlassian-cloud-products/ | 2026-11-13 |
| Slack — Activity | 멘션, DM, 스레드, 리마인더 등으로 필터링하고, 필터 조합을 상단 탭(저장된 보기)으로 만들 수 있습니다. | https://slack.com/help/articles/19693583638803 | 2026-11-13 |

## 24. 작은 팝오버와 전체 페이지 알림

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| Notion — Inbox | Inbox는 사이드바 위쪽에서 열리는 패널이고, 'Lock inbox pane open'으로 열어 둔 채 일할 수 있습니다. 페이지·댓글 스레드별로 묶이고, 읽음 상태와 유형으로 거를 수 있습니다. | https://www.notion.com/help/updates-and-notifications | 2026-11-13 |
| Atlassian Cloud | 종 아이콘을 누르면 알림 서랍(drawer)이 열립니다. 이 문서에는 전체 페이지 보기가 나오지 않습니다. | https://support.atlassian.com/atlassian-cloud/kb/overview-of-in-app-notifications-in-atlassian-cloud-products/ | 2026-11-13 |
| GitHub | 아이콘이 팝오버를 거치지 않고 바로 전체 알림함 페이지(github.com/notifications)로 이동합니다. | https://docs.github.com/en/subscriptions-and-notifications/how-tos/viewing-and-triaging-notifications/managing-notifications-from-your-inbox | 2026-11-13 |

같은 제품이 작은 팝오버와 전체 페이지를 함께 제공하고 '전체 보기'로 잇는다는 공식 문서는 찾지 못했습니다 `[미확인]`. 위 사례는 팝오버형(Notion, Atlassian)과 전체 페이지형(GitHub)을 따로 보여 줍니다.

## 25. 역할이 좁고 분명한 에이전트, 채팅만이 아닌 목록+채팅 혼합

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| NN/g — AI Chat Is Not (Always) the Answer (2024-03-01) | AI는 사람처럼 대화하거나 눈에 보일 필요가 없다고 말합니다. 개인화, 예측, 자동화를 기존 화면에 넣는 것이 대안이 될 수 있다고 봅니다. | https://www.nngroup.com/articles/ai-chat-not-the-answer/ | 2026-11-13 |
| NN/g — 10 Guidelines for Designing Your Site's AI Chatbots (2026-04-24) | 챗봇은 하나로 모으고, 첫 메시지에서 할 수 있는 주제를 밝혀 지나친 기대를 막으라고 권합니다. 추천 질문은 누를 수 있는 버튼으로 보여 주라고 합니다. | https://www.nngroup.com/articles/ai-chatbots-design-guidelines/ | 2026-11-13 |
| NN/g — Less Chat, More Answer (2026-04-17) | 사용자는 대화보다 빠르고 직접적인 답을 원한다고 봅니다. 인사말과 군더더기를 빼고 답부터 말하며, 도울 수 없으면 그렇다고 짧게 말하라고 권합니다. | https://www.nngroup.com/articles/less-chat-more-answer/ | 2026-11-13 |
| Microsoft HAX 가이드라인 G1·G2·G10 | 지침 1 "무엇을 할 수 있는지", 지침 2 "얼마나 잘할 수 있는지"를 분명히 하고, 지침 10은 확신이 없으면 범위를 좁히라고 합니다. | https://www.microsoft.com/en-us/haxtoolkit/library/ | 2026-11-13 |
| Copilot in Outlook | 스레드 요약과 초안 작성처럼 정해진 동작을 제공합니다. 초안은 사용자가 유지·수정·폐기를 고른 뒤 직접 보냅니다. | https://support.microsoft.com/en-us/outlook/welcome-to-copilot-in-outlook | 2026-11-13 |
| Slack — 리마인더 (비교 사례) | 리마인더는 메시지 메뉴의 '이것에 대해 알림'이나 `/remind` 명령으로 만들 수 있습니다. 그러나 확인과 수정은 목록형 To-dos 탭에서 기한 지남·예정 같은 필터로 합니다. 즉 채팅 명령만으로 리마인더를 다루지 않고 목록 화면을 따로 둡니다. | https://slack.com/help/articles/208423427 | 2026-11-13 |

## 26. 자동 발송 금지와 에이전트 동작 되돌리기

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| Google 블로그 — Gmail 보내기 취소 | 보낸 직후 '실행취소'를 누르면 메일이 임시보관함으로 돌아옵니다. 취소할 수 있는 시간은 기본 5초이고 10초, 20초, 30초로 늘릴 수 있습니다. | https://blog.google/products-and-platforms/products/gmail/how-to-unsend-email-gmail/ | 2026-11-13 |
| Microsoft HAX 가이드라인 | 지침 9 "빠르게 고칠 수 있게", 지침 16 "사용자 행동의 결과를 알려라", 지침 17 "전체를 한 번에 제어할 수 있게"가 있습니다. | https://www.microsoft.com/en-us/haxtoolkit/library/ | 2026-11-13 |
| Copilot in Outlook | AI가 만든 초안은 사용자가 고르고 고친 뒤 직접 보내며, 결과에 오류가 있을 수 있으니 검토하라고 안내합니다. | https://support.microsoft.com/en-us/outlook/welcome-to-copilot-in-outlook | 2026-11-13 |
| Gmail Nudges | 다시 알림은 알림일 뿐 메일을 대신 보내지 않습니다. 공식 문서는 알림만 설명하며, 대신 보낸다는 내용은 없습니다. | https://support.google.com/mail/answer/6585?hl=en | 2026-11-13 |
| Google PAIR — 피드백과 제어 | 사용자가 책임을 느끼거나 위험이 큰 일에서는 직접 통제하고 싶어 한다고 말합니다. 자동화를 끄는 방법과 수동 대안을 두라고 권합니다. | https://pair.withgoogle.com/chapter/feedback-controls/ | 2026-11-13 |

## 27. 왼쪽 탐색 + 목록 + 상세(3단) 레이아웃

| 출처 | 무엇을 하나 | URL | 확인일 |
|---|---|---|---|
| Android 개발자 문서 — 표준 레이아웃(Material 기반) | 목록-상세는 넓은 화면에서 두 창을 나란히 보여 줍니다. 좁은 화면에서는 한 번에 하나만 보이고 뒤로 가기로 목록에 돌아갑니다. 메시지 앱처럼 항목마다 추가 정보가 있는 앱에 맞는다고 설명합니다. | https://developer.android.com/guide/topics/ui/layout/canonical-layouts | 2026-11-13 |
| Microsoft Learn — Windows 앱 목록/상세 패턴 | 이 패턴은 이메일과 주소록에 자주 쓰인다고 설명합니다. 창 폭이 641epx 이상이면 나란히, 그보다 좁으면 쌓아서 보여 주라고 권합니다. | https://learn.microsoft.com/windows/apps/design/controls/list-details | 2026-11-13 |
| Microsoft Outlook — 읽기 창 | 고른 메일을 별도 창 없이 목록 옆이나 아래에서 읽게 하는 기본 레이아웃입니다. 새 Outlook은 오른쪽, 아래, 전체 화면, 팝아웃 전용을 고를 수 있습니다. | https://support.microsoft.com/en-us/outlook/use-and-configure-the-reading-pane-to-preview-messages-in-outlook | 2026-11-13 |

Fluent 2 사이트에서 목록-상세 레이아웃을 직접 정의한 페이지는 찾지 못했습니다 `[미확인]`. Microsoft 쪽 근거로는 Windows 앱 문서를 썼습니다.

---

## 가장 강한 근거 5개

1. **Gmail Nudges 공식 도움말** (2, 4, 9번)에 근거가 있습니다. 답장을 잊은 받은 메일과 후속 조치가 필요한 보낸 메일을 받은편지함 맨 위로 다시 올리는 기능을 Google이 직접 설명합니다. 메일 기반 다시 알림을 가장 크게 운영하는 사례입니다.
2. **Viva Insights Briefing 일시 중지 안내** (5, 6, 10, 21번)에 근거가 있습니다. 최근 14일의 보낸 메일과 받은 요청에서 할 일을 뽑고, 회의 준비와 내 요청 후속 조치를 아침에 알려 주던 기능을 Microsoft가 문서로 남겼습니다. 메일 발송을 멈추고 기능을 추가 기능 패널로 옮긴 사실도 참고할 만합니다.
3. **SaneBox·Boomerang의 '답이 없으면' 알림** (4, 8번)에 근거가 있습니다. 답장이 오면 알림이나 후속 메일을 자동으로 취소하는 규칙이 두 제품의 공식 도움말에 모두 나옵니다.
4. **Microsoft HAX 18개 지침과 Google PAIR 가이드북** (19, 20, 25, 26번)에 근거가 있습니다. 표시한 이유 설명(G11), 빠른 무시와 수정(G8·G9), 행동에서 배우기(G13), 할 수 있는 일 밝히기(G1·G2)를 직접 받쳐 줍니다.
5. **NN/g Push Notifications와 Android 알림 디자인 가이드** (15, 18번)에 근거가 있습니다. "다섯 개가 넘으면 하나로 합쳐라", 같은 종류는 묶어서 요약하라, 알림 버튼은 세 개까지라는 구체적인 숫자 기준을 줍니다.
