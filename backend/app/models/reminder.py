"""리마인더 · 알림 센터 · 웹 푸시 구독 (구조도 v3.1 7 · 9절, PL detail 4.2절)."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.db import Base


class Reminder(Base):
    """같은 업무 · 규칙 · 발송 시각에는 1건만 저장한다(중복 0, 구조도 12절 #12)."""

    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    rule: Mapped[str] = mapped_column(String(20))  # R-아침 | R-기한 | R-나중에
    slot: Mapped[str] = mapped_column(String(25))  # 규칙별 발송 시각 "2026-11-06T09:00"
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    channel: Mapped[str | None] = mapped_column(String(20))
    skipped_reason: Mapped[str | None] = mapped_column(String(100))  # 발송 직전 완료 · 제외면 건너뛴 이유

    __table_args__ = (UniqueConstraint("task_id", "rule", "slot"),)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    reminder_id: Mapped[int | None] = mapped_column(ForeignKey("reminders.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(255))
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    keys_enc: Mapped[str] = mapped_column(Text)  # 암호화 저장
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
