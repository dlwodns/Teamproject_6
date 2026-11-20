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
    # False면 메일에 시각이 없어 due_at 시각은 기본값(18:00 등)이다 → 모델에 날짜만 넘긴다(지어낸 시각 막기, AI-29 리뷰)
    due_time_stated: bool | None = None


class MailInput(BaseModel):
    subject: str = ""
    body: str = ""  # 개인정보를 가린 본문
    sender: str | None = None


class BriefingItemIn(BaseModel):
    """회고 묶음의 한 줄(mode=evening · weekly, io_spec 3.5절). backend 브리핑 묶음(reminders/briefings.py) 그대로."""

    task_id: Id | None = None
    text: str
    sender: str | None = None
    is_superior: bool = False
    is_event: bool | None = None
    due_at: KstDateTime | None = None
    due_time_stated: bool | None = None  # SummaryItem과 같다
    done_at: KstDateTime | None = None


class BriefingSectionIn(BaseModel):
    # evening: done_today · remaining · due_tomorrow / weekly: done_week · carry_over · waiting · due_next_week.
    # 모르는 id는 무시한다(목록 · 건수는 backend가 화면에 그대로 보인다)
    id: str
    label: str = ""
    items: list[BriefingItemIn] = []


class SummarizeRequest(BaseModel):
    mode: Literal["today", "evening", "weekly", "mail"]
    now: KstDateTime
    items: list[SummaryItem] = []  # mode=today
    sections: list[BriefingSectionIn] = []  # mode=evening · weekly (AI-29)
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
    """오늘 요약의 숫자 줄(mode=today). 코드가 센 값이라 문장 속 숫자와 어긋나면 이쪽이 맞다.
    화면은 기한 지남 · 오늘까지 · 응답 대기를 이 값으로 보이고, '미처리'는 대시보드(UX-D2) 값을 쓴다(아래 pending 참고)."""

    # 지금 남은 미처리 업무 수: 상태가 미처리인 것만(나중에 · 제외 빼고), 받은 날과 관계없이 전부.
    # 대시보드 1열 '미처리'(UX-D2: 미처리 + 나중에, 받은 날 기준)와 다른 값이라 화면에 '미처리'로 보이지 않는다(#61 리뷰).
    # 브리핑 검증(맞는 건수 집합)에 쓰고, 화면의 미처리 숫자는 대시보드 값 하나만 쓴다
    pending: int
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
    section_counts: dict[str, int] | None = None  # mode=evening · weekly만: {묶음 id: 건수}(코드가 셈)


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


# ---------- 답장 다듬기 (POST /polish) ----------
class TranslateRequest(BaseModel):
    """메일 번역(AI-32). 본문은 backend가 개인정보를 가린 것."""
    text: str


class TranslateResponse(BaseModel):
    text: str  # 한국어 번역문. 번역하지 않았거나 못 했으면 ''(fallback에 이유)
    lang: Literal["ko", "en", "ja", "zh", "other"]  # 원문 언어(코드가 글자로 판별)
    source: Literal["exaone", "none"]
    prompt_version: str
    fallback: str | None = None  # 40자 미만 · 이미 한국어 · 모델 호출 실패 · 번역문이 한국어가 아님
    truncated: bool = False  # 본문이 MAX_CHARS를 넘어 앞부분만 번역했다(화면이 '일부만 번역'으로 알린다)


# 화면 버튼과 1:1(app/prompts/polish_v1.py STYLES). 바꾸면 backend schemas/ai.py PolishStyle도 함께 고친다
PolishStyle = Literal["polite", "concise", "proofread", "clear"]


class PolishRequest(BaseModel):
    # 사용자가 쓴 글(개인정보를 가린 것). backend는 가리기 전 4000자로 막는다. 가리면 길어질 수 있어(a@x.kr → user1@x.kr) 여유를 둔다
    text: str = Field(min_length=1, max_length=6000)
    style: PolishStyle
    mail: MailInput | None = None  # 답장이면 원 메일(맥락으로만 읽는다)


class PolishResponse(BaseModel):
    text: str  # 다듬은 글. 모델이 실패하거나 검사에 걸리면 받은 글 그대로
    style: PolishStyle
    changed: bool  # 받은 글과 다른가
    source: Literal["exaone", "none"]  # none: 모델을 쓰지 못해 받은 글 그대로
    prompt_version: str | None = None
    fallback: str | None = None  # 받은 글 그대로 돌려준 이유
