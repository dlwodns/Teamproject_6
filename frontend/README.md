# frontend · React + Vite + TS

> 기준 문서: PRD v3.1 Q5 · 구조도 v3.1 2절 · wireframe 12절(v3.1 변경 미반영 — 성격 칸 · 응답 대기 · 알림 센터 · 캘린더는 FE에서 반영 예정)

| 폴더 | 내용 |
|---|---|
| `src/app/` | 라우터 · 공통 레이아웃(상단 바: 대시보드 \| 메일 \| 캘린더 \| 설정, 새 알림 수, ✦ 에이전트 버튼) · 전역 상태 · PWA(서비스 워커 · 웹 푸시 구독) |
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
| `src/api/` | 백엔드 호출 함수 (화면에서 fetch를 직접 쓰지 않는다) |
| `src/styles/` | 디자인 토큰. LG RED는 주 버튼 · 선택 메뉴에만(D21) |

- 시안 원본: `docs/20_frontend/ui_reference/final_dashboard_wireframe.html`
- 음성 · 글 지시는 모두 `features/agent`로 들어간다. 음성은 글자로 바뀐 뒤 같은 길을 탄다.
- 버튼으로 바꾼 상태와 에이전트가 바꾼 상태는 같은 API · 같은 화면 갱신을 탄다. 행동 실행 직후 대시보드 숫자를 다시 불러온다.
- 웹 푸시는 HTTPS에서만 동작한다. iOS는 홈 화면에 설치했을 때만 받는다.
