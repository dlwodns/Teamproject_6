# 조사 정리 · Outlook 대체 범위와 Graph 연결 계획 (2026-11-19)

> 목적: "Outlook에서 되는 건 우리 서비스에서도 되게 하자"는 방향 전환에 따라, Outlook 웹의 기능 전체와 우리 현황을 맞대 보고 Microsoft Graph로 가져오는 방법 · 순서 · 완주 가능성을 남긴다.
> 방법: ① Outlook 웹(새 Outlook, 한국어 화면)을 브라우저로 직접 열어 메일 · 쓰기(리본 5개 탭) · 일정 · To Do · 사람 · 앱 더보기를 확인했다(11-19). ② Microsoft 지원 문서 2곳(새 Outlook 시작하기 · 단축키)과 Graph v1.0 공식 문서 약 20곳을 읽었다.
> 개인 정보: 화면 속 메일 제목 · 주소 · 계정 이름은 옮기지 않았다.
> 표시: **[확인]** 화면 또는 공식 문서에서 확인 · **[불확실]** 공식 문서에서 찾지 못함 · **[판단]** 우리 쪽 해석과 제안
> 이전 조사: `research_outlook_20261107.md`(읽기 · 쓰기 화면 구성) · `research_outlook_features_20261113.md`(메일 관리 기능 6가지) · `research_20261022.md` 3절(계정 연결 방식)

## 0. 결정 (11-19)

- 상태: 채택 · 제안 · 결정: 문규남(11-19) · 리뷰: [미정]
- **범위를 뒤집는다.** README의 "만들지 않는 것: 메일 앱 대체 · 외부 캘린더 쓰기"를 지우고, 우리 앱 하나에서 메일 · 일정 · 할 일을 다 할 수 있게 한다.
- **Graph 연결(BE-7)을 먼저 한다.** 화면을 더미 위에서 먼저 넓히지 않는다.
- 그대로 두는 것: 보내기는 사용자가 [보내기]를 눌렀을 때만(D48). 서비스 경로 외부 LLM 호출 0건(D41). 메일 본문은 저장하지 않음(구조도 10절).
- 바꿀 문서: 6절.

## 1. 구조 — Outlook 데이터를 우리 API로 보여 준다

```
Outlook 사서함(Exchange Online)
   ▲ ▼  Microsoft Graph (OAuth 위임 권한, 사용자 토큰)
backend  ── 메일 원본 커넥터 outlook_graph (mail/connectors/)
   │        · 동기화해 저장: 메일 머리(보낸 사람 · 제목 · 시각 · 폴더 · 읽음 · 플래그) → 분류 · 리마인더 · 대시보드가 쓴다
   │        · 그때그때 가져옴: 본문 · 첨부 · 일정 범위 · 할 일 목록 (저장하지 않음)
   │        · 바꾸기: 보내기 · 이동 · 삭제 · 읽음 · 플래그 · 범주 · 일정 · 할 일 → Graph에 바로 쓴다
   ▼ HTTP (지금과 같은 우리 API 모양)
frontend ── 우리 화면만 그린다(Outlook 화면을 끼워 넣지 않는다)
```

- [판단] 사서함은 Exchange에 그대로 있으므로 우리 앱에서 바꾼 것은 Outlook에도 보이고, Outlook에서 바꾼 것은 동기화(델타)로 우리에게 온다. 그래서 **Outlook을 100% 따라 만들지 않아도 된다** — 그리기 · 메일 병합처럼 드문 기능은 같은 사서함을 Outlook에서 열어 쓰면 된다.
- [판단] 프론트엔드는 지금 API 모양을 유지하고 `MAIL_SOURCE=dummy | outlook_graph`로 원본만 바꾼다. 더미는 시연 대비용으로 남긴다(R1).

## 2. Outlook 기능과 우리 현황

### 2.1 메일 목록 · 읽기 [확인]

| Outlook | 우리 (11-19) | 넣을 단계 |
|---|---|---|
| 폴더: 받은 · 보낸 · 임시 · 보관 · 지운 편지함, 즐겨찾기, 그룹 | 업무 기준 메일함(상급자 · 마감 등)만, 실제 폴더 없음 | 1 |
| 중요 / 기타 탭, 필터, 정렬 | 업무 분류가 그 역할 | 유지 |
| 삭제 · 보관 · 이동 · 지운 편지함 비우기 | 없음 | 1 |
| 회신 · 전체 회신 · 전달 | 회신만 | 1 |
| 읽음 · 안 읽음 · 고정 · 다시 알림 | 있음(FE-5d) | 1에서 Graph에 씀 |
| 플래그 · 범주 | 우리식 플래그 4종(UX-D13), 범주 없음 | 2 |
| 검색 | 없음 | 1 |
| 정크 · 피싱 신고, 빠른 단계, 규칙, 인쇄, 번역, 반응 | 없음 | 뺌(Outlook에서) |
| 이 메일 요약(Copilot) | 메일 요약 있음(UX-D15) | 유지 |
| 보기 탭: 대화 묶기 · 밀도 · 레이아웃 · 확대/축소 · 몰입형 리더 | 없음 | 뺌 |

