"""메일 · 분류 요청 · 업무 (구조도 v3.1 4 · 5 · 9절)."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.db import Base

CATEGORIES = ("회신", "요청", "검토", "공지", "기타")  # D39
TASK_STATUSES = ("pending", "done", "excluded", "snoozed")  # D36 · 구조도 5절
LANES = ("할 일", "확인", "참고")  # 화면 칸(#21, ai/app/schemas/classify.py Lane)
CHECK_REASONS = ("결과 회신", "완료 보고", "해당 여부 확인", "시스템 알림", "읽고 확인")  # ai CheckReason


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Mail(Base):
    """받은 메일 · 보낸 메일 모두 저장한다(보낸 메일은 무응답 계산용, D43). 본문은 저장하지 않는다(구조도 10절)."""

    __tablename__ = "mails"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str] = mapped_column(String(255))  # 원본 메일 id (재동기화 중복 방지)
    conversation_id: Mapped[str | None] = mapped_column(String(255), index=True)
    direction: Mapped[str] = mapped_column(String(10))  # received | sent
    sender: Mapped[str] = mapped_column(String(255))
    recipients: Mapped[list | None] = mapped_column(JSON)
    cc: Mapped[list | None] = mapped_column(JSON)
    subject: Mapped[str] = mapped_column(String(500), default="")
    sent_at: Mapped[datetime] = mapped_column(DateTime, index=True)  # 수신(받은 메일) · 발신(보낸 메일) 시각
    category: Mapped[str | None] = mapped_column(String(10))  # 분류 전이면 비어 있다
    category_source: Mapped[str | None] = mapped_column(String(10))  # rule | exaone
    kind: Mapped[str | None] = mapped_column(String(10))  # 메일 성격 K01~K21, 분류 응답 그대로(#21)
    lane: Mapped[str | None] = mapped_column(String(5))  # 할 일 · 확인 · 참고. 분류 전 · 보낸 메일은 비어 있다(#21)
    web_link: Mapped[str | None] = mapped_column(Text)  # 원문 링크

    __table_args__ = (
        UniqueConstraint("account_id", "source_id"),
        CheckConstraint(_in("direction", ("received", "sent")), name="ck_mails_direction"),
        CheckConstraint(f"category IS NULL OR {_in('category', CATEGORIES)}", name="ck_mails_category"),
        CheckConstraint(f"lane IS NULL OR {_in('lane', LANES)}", name="ck_mails_lane"),
    )


class ClassifyJob(Base):
    """ai /classify 요청 대기열. 받은 메일만 넣는다. ai가 꺼져 있어도 queued로 남는다(구조도 12절 #17)."""

    __tablename__ = "classify_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    mail_id: Mapped[int] = mapped_column(ForeignKey("mails.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(10), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)  # 3회까지 다시 시도
    error: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(255))
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    elapsed_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    __table_args__ = (
        CheckConstraint(_in("status", ("queued", "running", "done", "failed")), name="ck_classify_jobs_status"),
    )


class Task(Base):
    """화면 단위인 업무. 한 메일에 여러 개일 수 있다(D20-6). 상태를 바꾸면 action_log에 남긴다."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    mail_id: Mapped[int] = mapped_column(ForeignKey("mails.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)  # 할 일
    due_raw: Mapped[str | None] = mapped_column(String(100))  # 메일 속 기한 표현 그대로
    due_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    due_source: Mapped[str] = mapped_column(String(10), default="none")
    mentioned_me: Mapped[bool] = mapped_column(Boolean, default=False)
    urgent: Mapped[bool] = mapped_column(Boolean, default=False)  # mentioned_me처럼 메일 단위 분류 값을 업무마다 복사(#21)
    is_follow_up: Mapped[bool] = mapped_column(Boolean, default=False)  # 재요청
    priority: Mapped[str | None] = mapped_column(String(2))  # P1 ~ P3
    source: Mapped[str | None] = mapped_column(String(10))  # rule | exaone
    confidence: Mapped[float | None] = mapped_column(Float)
    span: Mapped[str | None] = mapped_column(Text)
    evidence_text: Mapped[str | None] = mapped_column(Text)  # 저장 여부 [미정] (구조도 10절)
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime)
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime)
    done_at: Mapped[datetime | None] = mapped_column(DateTime)
    seen_at: Mapped[datetime | None] = mapped_column(DateTime)  # 비어 있으면 '새 업무'

    __table_args__ = (
        CheckConstraint(_in("status", TASK_STATUSES), name="ck_tasks_status"),
        CheckConstraint(_in("due_source", ("rule", "model", "none")), name="ck_tasks_due_source"),
        CheckConstraint("status != 'snoozed' OR snoozed_until IS NOT NULL", name="ck_tasks_snoozed_until"),
    )


class MailCheck(Base):
    """확인 칸 항목(분류 응답 checks, #21). 할 일이 없는 메일에만, 메일 1통에 최대 1개.
    업무가 아니라서 Task 지표 · 리마인더에 넣지 않는다."""

    __tablename__ = "mail_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    mail_id: Mapped[int] = mapped_column(ForeignKey("mails.id", ondelete="CASCADE"), unique=True)
    text: Mapped[str] = mapped_column(Text)  # 문구(제목 요지 또는 엑사원 할 일을 옮긴 문구)
    reason: Mapped[str] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(String(10), default="rule")  # rule | exaone(엑사원 할 일을 옮긴 것)
    evidence_text: Mapped[str | None] = mapped_column(Text)  # 저장 여부 [미정] (구조도 10절)
    seen_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        CheckConstraint(_in("reason", CHECK_REASONS), name="ck_mail_checks_reason"),
        CheckConstraint(_in("source", ("rule", "exaone")), name="ck_mail_checks_source"),
    )
