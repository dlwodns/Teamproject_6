"""대시보드 원자료 응답 (BE-3). 형식은 FE 임시 계약 frontend/src/api/provisional.ts를 따른다.

집계(완료율 · 기한 · 칸)는 FE aggregate.ts가 한다. 서버는 원자료만 보낸다.
응답 시각은 +09:00이 붙은 KST다(D47).
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.actions import Status
from app.schemas.awaiting import AwaitingView

Category = Literal["회신", "요청", "검토", "공지", "기타"]  # D39 · models/mail.py CATEGORIES


class DashboardContact(BaseModel):
    email: str
    name: str | None
    position: str | None
    is_superior: bool
    is_favorite: bool


class DashboardMail(BaseModel):
    id: int
    source_id: str
    direction: Literal["received"]  # 받은 메일만. 보낸 메일은 BE-13에서 따로 제공한다
    sender: str
    subject: str
    received_at: datetime  # DB mails.sent_at(받은 메일은 수신 시각)
    category: Category | None  # 분류 전이면 null(필드를 빼지 않는다)


class DashboardTask(BaseModel):
    id: int
    mail_id: int
    text: str
    due_at: datetime | None
    due_raw: str | None  # provisional 외 추가 필드: 메일 속 기한 표현 그대로(이후 기한 라벨용)
    due_source: str
    status: Status
    seen_at: datetime | None


class DashboardResponse(BaseModel):
    as_of: datetime  # 기준 시각 = clock.now()
    contacts: list[DashboardContact]
    mails: list[DashboardMail]
    tasks: list[DashboardTask]
    # 응답 대기(BE-13). 사용자를 모르면(헤더 없고 dev 사용자도 없음) 빼서 보낸다 — FE는 빠지면 칸을 숨기고 []면 '없음'
    awaiting: list[AwaitingView] | None = None