### 2.2 메일 쓰기 [확인] (리본 메시지 · 삽입 · 텍스트 서식 지정 · 그리기 · 옵션)

| Outlook | 우리 | 넣을 단계 |
|---|---|---|
| 새 메일, 받는 사람 · 참조 · 숨은 참조, 보낸 사람 고르기 | 답장만, 받는 사람 고정 | 1 |
| 첨부 · 링크 · 서명 | 없음 | 1(첨부 3MB 미만) · 2(큰 첨부) |
| 서식: 굵게 · 기울임 · 밑줄 · 취소선 · 글머리 · 번호 · 들여쓰기 · 링크 · 서식 지우기 | 없음(UX-D5에서 뺌) | 2 |
| 글꼴 · 크기 · 색 · 강조 · 맞춤 · 위/아래 첨자 · 인용 · 스타일 | 없음 | 뺌 |
| 초안 저장(임시 보관함) | 없음 | 1 |
| 예약 전송 | 없음 | 2 |
| 중요도 높음 · 낮음 | 없음 | 2 |
| 메일 템플릿 | 템플릿 있음(우리 방식이 더 강함) | 유지 |
| 받아쓰기 · 편집자 | 음성 입력 · 격식체 다시 쓰기 있음 | 유지 |
| 사진 · 표 · 이모지 · 녹음 · 투표 · 설문 · Loop · 그리기 · 메일 병합 · 민감도 · 암호화 · 일반 텍스트 전환 | 없음 | 뺌 |

### 2.3 일정 [확인]

| Outlook | 우리 | 넣을 단계 |
|---|---|---|
| 일 · 근무 주 · 주 · 월 · 분할 보기, 미니 달력 | 달 보기 + 고른 날 목록(FE-D24) | 2(주 보기) |
| 새 이벤트: 제목 · 시간 · 장소 · 본문 · 알림 · 반복 | 이벤트 추가 · 삭제(우리 DB) | 1(Graph 읽기 · 쓰기) · 2(반복) |
| 참석자 · 스케줄러 · Teams 모임 · 바쁨 표시 · 비공개 · 범주 · 공유 · 인쇄 | 없음 | 뺌(참석자는 초대 메일이 나가므로 D48과 함께 다시 결정) |

### 2.4 To Do [확인]

- Outlook: 오늘 할 일 · 중요 · 계획된 일정 · 나에게 할당됨 · 플래그가 지정된 전자 메일 · 작업 · 새 목록, 그리드 · 목록 보기, 정렬 · 그룹, 작업마다 기한 · 알림 · 반복.
- 우리: 메일에서 뽑은 업무만, 직접 추가 없음. 상태는 미처리 · 나중에 · 완료 · 제외.
- [판단] 단계 2: 직접 할 일 추가 + Graph To Do 목록 읽기 · 쓰기. 메일에서 뽑은 업무를 To Do로 내보낼지는 따로 결정.

### 2.5 사람 · Copilot · 앱 추가

- 사람 [확인]: 연락처 · 즐겨찾기 · 연락처 목록 · 범주 · vCard · 가져오기 · 내보내기. 우리는 에이전트 기억(사람)만 있다. [판단] 단계 3 — 받는 사람 자동 완성에 필요한 만큼만.
- Copilot: 우리 캐치봇과 같은 자리. 요약 외 Copilot 기능(초안 · 코칭)은 공식 문서를 읽지 못했다 [불확실].
- 앱 추가 [확인]: Outlook 추가 기능 스토어. 이번 결정으로 우리 앱이 Outlook을 대체하므로 추가 기능 길은 쓰지 않는다.

### 2.6 우리만 하는 것 (Outlook에 없음)

업무 자동 추출 · 분류, 대시보드, 누락 방지 리마인더, 응답 대기, 음성 · 글 지시 에이전트(T01~T14), 근거 형광펜, 사내 모델(엑사원). 대체하더라도 첫 화면은 대시보드다.

