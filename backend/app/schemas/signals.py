"""ai `POST /signals` 응답을 backend가 쓰는 형식으로 받는다 (AI-24 · AI-D20, 명세 reminders.md 8절, BE-12).

ai 쪽 정의는 `ai/app/schemas/signals.py`가 기준이다. 바꿀 때는 양쪽을 함께 고친다.
- ID: ai는 문자열로 돌려준다 → 정수로 바꾼다(D47 결정 2). 시각: 시간대 없는 KST(붙어 오면 KST로 바꿔 뗀다).
- 모델이 판단하지 못하면 HTTP 200에 신호 없이 fallback(quota · model_failed · bad_output · empty_body)이 온다.
"""
from typing import Literal

from app.schemas.ai import _AI, KstNaive


class SignalCommitment(_AI):
    who: Literal["me", "them"]
    text: str
    due_raw: str | None = None
    due_at: KstNaive = None
    evidence: str


class SignalDueChange(_AI):
    task_id: int
    new_due_raw: str | None = None
    new_due_at: KstNaive = None
    evidence: str


class SignalResolved(_AI):
    task_id: int
    reason: Literal["done_by_other", "cancelled", "not_needed"]
    evidence: str


class SignalsResult(_AI):
    mail_id: int | None = None
    commitments: list[SignalCommitment] = []
    due_changes: list[SignalDueChange] = []
    resolved: list[SignalResolved] = []
    asks_me_question: bool = False
    source: Literal["exaone", "none"] = "none"
    model: str | None = None
    prompt_version: str | None = None
    elapsed_ms: int = 0
    dropped: int = 0
    fallback: str | None = None  # null | quota | model_failed | bad_output | empty_body
    detail: str | None = None
