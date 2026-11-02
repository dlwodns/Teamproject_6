"""backend ↔ ai `POST /summarize` · `POST /draft` 형식 (구조도 v3.1 8절, D42). 결과는 표시용이며 발송하지 않는다."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SummaryItem(BaseModel):
    task_id: str
    text: str
    sender: str | None = None  # 가린 이름 또는 '김 팀장'처럼 직급 표기
    category: str | None = None
    due_at: datetime | None = None
    priority: Literal["P1", "P2", "P3"] = "P3"
    status: Literal["pending", "snoozed"] = "pending"


class MailInput(BaseModel):
    subject: str = ""
    body: str = ""  # 개인정보를 가린 본문
    sender: str | None = None


class SummarizeRequest(BaseModel):
    mode: Literal["today", "mail"]
    now: datetime
    items: list[SummaryItem] = []  # mode=today
    awaiting_reply_count: int = 0  # 3일 이상 무응답 발신 메일 수 (T06)
    mail: MailInput | None = None  # mode=mail (영문 메일은 한국어로 요약)
    use_model: bool = True  # False면 코드 요약만 (응답 즉시)


class SummarizeResponse(BaseModel):
    text: str
    source: Literal["code", "exaone"]
    prompt_version: str | None = None
    fallback: str | None = None


class DraftRequest(BaseModel):
    kind: Literal["reply", "new"]  # reply: 회신 초안(T07), new: 새 메일 초안(T12)
    mail: MailInput | None = None  # reply일 때 원 메일
    recipient: str | None = None  # new일 때 받는 사람 표기
    topic: str | None = None
    tone: Literal["polite", "short"] = "polite"
    signer: str | None = None  # 서명에 쓸 내 이름 표기


class DraftResponse(BaseModel):
    subject: str
    body: str
    source: Literal["template", "exaone"]
    prompt_version: str | None = None
    fallback: str | None = None
