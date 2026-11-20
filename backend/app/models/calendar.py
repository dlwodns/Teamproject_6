"""앱 캘린더 일정 (D50 결정 6 · BE-15). Outlook 캘린더에는 쓰지 않는다.

일정은 업무와 따로 간다. 일정을 넣어도 업무는 완료되지 않고, 업무를 완료 · 미뤄도 일정은 그대로다.
지우면 행을 없애지 않고 deleted_at을 채운다(되돌리기로 살린다). 메일 한 통에 살아 있는 일정은 하나다(services/calendar).
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.db import Base


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    mail_id: Mapped[int | None] = mapped_column(ForeignKey("mails.id", ondelete="CASCADE"), index=True)  # 말로 준 일정은 비어 있다
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))  # 일정참석 업무에서 넣었으면
    title: Mapped[str] = mapped_column(String(200))
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)  # 시간대 없는 KST(D47)
    end_at: Mapped[datetime] = mapped_column(DateTime)  # 메일에 끝 시각이 없으면 시작 + 1시간(D50)
    auto: Mapped[bool] = mapped_column(Boolean, default=False)  # 자동 등록(calendar_auto_add)으로 넣었나. 지금은 늘 False
    action_id: Mapped[int | None] = mapped_column(ForeignKey("action_log.id", ondelete="SET NULL"))  # 만든 행동
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)
    # BE-7 1c: Outlook에 같이 넣은 일정(바뀌지 않는 id)과 그 계정. 빼면 Outlook에서도 지우고 비운다
    outlook_id: Mapped[str | None] = mapped_column(String(255))
    outlook_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    # Outlook 만들기를 시작했다는 표시이자 Graph transactionId — 응답이 끊겨 다시 만들어도 Outlook이 같은 일정으로 본다.
    # outlook_id가 비었는데 이 값이 있으면 아직 반영 안 됨 → 틱이 다시 맞춘다(retry_outlook). 지우기가 끝나면 비운다
    outlook_txn: Mapped[str | None] = mapped_column(String(64))
