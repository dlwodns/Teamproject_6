"""메일 한 통 응답 (GET /api/mails/{id}, #55 리뷰). 형식은 FE 임시 계약 frontend/src/api/provisional.ts의 메일 · 업무 칸을 따른다.

대시보드 메일 칸(BE-3 #47)과 같은 이름을 쓰고, 받는 사람 · 본문 · 이 메일의 업무를 더한다. 응답 시각은 +09:00 KST(D47).
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.actions import Status

Category = Literal["회신", "요청", "검토", "공지", "기타"]  # D39 · models/mail.py CATEGORIES


class MailDetailTask(BaseModel):
    id: int
    mail_id: int
    text: str
    due_at: datetime | None
    due_raw: str | None  # 메일 속 기한 표현 그대로
    due_source: str
    status: Status
    seen_at: datetime | None
    evidence_text: str | None  # 근거 문장(AI-15). 화면이 본문에서 이 문장을 형광펜으로 칠한다


class MailDetailSummary(BaseModel):
    """AI-32: 분류 때 같이 만든 메일 요약(ai MailSummary). 화면은 읽기 창 맨 위에 요약 → 업무 → 원문 순서로 보인다."""
    lang: str
    gist: str  # 한국어 요지 1~2문장
    asks: list[str] = []
    due_text: str | None = None


class MailDetail(BaseModel):
    id: int
    source_id: str
    direction: Literal["received", "sent"]
    sender: str
    subject: str
    received_at: datetime  # DB mails.sent_at(받은 메일은 수신 시각, 보낸 메일은 발신 시각)
    category: Category | None  # 분류 전이면 null
    lane: str | None  # 할 일 · 확인 · 참고. 분류 전 · 보낸 메일은 null
    to: list[str]
    cc: list[str]
    body: str  # 원본에서 그때 가져온 본문(DB에 저장하지 않는다, 구조도 10절)
    # AI-42: 거른 HTML 본문(Outlook HTML 메일만). 붙은 그림은 /api/mails/{id}/inline/{cid}로 바꿔 둔다. 없으면 화면은 body를 쓴다
    body_html: str | None = None
    tasks: list[MailDetailTask]
    summary: MailDetailSummary | None = None  # 분류 전 · 요약 못 함이면 null
