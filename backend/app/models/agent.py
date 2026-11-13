"""에이전트 제안 카드 숨김 · 내 배포 목록 (D50 · PL-16).

둘 다 새 테이블이다. 기존 테이블에 칸을 더하지 않은 것은 마이그레이션 도구가 없어서다(create_all은 있는 테이블에
칸을 더하지 않는다). 새 테이블은 이미 있는 ax.db · demo.db에도 시작할 때 만들어진다.
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.db import Base


class SuggestionHide(Base):
    """[이 제안 숨기기]. 같은 키는 until까지 띄우지 않는다. 키에 카드 종류가 들어 있어 종류가 바뀌면 숨김이 풀린다."""

    __tablename__ = "suggestion_hides"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(100))
    until: Mapped[datetime] = mapped_column(DateTime)  # 다음 R-아침 시각
    mail_ids: Mapped[list | None] = mapped_column(JSON)  # 응답 대기 카드: 숨길 때 기다리던 메일(새 메일이 생기면 다시 뜸)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    __table_args__ = (UniqueConstraint("user_id", "key"),)


class AgentSettings(Base):
    """에이전트 설정(사용자당 1행). settings 표에 칸을 더하지 않고 새 표로 둔다(마이그레이션 도구가 없다).
    행이 없으면 모두 기본값이다."""

    __tablename__ = "agent_settings"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    learn_from_mail: Mapped[bool] = mapped_column(Boolean, default=True)  # 메일 기억하기. 기본 켜짐(11-11, BE-D17)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ContactFact(Base):
    """연락처의 문맥 기억(PL-16, BE-D21): 메일 문장을 모델이 읽고 알아낸 사실. 종류는 정해진 칸뿐이다(BE-D18).
    works_on: 맡은 거래처 · 프로젝트 · 업무 / org: 소속 회사 · 부서. 근거 문장은 본문에 글자 그대로 있던 것."""

    __tablename__ = "contact_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    value: Mapped[str] = mapped_column(String(100))
    evidence: Mapped[str | None] = mapped_column(String(1000))
    mail_id: Mapped[int | None] = mapped_column(ForeignKey("mails.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    __table_args__ = (UniqueConstraint("contact_id", "kind"),
                      CheckConstraint("kind IN ('works_on', 'org')", name="ck_contact_facts_kind"))


class MailingList(Base):
    """내가 속한 배포 목록(내 직책 목록 · 우리 팀 목록). ai 분류 요청의 owner.member_of로 간다(AI-D15)."""

    __tablename__ = "user_mailing_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    address: Mapped[str] = mapped_column(String(255))
    # role: 내 직책 목록(팀장들 등) · team: 우리 팀 목록 · all: 전사 · 단체. role · team으로 온 지시는 나에게 온 것이다(AI-D15)
    kind: Mapped[str] = mapped_column(String(10), default="team")

    __table_args__ = (UniqueConstraint("user_id", "address"),
                      CheckConstraint("kind IN ('role', 'team', 'all')", name="ck_user_mailing_lists_kind"))