### 2.7 단축키

- 있음(FE-5d): `Ctrl+R` 회신 · `Ctrl+Q` / `Ctrl+U` 읽음 · 안 읽음 · `Ctrl+.` / `Ctrl+,` 다음 · 이전 · `Insert` 고정 · `Delete` 업무 제외 · `?` 도움말.
- 더할 것 [확인, 새 Outlook 단축키 문서]: `Ctrl+N` 새 메일 · `Ctrl+Shift+R` 전체 회신 · `Ctrl+F` 전달 · `Ctrl+Enter` 보내기 · `Shift+Delete` 영구 삭제 · `Ctrl+1~4` 메일 · 일정 · 캐치봇 · 사람 · 일정 보기 `Ctrl+Alt+1~4` · `Alt+Shift+Y` 오늘.
- 주의: 일정 보기 전환이 새 Outlook 문서는 `Ctrl+Alt+1~4`, 웹 Outlook 문서는 `Shift+Alt+1~4`로 다르다. 새 Outlook을 따른다 [판단]. 우리 `Delete`는 '업무 제외'라 Outlook의 '메일 삭제'와 뜻이 다르다 — 폴더가 생기면 다시 정한다.

## 3. Graph로 가져오는 방법

| 기능 | Graph v1.0 | 권한(위임) | 판정 |
|---|---|---|---|
| 폴더 목록 | `GET /me/mailFolders` | Mail.Read | [확인] |
| 메일 동기화 | `GET /me/mailFolders/{id}/messages/delta` — 이동 · 읽음 변경도 델타로 옴, `$search` 불가 | Mail.Read | [확인] |
| 본문 · 첨부 보기 | `GET /me/messages/{id}`, `/attachments` | Mail.Read | [확인] |
| 새 메일 보내기 | `POST /me/sendMail` | Mail.Send | [확인] |
| 회신 · 전체 회신 · 전달 | `POST /me/messages/{id}/reply` · `/replyAll` · `/forward` | Mail.Send | [확인] |
| 초안 | `POST /me/messages`(만들기) → `POST /me/messages/{id}/send` | Mail.ReadWrite · Mail.Send | [확인] |
| 이동 · 보관 | `POST /me/messages/{id}/move` — **이동하면 메시지 id가 바뀐다** | Mail.ReadWrite | [확인] |
| 읽음 · 플래그 · 범주 | `PATCH /me/messages/{id}` (isRead · flag · categories) | Mail.ReadWrite | [확인] |
| 삭제 | `DELETE /me/messages/{id}` | Mail.ReadWrite | [확인] |
| 첨부 올리기 | 3MB 미만 `POST .../attachments`, 3~150MB `createUploadSession` | Mail.ReadWrite | [확인] |
| 검색 | `GET /me/messages?$search="..."` — 최대 1,000건 | Mail.Read | [확인] (`$filter` 결합 제한은 [불확실]) |
| 예약 전송 | 공식 Graph 문서에서 방법을 찾지 못함 | — | [불확실] |
| 일정 보기 · 만들기 | `GET /me/calendarView?startDateTime&endDateTime`, `POST /me/events`, 반복(daily · weekly · monthly · yearly) | Calendars.ReadWrite | [확인] |
| 빈 시간 찾기 | `POST /me/findMeetingTimes` — **개인 계정 미지원** | Calendars.Read.Shared | [확인] |
| To Do | `GET /me/todo/lists`, `/me/todo/lists/{id}/tasks` | Tasks.ReadWrite | [확인] |
| 연락처 | `GET` · `POST /me/contacts` | Contacts.ReadWrite | [확인] |
| 새 메일 알림 | 구독(webhook) 최대 10,080분(7일 미만) | — | [확인] |
| 호출 한도 | Outlook: 앱 + 사서함당 10분 10,000건, 동시 4건 | — | [확인](요약본 기준, 원문 대조 필요) |

- 위 권한 다섯 개(Mail.ReadWrite · Mail.Send · Calendars.ReadWrite · Tasks.ReadWrite · Contacts.ReadWrite)는 모두 **개인 Microsoft 계정에서 쓸 수 있다** [확인].
- 회사 · 학교 계정은 관리자가 사용자 동의를 끌 수 있다 [확인]. 그러면 관리자 동의가 있어야 한다 [판단]. 학교 계정에서 우리 앱 동의가 되는지는 **확인 불가** — 개인 Outlook.com 테스트 계정으로 먼저 붙인다(`research_20261022.md` 3절 권장과 같음).
- [판단] 이동하면 id가 바뀌므로 우리 DB의 메일 키는 Graph id를 그대로 쓰지 않는다. 변경되지 않는 id(요청 머리 `Prefer: IdType="ImmutableId"`)를 쓰는 방법이 있다고 알려져 있으나 이번에 공식 문서를 읽지 못했다 [불확실] — BE-7 시작 때 먼저 확인한다.
- [판단] 예약 전송 · 보내기 취소는 Graph에 기대지 않고 우리 스케줄러(APScheduler)가 들고 있다가 그 시각에 보낸다. 서버가 꺼져 있으면 늦게 보내지는 한계가 있다.

