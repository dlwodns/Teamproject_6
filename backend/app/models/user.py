"""사용자 · 계정 · 연락처 · 설정 · 템플릿 (구조도 v3.1 9절)."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    department: Mapped[str | None] = mapped_column(String(100))
    position: Mapped[str | None] = mapped_column(String(50))  # 직급
    work_hours: Mapped[str | None] = mapped_column(String(20))  # 예: "09:00-18:00"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Account(Base):
    """연결한 메일 계정. 토큰은 암호화해서 저장한다(키는 .env TOKEN_ENCRYPTION_KEY, BE-6)."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(20))  # dummy | outlook_graph | imap
    email: Mapped[str] = mapped_column(String(255))
    access_token_enc: Mapped[str | None] = mapped_column(Text)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (UniqueConstraint("user_id", "provider", "email"),)


class Contact(Base):
    """발신자. 상급자 · 즐겨찾기는 우선순위 · T11 중요 발신자 지정에 쓴다(D9)."""

    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(100))
    position: Mapped[str | None] = mapped_column(String(50))
    is_superior: Mapped[bool] = mapped_column(Boolean, default=False)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (UniqueConstraint("user_id", "email"),)


class UserSettings(Base):
    """사용자당 1행. 기본값은 PL detail 4.2절(R-아침 08:30) · 5절(무응답 3일)."""

    __tablename__ = "settings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    dashboard_layout: Mapped[dict | None] = mapped_column(JSON)
    remind_time: Mapped[str] = mapped_column(String(5), default="08:30")
    quiet_start: Mapped[str | None] = mapped_column(String(5))  # 조용한 시간 시작 "22:00"
    quiet_end: Mapped[str | None] = mapped_column(String(5))
    awaiting_reply_days: Mapped[int] = mapped_column(Integer, default=3)
    read_body: Mapped[bool] = mapped_column(Boolean, default=True)  # 끄면 제목 · 발신자로만 규칙 분류
    stt_mode: Mapped[str] = mapped_column(String(10), default="browser")
    reduce_motion: Mapped[bool] = mapped_column(Boolean, default=False)
    reply_confirm_skip_until: Mapped[datetime | None] = mapped_column(DateTime)  # '오늘 하루 보지 않기': 이 시각(다음 R-아침)까지 답장하면 묻지 않고 완료(D48)


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # reply | send(P2 템플릿 전송). rule은 11-11 뺐다(BE-D20)
    name: Mapped[str] = mapped_column(String(100))
    subject: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)  # 자리표시자 {수신자명} · {원메일제목}

    # 새로 만드는 DB부터 적용된다(create_all은 있는 테이블의 제약을 바꾸지 않는다). 예전 DB의 rule 행은 읽는 곳이 없어 무해하다
    __table_args__ = (CheckConstraint("kind IN ('reply', 'send')", name="ck_templates_kind"),)
