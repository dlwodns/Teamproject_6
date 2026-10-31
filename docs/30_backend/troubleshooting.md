# 백엔드 트러블슈팅

> 문제 · 원인 · 해결 · 재발 방지를 쌓는다. 쓰는 법: `../00_common/templates/troubleshooting_template.md`
> 기존 항목은 `Project_Rocket6` 기록(log · decisions · exaone_bench)에서 옮겼다.

## BE-T1 · Outlook.com 서버 대리 로그인이 동작하지 않음 (2026-10-22)

- 상태: 우회 · 발견: 문규남 · 해결: 문규남 · 리뷰: [미정] · 공동: — · 근거: D17 · research_20261022 3절
- 증상: 팀 선호였던 서버 대리 로그인(아이디 · 비밀번호로 서버가 접속)을 조사했다.
- 원인: Outlook.com은 2024-09-16부터 기본 인증을 막았다. 앱 비밀번호의 Outlook.com IMAP 지원은 공식 근거를 찾지 못했다 `[미확인]`.
- 해결: 조사 권장안을 OAuth(Microsoft Graph)로 바꿨다. 방식 확정은 아직이다.
- 재발 방지: 메일 서비스 인증 방식은 공식 문서로 확인한 뒤 정한다. 연동 전 팀 테스트 계정으로 먼저 시도한다.
