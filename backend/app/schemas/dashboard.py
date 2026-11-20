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
    # BE-7 · FE-5d(provisional.ts 선택 칸). account: 받은 계정 주소. folder: Outlook 메일함(inbox · archive · deleteditems ·
    # other = Outlook에서 옮김), 더미는 null. read_at: null = 안 읽음. pinned_at: null = 고정 안 함
    to: list[str] = []
    account: str | None = None
    folder: str | None = None
    read_at: datetime | None = None
    pinned_at: datetime | None = None


class DashboardTask(BaseModel):
    id: int
    mail_id: int
    text: str
    due_at: datetime | None
    due_raw: str | None  # provisional 외 추가 필드: 메일 속 기한 표현 그대로(이후 기한 라벨용)
    due_source: str
    status: Status
    seen_at: datetime | None
    # 11-20: 메일 읽기의 근거 형광펜(FE-5b)은 이 목록의 업무를 쓴다 — 없으면 실제 서버에서 형광펜이 하나도 칠해지지 않았다
    type: str | None = None  # 업무 유형(AI-D15)
    evidence_text: str | None = None  # 근거 문장(AI-15, 본문 문장을 줄바꿈으로 이은 것)


class DashboardResponse(BaseModel):
    as_of: datetime  # 기준 시각 = clock.now()
    contacts: list[DashboardContact]
    mails: list[DashboardMail]
    tasks: list[DashboardTask]
    # 응답 대기(BE-13). 사용자를 모르면(헤더 없고 dev 사용자도 없음) 빼서 보낸다 — FE는 빠지면 칸을 숨기고 []면 '없음'
    awaiting: list[AwaitingView] | None = None
