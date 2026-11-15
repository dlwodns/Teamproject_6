"""캘린더 API 응답 (BE-15 · D50). 시각은 +09:00(D47)."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class CalendarItem(BaseModel):
    kind: Literal["due", "snoozed", "meeting", "event"]  # 기한 · 다시 알림 · 회의(일정참석 업무) · 넣은 일정
    title: str
    start: datetime
    end: datetime | None  # meeting · event만. due · snoozed는 한 시점
    time_stated: bool  # False면 날짜만 보여 준다(메일에 시각이 없어 기본 시각으로 채운 기한)
    mail_id: int | None
    task_id: int | None
    event_id: int | None  # event만. [빼기]에 쓴다
    subject: str | None  # 메일 제목(메일로 넘어가기)
    auto: bool = False  # 자동 등록한 일정(지금은 늘 False)


class CalendarRange(BaseModel):
    start: date
    end: date
    as_of: datetime
    items: list[CalendarItem]


class EventCreate(BaseModel):
    start: datetime
    end: datetime | None = None  # 없으면 시작 + 1시간
    title: str | None = Field(default=None, max_length=200)  # 없으면 메일 제목, 그것도 없으면 '일정'
    mail_id: int | None = None
    task_id: int | None = None
    via: str | None = Field(default=None, max_length=50)  # 누른 화면(suggestion:meeting 등, D50)


class EventResult(BaseModel):
    action_id: int  # 되돌리기: POST /api/actions/{action_id}/undo
    item: CalendarItem
