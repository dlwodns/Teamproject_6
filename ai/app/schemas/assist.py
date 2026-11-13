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
    is_superior: bool = False  # 보낸 사람이 상급자(contacts.is_superior). 오늘 요약 첫 문장에서 이름을 드는 기준(AI-D21)
    is_event: bool | None = None  # 시각이 정해진 일정(업무 유형 일정참석). None이면 '참석' 낱말로 본다('참석자'는 아님)


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

    # 원문 언어. 코드가 글자 비율로 판별한다. 'other'는 영어가 아닌 라틴 문자 언어(불어 · 독일어 · 스페인어 등, 화면은 '기타 외국어')
    lang: Literal["ko", "en", "ja", "zh", "other"]
    gist: str = Field(min_length=1)  # 한국어 요지 1~2문장
    asks: list[str] = []  # 나에게 요청한 것(한국어). 없으면 []
    due_text: str | None = None  # 본문에 적힌 기한 표현 원문 그대로. 없으면 null


class TodayCounts(BaseModel):
    """오늘 요약의 숫자 줄(mode=today). 코드가 센 값이라 화면은 이 값을 쓴다 — 문장 속 숫자와 어긋나면 이쪽이 맞다."""

    pending: int  # 미처리(나중에 제외)
    due_today: int  # 오늘까지 기한(기한 지남 포함)
    overdue: int
    awaiting_reply: int


class SummarizeResponse(BaseModel):
    text: str  # mode=mail이면 mail_summary.gist와 같다(v1 호출자 호환). 외국어 메일을 요약하지 못하면 ''
    source: Literal["code", "exaone"]
    prompt_version: str | None = None
    fallback: str | None = None
    mail_summary: MailSummary | None = None  # mode=mail만. 요약을 못 만들면(외국어 + 모델 없음) None
    counts: TodayCounts | None = None  # mode=today만


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
