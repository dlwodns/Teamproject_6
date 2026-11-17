"""설정 GET · PATCH /api/settings (FE 제안 계약 contract.ts Settings) · 연락처 목록 GET /api/contacts.

- 알림 시각: 하루 요약 remind_time · 회고 evening_time. 리마인더 엔진은 매 틱 DB에서 정책을 다시 읽으므로(app/reminders/policy.load)
  바꾼 값은 다음 틱부터 반영된다. 근무 시간 · 요일 · 조용한 시간 · 부재 중도 같은 정책이다(명세 reminders.md 4.2절).
- 메일 본문 읽기(read_body): 끄면 새로 분류하는 메일은 제목 · 발신자로만 판단한다(app/jobs/classify.py, 구조도 10절).
- 답장 템플릿(templates, BE-16 일반 템플릿): 보낸 목록으로 통째로 바꾼다(1~20개). 저장한 적이 없으면 기본 4개를 보인다.
  자리표시자 {수신자명} · {발신자명} · {내용}. 본문 틀(pattern)은 인사 · 맺음 · 서명으로 서버가 만든다(FE compose.ts renderReply가 쓴다).
"""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.clock import as_kst, to_kst_naive
from app.core.db import get_db
from app.core.user import current_user_id
from app.models import Contact, Template, UserSettings

router = APIRouter(prefix="/api")

HHMM = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]
DAYS = Annotated[str, Field(pattern=r"^[1-7](-[1-7])?(,[1-7](-[1-7])?)*$", max_length=20)]  # "1-5" · "1,3,5" (policy.parse_days)
MAX_TEMPLATES = 20


def pattern(greeting: str, closing: str, signature: str) -> str:
    """mock settings.v1.json과 같은 틀: 인사 → 빈 줄 → {내용} → 빈 줄 → 맺음 → 줄바꿈 → 서명. 빈 칸은 뺀다."""
    tail = "\n".join(x for x in (closing, signature) if x)
    return "\n\n".join(x for x in (greeting, "{내용}", tail) if x)


class TemplateView(BaseModel):
    key: str
    name: str
    greeting: str
    closing: str
    signature: str
    pattern: str


class TemplateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    name: str = Field(min_length=1, max_length=100)
    greeting: str = Field("", max_length=2000)
    closing: str = Field("", max_length=2000)
    signature: str = Field("", max_length=500)
    pattern: str | None = None  # 보내도 무시한다(서버가 만든다)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("이름이 비어 있다")
        return v.strip()

    @field_validator("greeting", "closing", "signature")
    @classmethod
    def _no_body_slot(cls, v: str) -> str:
        if "{내용}" in v:  # 본문 자리는 틀이 정한다. 칸 안에 있으면 FE renderReply가 본문 위치를 잘못 자른다
            raise ValueError("{내용}은 넣을 수 없다")
        return v


_HELLO = "{수신자명}님, 안녕하세요. {발신자명}입니다."
DEFAULT_TEMPLATES = [  # 기본 4개(FE mock settings.v1.json과 같은 글)
    TemplateIn(key="basic", name="기본 회신", greeting=_HELLO, closing="감사합니다.", signature="{발신자명} 드림"),
    TemplateIn(key="material", name="자료 송부", greeting=f"{_HELLO}\n요청하신 자료를 첨부해 보내드립니다.", closing="확인 부탁드립니다.",
               signature="{발신자명} 드림"),
    TemplateIn(key="schedule", name="일정 회신", greeting=f"{_HELLO}\n문의하신 일정 관련 회신드립니다.",
               closing="일정이 바뀌면 다시 말씀드리겠습니다.", signature="{발신자명} 드림"),
    TemplateIn(key="ack", name="확인했습니다", greeting=f"{_HELLO}\n메일 잘 받았고 내용 확인했습니다.", closing="감사합니다.",
               signature="{발신자명} 드림"),
]


class SettingsView(BaseModel):
    remind_time: str
    evening_time: str
    awaiting_reply_days: int
    quiet_start: str | None
    quiet_end: str | None
    reduce_motion: bool
    stt_mode: str
    reply_confirm_skip_until: datetime | None
    read_body: bool
    work_start: str
    work_end: str
    work_days: str
    away_until: datetime | None
    templates: list[TemplateView]


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    remind_time: HHMM | None = None
    evening_time: HHMM | None = None
    awaiting_reply_days: int | None = Field(None, ge=1, le=30)
    quiet_start: HHMM | None = None
    quiet_end: HHMM | None = None
    reduce_motion: StrictBool | None = None
    stt_mode: str | None = Field(None, max_length=10)
    reply_confirm_skip_until: datetime | None = None  # '오늘 다시 보지 않음'(D48). null이면 해제
    read_body: StrictBool | None = None
    work_start: HHMM | None = None
    work_end: HHMM | None = None
    work_days: DAYS | None = None
    away_until: datetime | None = None  # 부재 중(~까지). null이면 해제
    templates: list[TemplateIn] | None = Field(None, min_length=1, max_length=MAX_TEMPLATES)

    @field_validator("work_days")
    @classmethod
    def _ascending(cls, v: str | None):
        for part in (v or "").split(","):
            a, _, b = part.partition("-")
            if b and int(a) > int(b):  # "7-6"은 policy.parse_days가 말없이 평일로 바꾼다
                raise ValueError("요일 범위는 앞이 작아야 한다")
        return v

    @field_validator("templates")
    @classmethod
    def _unique(cls, v: list[TemplateIn] | None):
        if v is not None and len({t.key for t in v}) != len(v):
            raise ValueError("템플릿 key가 겹친다")
        return v


