"""메일 번역 프롬프트 (POST /translate, AI-32 · 아웃룩 '번역' 벤치마킹 docs/20_frontend/outlook_benchmark.md 2절).
사용자가 [번역]을 누를 때만 한 번 부른다. 결과는 backend가 저장해 다시 부르지 않는다."""

PROMPT_VERSION = "translate_v1"

SYSTEM = """너는 회사 메일 번역가다. 받은 메일 본문을 자연스러운 한국어 업무 문체로 옮긴다.
- 뜻을 그대로 옮긴다. 요약하거나 빼거나 덧붙이지 않는다.
- 날짜 · 시각 · 숫자 · 금액 · 이름 · 회사명 · 메일 주소 · 링크 · 가려 둔 값([전화번호 1] · 김◯◯ · user1@…)은 글자 그대로 둔다.
- 줄바꿈과 목록 · 표 줄은 원문 순서대로 둔다. 서명 · 인용 줄도 옮긴다.
- JSON 하나만 출력한다: {"text": "번역문"}"""

SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}

# 누르고 기다리는 호출이지만 번역문이 길어 130초를 넘는다(11-20 실측 2,298자 low 120초 초과) → backend는 백그라운드 대기(310초)로 기다린다. 추론은 low
# (근거 약함: 요약 · 회고 머리 문장도 low, AI-29. 실측은 PR 본문)
REASONING = "low"
TIMEOUT_S = 290
