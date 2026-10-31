# backend · API 서버 + SQLite

> 프레임워크: 현재 FastAPI. Spring Boot 전환은 팀 논의 중이다 `[미정]`. 어느 쪽이든 AI는 `ai/` 서비스를 HTTP로 부른다(D34).

| 폴더 | 내용 |
|---|---|
| `app/api/` | 라우터: tasks · mails · accounts · settings · agent · voice(→ ai 중계) |
| `app/core/` | 설정(.env 읽기) · DB 연결 · 토큰 암호화 |
| `app/models/` | DB 테이블 (users · accounts · mails · tasks · settings · notification_logs) |
| `app/schemas/` | 요청 · 응답 형식 |
| `app/mail/connectors/` | 메일 가져오기: `dummy`(개발 · 평가) · `outlook_graph`(OAuth 권장) · `imap` |
| `app/ai_client/` | `ai/` 서비스 호출(`/classify` · `/agent/plan` · `/stt`). 주소는 `AI_SERVICE_URL` |
| `app/agent/` | 에이전트 실행: ai가 돌려준 계획 → 사용자 확인 → `tools/`(허용된 기능만) 실행 → 실행 기록 |
| `app/privacy/` | ai에 보내기 전 개인정보 가리기 · 본문 읽기 동의 · 보관 기간 · 로그에 본문 남기지 않기 |
| `app/notify/` | 알림. 1단계 제외(D16), 자리만 둔다 |
| `app/jobs/` | 주기 작업(동기화 · 분류 요청 · 알림), APScheduler 1프로세스 |
| `tests/` | API 테스트 (architecture 5절 10건 → v3에서 갱신) |

## 규칙
- Claude(anthropic) 패키지를 넣지 않는다.
- 엑사원을 직접 부르지 않는다. 분류 · 의도 파악 · STT는 `ai_client/`로만 요청한다.
- 분류 요청은 백그라운드 작업으로 보낸다(메일 1통 약 25초). ai가 응답하지 않아도 메일 동기화와 화면은 동작해야 한다.
- 에이전트는 `agent/tools/`에 등록한 기능만 실행한다. 삭제 · 메일 발송은 반드시 사용자 확인을 받는다.