NOT_NULL = {"remind_time", "evening_time", "awaiting_reply_days", "reduce_motion", "stt_mode", "read_body", "work_start",
            "work_end", "work_days", "templates"}


def _row(db: Session, user_id: int) -> UserSettings:
    s = db.get(UserSettings, user_id)
    if s is None:
        s = UserSettings(user_id=user_id)
        db.add(s)
        db.flush()  # 기본값을 채운다
    return s


def _templates(db: Session, user_id: int) -> list[TemplateView]:
    rows = db.scalars(select(Template).where(Template.user_id == user_id, Template.kind == "reply").order_by(Template.id)).all()
    if not rows:  # 저장한 적이 없으면 기본(저장하지 않는다)
        return [TemplateView(**t.model_dump(exclude={"pattern"}), pattern=pattern(t.greeting, t.closing, t.signature))
                for t in DEFAULT_TEMPLATES]
    return [TemplateView(key=t.key or f"t{t.id}", name=t.name, greeting=t.greeting or "", closing=t.closing or "",
                         signature=t.signature or "",
                         # 칸을 나누기 전의 행은 본문(body)을 틀로 쓴다
                         pattern=pattern(t.greeting or "", t.closing or "", t.signature or "")
                         if (t.greeting or t.closing or t.signature) else (t.body or "{내용}"))
            for t in rows]


def _view(db: Session, s: UserSettings) -> SettingsView:
    return SettingsView(remind_time=s.remind_time, evening_time=s.evening_time, awaiting_reply_days=s.awaiting_reply_days,
                        quiet_start=s.quiet_start, quiet_end=s.quiet_end, reduce_motion=s.reduce_motion,
                        stt_mode=s.stt_mode, reply_confirm_skip_until=as_kst(s.reply_confirm_skip_until),
                        read_body=s.read_body, work_start=s.work_start, work_end=s.work_end, work_days=s.work_days,
                        away_until=as_kst(s.away_until), templates=_templates(db, s.user_id))


@router.get("/settings", response_model=SettingsView)
def get_settings(user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> SettingsView:
    s = _row(db, user_id)
    db.commit()
    return _view(db, s)


@router.patch("/settings", response_model=SettingsView)
def patch_settings(body: SettingsPatch, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> SettingsView:
    """보낸 칸만 바꾼다. null은 조용한 시간(quiet_*) · 오늘 다시 보지 않음 · 부재 중만 '없음'(해제)으로 받는다. 다른 칸의 null은 무시한다."""
    s = _row(db, user_id)
    fields = body.model_dump(exclude_unset=True, exclude={"templates"})
    for k, v in fields.items():
        if v is None and k in NOT_NULL:
            continue
        setattr(s, k, to_kst_naive(v) if isinstance(v, datetime) else v)  # 시각은 naive KST로 저장(D47)
    # 보낸 칸만 검사한다 — 예전에 반쪽만 저장된 행 때문에 상관없는 PATCH까지 막히지 않게(policy.load는 반쪽을 '없음'으로 본다)
    if {"work_start", "work_end"} & fields.keys() and s.work_start >= s.work_end:  # 'HH:MM' 글자 비교 = 시각 비교
        db.rollback()
        raise HTTPException(422, "근무 시작은 근무 끝보다 이르다")
    if {"quiet_start", "quiet_end"} & fields.keys() and (s.quiet_start is None) != (s.quiet_end is None):
        db.rollback()
        raise HTTPException(422, "조용한 시간은 시작 · 끝을 함께 정하거나 함께 비운다")
    if body.templates is not None:
        db.execute(delete(Template).where(Template.user_id == user_id, Template.kind == "reply"))
        for t in body.templates:
            db.add(Template(user_id=user_id, kind="reply", key=t.key, name=t.name, greeting=t.greeting, closing=t.closing,
                            signature=t.signature, body=pattern(t.greeting, t.closing, t.signature)))
    db.commit()
    return _view(db, s)


class ContactView(BaseModel):
    id: int
    email: str
    name: str | None
    position: str | None
    is_superior: bool
    is_favorite: bool


@router.get("/contacts", response_model=list[ContactView])
def list_contacts(user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> list[ContactView]:
    """설정 '사람' 칸: 모든 연락처. 상급자 · 즐겨찾기 표시는 PATCH /api/agent/memory/people/{id}(되돌리기 기록이 남는다)."""
    rows = db.scalars(select(Contact).where(Contact.user_id == user_id)
                      .order_by(Contact.is_superior.desc(), Contact.is_favorite.desc(), Contact.name.is_(None), Contact.name, Contact.email))  # 이름 없는 사람은 뒤로
    return [ContactView(id=c.id, email=c.email, name=c.name, position=c.position, is_superior=c.is_superior,
                        is_favorite=c.is_favorite) for c in rows]
