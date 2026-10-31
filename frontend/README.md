# frontend · React + Vite + TS

| 폴더 | 내용 |
|---|---|
| `src/app/` | 라우터 · 공통 레이아웃(상단 바: 대시보드 \| 메일 \| 설정, 에이전트 버튼) · 전역 상태 |
| `src/pages/dashboard/` | 요약 줄 + 세로 2열 업무 칸 (wireframe 12절, D20) |
| `src/pages/mail/` | 메일 목록 · 원본 메일 패널 |
| `src/pages/settings/` | 내 정보 · 메일 연동 · 알림 · 템플릿 · 화면 · AI 에이전트 |
| `src/features/tasks/` | 업무 카드 · 완료 · 되돌리기 · 일괄 처리 · 회신 후 완료 확인 팝업(D23) |
| `src/features/mail/` | 메일 표시 · 답장 작성 |
| `src/features/settings/` | 설정 항목별 폼, 개인정보 동의 화면 |
| `src/features/agent/` | 에이전트 패널(360px) · 실행 전 확인 카드 |
| `src/features/voice/` | 음성 입력 버튼. `adapters/`에 browser(Web Speech API) · server(백엔드 STT) 두 방식 |
| `src/components/` | 공용 UI (버튼 · 칩 · 토스트 · 패널) |
| `src/api/` | 백엔드 호출 함수 (화면에서 fetch를 직접 쓰지 않는다) |
| `src/styles/` | 디자인 토큰. LG RED는 주 버튼 · 선택 메뉴에만(D21) |

- 시안 원본: `docs/20_frontend/ui_reference/final_dashboard_wireframe.html`
- 음성 · 글 지시는 모두 `features/agent`로 들어간다. 음성은 글자로 바뀐 뒤 같은 길을 탄다.