## 4. 완주 가능성

남은 일정: 11/20 초안 · 11/21 리뷰 · 11/27 제출 · 11/28 IR Day(`plan.md` PL-13). 오늘(11-19) 기준 일할 날은 약 7일이다.

- **Outlook 전체 대체는 11/27까지 완주할 수 없다** [판단]. 2절의 '단계 1 · 2'만 해도 백엔드 커넥터 · 동기화 · 쓰기 동작 · 프론트 새 화면(폴더 · 새 메일 · 서식 · 주 보기 · To Do)이 모두 새로 필요하고, BE-7은 담당이 아직 [미정]이다.
- **단계 1은 가능하다** [판단]. Graph 쪽은 공식 API가 모두 있고(3절), 우리 API 모양을 유지하면 프론트 변경은 새 메일 · 폴더 · 검색에 몰린다. 조건: 한 사람이 BE-7에 전념하고, 11/20까지 앱 등록과 테스트 계정 로그인이 된다.
- 1절처럼 사서함이 Exchange에 그대로 있으므로, 못 만든 기능은 Outlook에서 열어 쓰면 된다. 그래서 단계 1에서 끊어도 "대체"의 핵심(매일 하는 일은 우리 앱에서 끝남)은 시연할 수 있다.

위험:

| 위험 | 대응 |
|---|---|
| 학교 · 회사 계정 동의 막힘 | 개인 Outlook.com 테스트 계정으로 시연 |
| 시연 현장 네트워크 · 로그인 실패 | `MAIL_SOURCE=dummy` 미리 분류한 DB로 시연(멘토 의견 · R1 그대로) |
| 이동 시 id 변경으로 업무 · 리마인더 연결 끊김 | 3절 변경되지 않는 id 확인을 BE-7 첫 작업으로 |
| 토큰 보관 | BE-6 토큰 암호화를 BE-7과 함께 |
| 호출 한도(동시 4건) | 동기화는 델타로, 한 사서함에 요청 몰지 않기 |

## 5. 순서

| 단계 | 기간 | 내용 | 끝났다는 기준 |
|---|---|---|---|
| 0 | 11/20 | Entra 앱 등록(사용자가 직접) · 로그인 대상 `consumers` · 리디렉션 주소, backend MSAL 로그인 · 토큰 암호화 저장, egress 허용 목록에 Graph · 로그인 주소 | 테스트 계정으로 로그인 후 `GET /me` 성공 |
| 1a | 11/21~22 | 받은 · 보낸 편지함 델타 동기화 → 지금 Mail 저장 경로 + 분류 파이프라인, 본문 그때그때 가져오기(`mail/body.py`), 폴더 목록 | 실제 메일이 대시보드에 업무로 뜸 |
| 1b | 11/23~24 | 쓰기 동작: 회신 · 전체 회신 · 전달 · 새 메일 · 참조 · 숨은 참조 · 초안 · 작은 첨부, 읽음 · 고정 · 이동 · 보관 · 삭제를 Graph에 씀, `SENDABLE`에 outlook_graph | 우리 앱에서 보낸 메일이 Outlook 보낸 편지함에 보임 |
| 1c | 11/25~26 | 검색, 일정 calendarView 읽기 + 이벤트 만들기 · 지우기(참석자 없이), 단축키 추가 | Outlook 일정이 우리 캘린더에 보임 |
| 2 | 11/28 이후 | 서식 · 서명 · 예약 전송 · 중요도 · 범주 · 주 보기 · 반복 · To Do · 큰 첨부 | — |
| 3 | 그 뒤 | 연락처 · 새 메일 알림 구독 | — |

11/27 제출은 단계 1까지를 목표로 하고, 1c가 밀리면 일정은 읽기만 넣는다.

