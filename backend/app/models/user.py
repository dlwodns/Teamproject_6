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
    # Graph 변경 알림 구독(BE-7, GRAPH_NOTIFY_URL이 있을 때만). notify_state는 알림의 clientState와 맞춰 보는 값
    subscription_id: Mapped[str | None] = mapped_column(String(100))
    subscription_expires_at: Mapped[datetime | None] = mapped_column(DateTime)  # 실제 시각(real_now, UTC 아님 · naive KST)
    notify_state: Mapped[str | None] = mapped_column(String(64))
    # 로그인 주소 말고 이 계정으로 받는 주소(별칭, 소문자). 분류가 '나에게 온 메일'을 알아보는 데 쓴다(app/mail/profile.py)
    aliases: Mapped[list | None] = mapped_column(JSON)

    __table_args__ = (UniqueConstraint("user_id", "provider", "email"),)


class MailSync(Base):
    """Outlook 메일함별 델타 동기화 위치(BE-7). 다음 동기화는 delta_link부터 바뀐 것만 받는다."""

    __tablename__ = "mail_sync"

    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True)
    folder: Mapped[str] = mapped_column(String(20), primary_key=True)  # inbox | sentitems
    delta_link: Mapped[str | None] = mapped_column(Text)


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
    remind_time: Mapped[str] = mapped_column(String(5), default="08:30")  # 하루 요약(아침 브리핑) 시각
    evening_time: Mapped[str] = mapped_column(String(5), default="17:30")  # 퇴근 회고 시각(주간 회고도 금요일 이 시각)
    quiet_start: Mapped[str | None] = mapped_column(String(5))  # 조용한 시간 시작 "22:00"
    quiet_end: Mapped[str | None] = mapped_column(String(5))
    awaiting_reply_days: Mapped[int] = mapped_column(Integer, default=3)
    read_body: Mapped[bool] = mapped_column(Boolean, default=True)  # 끄면 제목 · 발신자로만 규칙 분류
    stt_mode: Mapped[str] = mapped_column(String(10), default="browser")
    reduce_motion: Mapped[bool] = mapped_column(Boolean, default=False)
    mail_signature: Mapped[str | None] = mapped_column(Text)  # 메일 서명(BE-7). 화면이 보낼 글 끝에 붙인다(Graph에는 서명 API가 없다)
    reply_confirm_skip_until: Mapped[datetime | None] = mapped_column(DateTime)  # '오늘 하루 보지 않기': 이 시각(다음 R-아침)까지 답장하면 묻지 않고 완료(D48)
    # 리마인더 알림 정책(BE-12, 명세 reminders.md 4.2절). 예전 DB에는 시작할 때 칸을 더한다(app/reminders/schema.py)
    work_start: Mapped[str] = mapped_column(String(5), default="09:00")  # 근무 시작. 근무 시간 밖 알림은 다음 근무 시작에 몰아 보낸다
    work_end: Mapped[str] = mapped_column(String(5), default="18:00")
    work_days: Mapped[str] = mapped_column(String(20), default="1-5")  # 1=월 … 7=일. "1-5" · "1,3,5" · "1-3,6"
    away_until: Mapped[datetime | None] = mapped_column(DateTime)  # 부재 중(~까지). 그동안 알림을 보내지 않는다
    reminder_mute: Mapped[dict | None] = mapped_column(JSON)  # {유형: true} = 그 유형 알림 끔(목록에는 남는다)


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # reply | send(P2 템플릿 전송). rule은 11-11 뺐다(BE-D20)
    name: Mapped[str] = mapped_column(String(100))
    subject: Mapped[str | None] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)  # 자리표시자 {수신자명} · {발신자명} · {내용}. 답장 템플릿은 사용자가 자유롭게 쓴 틀
    # 답장 템플릿 이름표(설정 화면, api/settings.py). 예전 DB에는 시작할 때 칸을 더한다(app/reminders/schema.py)
    key: Mapped[str | None] = mapped_column(String(40))

    # 새로 만드는 DB부터 적용된다(create_all은 있는 테이블의 제약을 바꾸지 않는다). 예전 DB의 rule 행은 읽는 곳이 없어 무해하다
    __table_args__ = (CheckConstraint("kind IN ('reply', 'send')", name="ck_templates_kind"),)
