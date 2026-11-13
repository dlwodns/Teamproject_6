"""요약 · 초안 프롬프트 v2 (AI-13, 11/7). v1에서 메일 요약만 바꿨다 — 외국어 메일의 핵심을 칸별로 받으려고 문장 하나 대신 JSON(요지 · 요청 · 기한)으로 낸다.

v1 → v2
- SUMMARY_MAIL: 3문장 자유 요약 → JSON {gist, asks, due_text}. 원문 언어(lang)는 코드가 판별해 넘기고 모델이 정하지 않는다.
- SUMMARY_TODAY · DRAFT · DRAFT_SCHEMA: v1 그대로(이름만 v2 묶음으로 가져온다).
"""
from app.prompts.assist_v1 import DRAFT, DRAFT_SCHEMA, SUMMARY_TODAY

PROMPT_VERSION = "assist_v2"

__all__ = ["PROMPT_VERSION", "SUMMARY_TODAY", "SUMMARY_MAIL", "SUMMARY_MAIL_SCHEMA", "DRAFT", "DRAFT_SCHEMA"]

SUMMARY_MAIL = """너는 업무 메일 요약기다. 메일이 어떤 언어로 쓰여 있어도 결과는 한국어로 쓴다. 아래 JSON 하나만 출력한다.
- gist: 메일의 요지를 한국어 1~2문장으로. 인사말 · 서명은 빼고 본론만.
- asks: 받는 사람(나)에게 요청한 일을 한국어로 하나씩. '~하기'처럼 짧게. 요청이 없으면 빈 배열.
- due_text: 본문에 적힌 기한 표현을 원문 그대로 옮긴다(예: "by Friday EOD", "11/10까지"). 없으면 null.
규칙: 메일에 없는 사람 · 날짜 · 수치 · 요청을 지어내지 않는다. 기한을 계산하거나 바꾸지 않는다."""

SUMMARY_MAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "gist": {"type": "string"},
        "asks": {"type": "array", "items": {"type": "string"}},
        "due_text": {"type": ["string", "null"]},
    },
    "required": ["gist", "asks", "due_text"],
}