진행(11-19): 백엔드 단계 0 · 1a · 1b와 1c 일정 읽기를 구현했다(`docs/30_backend/plan.md` BE-7). Graph는 흉내 서버로만 시험했다 — Entra 앱 등록 뒤 실제 계정으로 확인한다. 남음: Outlook 일정 쓰기 · 검색 · 첨부 · 서명, 화면(FE) 쪽 새 메일 · 전체 답장 · 전달 · 메일함 · 계정 연결.
진행(11-19 저녁): 실제 계정(개인)으로 로그인 · 동기화 · 새 메일 보내기 확인. 화면 메일함 · 계정 연결(#251) · 새 메일 · 전체 답장 · 전달 · 참조(FE-18 #254), 1c 일정 쓰기 · 검색(받아 둔 메일 안)을 넣었다. 남음: 작은 첨부, Graph $search(오래된 메일), 단계 2(서명 · 예약 전송).
진행(11-19 밤, PR #256): 작은 첨부 · 받은 첨부 · Outlook 사서함 검색 · 서명(우리 설정) · 예약 보내기(우리 스케줄러, [판단] 그대로) · 변경 알림(GRAPH_NOTIFY_URL, 배포 뒤 켬)을 넣었다. 실제 계정 확인: 일정 쓰기 · 검색 · 예약 + 첨부. [확인] Graph `$search` 결과는 `Prefer: IdType="ImmutableId"`를 따르지 않고 보통 id(140자)를 준다 — 우리 메일과는 대화 id + 제목으로 맞춘다.

## 6. 바꿀 문서

- `README.md` 2절 '만들지 않는 것'에서 "메일 앱 대체 · 외부 캘린더 쓰기"를 뺀다. 캘린더 줄 "Outlook 캘린더에는 쓰지 않음"을 고친다.
- `docs/00_common/decisions.md` 캘린더 결정(Outlook 캘린더 11/21까지 쓰지 않음)을 이 결정으로 바꾼다고 적는다.
- `docs/20_frontend/decisions.md` UX-D5(서식 막대 뺌) · `research_outlook_20261107.md` 2절(참조 · 숨은 참조 · 예약 P1)을 2절 단계로 고친다.
- `docs/30_backend/plan.md` BE-7 범위를 3절 표로 넓히고 담당을 정한다.
- `docs/10_planning/refs/PRD.md` 계정 연결 · 만들지 않는 것.

## 출처

- Outlook 웹 화면 직접 확인(11-19): 메일 · 메일 쓰기 리본 5개 탭 · 일정 · 새 이벤트 · To Do · 사람 · 앱 더보기 · 앱 스토어
- 새 Outlook 시작하기: https://support.microsoft.com/en-us/office/getting-started-with-the-new-outlook-for-windows-656bb8d9-5a60-49b2-a98b-ba7822bc7627
- Outlook 단축키: https://support.microsoft.com/en-us/office/keyboard-shortcuts-for-outlook-3cdeb221-7ae5-4c1d-8c1d-9e63216c1efd
- Graph 메일: https://learn.microsoft.com/en-us/graph/api/user-list-mailfolders · https://learn.microsoft.com/en-us/graph/api/message-delta · https://learn.microsoft.com/en-us/graph/api/user-sendmail · https://learn.microsoft.com/en-us/graph/api/message-reply · https://learn.microsoft.com/en-us/graph/api/message-replyall · https://learn.microsoft.com/en-us/graph/api/message-forward · https://learn.microsoft.com/en-us/graph/api/user-post-messages · https://learn.microsoft.com/en-us/graph/api/message-send · https://learn.microsoft.com/en-us/graph/api/message-move · https://learn.microsoft.com/en-us/graph/api/message-update · https://learn.microsoft.com/en-us/graph/api/message-delete · https://learn.microsoft.com/en-us/graph/outlook-large-attachments · https://learn.microsoft.com/en-us/graph/search-query-parameter
- Graph 일정 · 할 일 · 연락처: https://learn.microsoft.com/en-us/graph/api/user-list-calendarview · https://learn.microsoft.com/en-us/graph/api/user-post-events · https://learn.microsoft.com/en-us/graph/api/resources/recurrencepattern · https://learn.microsoft.com/en-us/graph/api/user-findmeetingtimes · https://learn.microsoft.com/en-us/graph/api/resources/todo-overview · https://learn.microsoft.com/en-us/graph/api/user-post-contacts
- 권한 · 구독 · 한도 · 동의: https://learn.microsoft.com/en-us/graph/permissions-reference · https://learn.microsoft.com/en-us/graph/api/resources/subscription · https://learn.microsoft.com/en-us/graph/throttling-limits · https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/configure-user-consent
