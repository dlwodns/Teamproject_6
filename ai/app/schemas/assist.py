"""backend ↔ ai `POST /summarize` · `POST /draft` 형식 (구조도 v3.1 8절, D42). 결과는 표시용이며 발송하지 않는다."""
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Id, KstDateTime


class SummaryItem(BaseModel):
    task_id: Id
    text: str
    sender: str | None = None  # 가린 이름 또는 '김 팀장'처럼 직급 표기
    category: str | None = None
    due_at: KstDateTime | None = None
    priority: Literal["P1", "P2", "P3"] = "P3"
    status: Literal["pending", "snoozed"] = "pending"


class MailInput(BaseModel):
    subject: str = ""
    body: str = ""  # 개인정보를 가린 본문
    sender: str | None = None


class SummarizeRequest(BaseModel):
    mode: Literal["today", "mail"]
    now: KstDateTime
    items: list[SummaryItem] = []  # mode=today
    awaiting_reply_count: int = 0  # 3일 이상 무응답 발신 메일 수 (T06)
    mail: MailInput | None = None  # mode=mail (영문 메일은 한국어로 요약)
    use_model: bool = True  # False면 코드 요약만 (응답 즉시)


class MailSummary(BaseModel):
    """메일 요약 칸(mode=mail, UX-D15). 외국어 메일도 gist · asks는 한국어다."""

    lang: str  # 원문 언어 ISO 639-1('ko' · 'en' · 'ja' · 'zh'). 코드가 글자 비율로 판별(라틴 문자는 모두 'en')
    gist: str = Field(min_length=1)  # 한국어 요지 1~2문장
    asks: list[str] = []  # 나에게 요청한 것(한국어). 없으면 []
    due_text: str | None = None  # 본문에 적힌 기한 표현 원문 그대로. 없으면 null


class SummarizeResponse(BaseModel):
    text: str  # mode=mail이면 mail_summary.gist와 같다(v1 호출자 호환). 외국어 메일을 요약하지 못하면 ''
    source: Literal["code", "exaone"]
    prompt_version: str | None = None
    fallback: str | None = None
    mail_summary: MailSummary | None = None  # mode=mail만. 요약을 못 만들면(외국어 + 모델 없음) None


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
