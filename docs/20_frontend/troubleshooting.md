# 프론트엔드 트러블슈팅

> 문제 · 원인 · 해결 · 재발 방지를 쌓는다. 쓰는 법: `../00_common/templates/troubleshooting_template.md`
> 기존 항목은 `Project_Rocket6` 기록(log · decisions · exaone_bench)에서 옮겼다.

## FE-T1 · Figma 연동 호출이 월 20회로 제한됨 (2026-10-24)

- 상태: 우회 · 발견: 문규남 · 해결: 문규남 · 리뷰: [미정] · 공동: — · 근거: D20
- 증상: 대시보드 시안을 Figma로 바로 만들려 했으나 연동 호출 횟수가 부족했다.
- 원인: Figma 계정이 Starter · View 시트라 연동 호출이 월 20회로 제한된다.
- 해결: HTML 시안을 먼저 만들어 동작을 검증하고, 확정본만 Figma로 옮겼다.
- 재발 방지: 화면 검증은 HTML 시안(`ui_reference/`)에서 하고, Figma는 확정본 보관용으로 쓴다.
