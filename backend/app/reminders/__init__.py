"""리마인더 엔진 (BE-12, 명세 docs/10_planning/reminders.md 2 · 3 · 4 · 7절).

- types.py: 유형 · 묶음 · 우선순위 · 알림 시각 규칙 표(한 곳)
- rules.py: 지금 챙길 항목 계산. 저장된 값과 AI 신호(commitments · reminder_signals)만 읽는다. 쓰지 않는다
- policy.py: 근무 시간 · 조용한 시간 · 부재 중 · 알림 간격(1일 → 2일, 3번이면 조용히 둠)
- engine.py: 1분마다 ① 항목 계산 ② 보낼 알림 정하기 ③ 보내기 직전 재확인 ④ notifications · reminders에 쓰기
- actions.py: 항목 버튼(숨기기 · 신고 · 적용)과 T16 기한 바꾸기 · 약속 끝내기의 되돌리기
- briefings.py: 아침 브리핑 · 퇴근 회고 · 주간 회고 내용
- schema.py: 예전 SQLite 파일에 새 칸 · 제약을 넣는 작은 이전 작업(create_all 직후 자동)
이 패키지의 __init__은 아무것도 불러오지 않는다(app.models가 schema.py를 부르므로 순환을 피한다).
"""
