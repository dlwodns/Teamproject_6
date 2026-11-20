"""메일 · 분류 요청 · 업무 (구조도 v3.1 4 · 5 · 9절)."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.db import Base

CATEGORIES = ("회신", "요청", "검토", "공지", "기타")  # D39
TASK_STATUSES = ("pending", "done", "excluded", "snoozed")  # D36 · 구조도 5절
LANES = ("할 일", "확인", "참고")  # 화면 칸(#21, ai/app/schemas/classify.py Lane)
HIDDEN_FOLDERS = ("archive", "deleteditems")  # 보관 · 지운 편지함 메일과 그 업무는 대시보드에 보이지 않는다(BE-7, 11-19)
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
    # BE-7 · FE-5d: 메일함 칸. folder는 Outlook 메일함(inbox · sentitems · archive · deleteditems), 더미는 비어 있다(받은 · 보낸으로 본다).
    # read_at: Outlook은 읽은 시각을 주지 않아 처음 읽음으로 본 동기화 시각을 넣는다. pinned_at은 우리 앱만의 고정(Outlook에 쓰지 않음)
    folder: Mapped[str | None] = mapped_column(String(20))
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
    pinned_at: Mapped[datetime | None] = mapped_column(DateTime)
    # 우리 앱에서만 숨김(11-19): 연결을 끊은 Outlook 계정 메일을 보관 · 지움으로 옮기면 Outlook에 쓸 수 없어 여기만 채운다.
    # 동기화는 이 칸을 건드리지 않는다(다시 연결해도 숨긴 채). 받은 편지함으로 옮기면 비운다
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint("account_id", "source_id"),
        CheckConstraint(_in("direction", ("received", "sent")), name="ck_mails_direction"),
        CheckConstraint(f"category IS NULL OR {_in('category', CATEGORIES)}", name="ck_mails_category"),
        CheckConstraint(f"lane IS NULL OR {_in('lane', LANES)}", name="ck_mails_lane"),
    )


def visible_mail():
    """보이는 메일(SQL 조건): 보관 · 지운 편지함이 아니고 우리 앱에서 숨기지 않은 메일. 대시보드 · 리마인더 · 브리핑 · 캘린더 ·
    응답 대기 · 캐치봇 검색이 모두 이 조건을 쓴다(11-19 사용자 결정: 보관 · 지운 메일의 업무는 어디에도 보이지 않는다).
    업무 id를 골라 직접 바꾸는 길(PATCH /api/tasks, 되돌리기)은 막지 않는다."""
    return (Mail.folder.is_(None) | Mail.folder.not_in(HIDDEN_FOLDERS)) & Mail.hidden_at.is_(None)


def is_visible(mail: "Mail") -> bool:
    return mail.folder not in HIDDEN_FOLDERS and mail.hidden_at is None


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
    started_at: Mapped[datetime | None] = mapped_column(DateTime)  # running으로 꺼낸 시각. 오래 남은 running을 되살린다
    fallback: Mapped[str | None] = mapped_column(Text)  # 모델 실패로 규칙 결과만 저장한 이유. 엑사원 재분류 대상 표시
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
    # BE-15 캘린더(D50 · AI-20): 업무 유형(AI-D15 6종, 일정참석이면 캘린더에 '일정'으로 보인다) · 시각이 메일에 적혀 있었나 ·
    # 일정참석 끝 시각. 옛 행은 비어 있다(유형 모름 · 시각 적힘 모름)
    type: Mapped[str | None] = mapped_column(String(20))
    due_time_stated: Mapped[bool | None] = mapped_column(Boolean)
    end_at: Mapped[datetime | None] = mapped_column(DateTime)
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


class ScheduledSend(Base):
    """예약 보내기(BE-7 단계 2). Graph에 예약 전송 API가 없어 우리 스케줄러가 들고 있다가 그 시각에 보낸다
    (research_outlook_20261119.md 3절 [판단]). 서버가 꺼져 있으면 켜진 뒤 첫 틱에 늦게 나간다.
    request_json은 보내기 요청 그대로(첨부 포함) — 보낸 뒤에는 비운다(본문을 오래 두지 않는다, 구조도 10절)."""

    __tablename__ = "scheduled_sends"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # reply | replyAll | forward | new
    mail_id: Mapped[int | None] = mapped_column(ForeignKey("mails.id", ondelete="CASCADE"))  # 원 메일(새 메일은 없음)
    subject: Mapped[str] = mapped_column(String(255))  # 목록 표시용
    to_text: Mapped[str] = mapped_column(String(500))  # 목록 표시용 받는 사람
    request_json: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))  # 비우면 SQL NULL(JSON null 글자가 아니라)
    send_at: Mapped[datetime] = mapped_column(DateTime, index=True)  # 시간대 없는 KST(D47)
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | sending | sent | failed | unknown | canceled
    error: Mapped[str | None] = mapped_column(String(200))
    sent_mail_id: Mapped[int | None] = mapped_column(ForeignKey("mails.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime)  # '보내는 중'으로 잡은 실제 시각 — 오래 멈춘 것을 찾는다(run_due)
