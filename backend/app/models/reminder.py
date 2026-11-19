"""리마인더 · 알림 센터 · 약속 · AI 신호 · 웹 푸시 구독 (구조도 v3.1 7 · 9절, PL detail 4.2절, 명세 reminders.md 7.1절 BE-12).

예전 DB의 reminders · notifications 표는 새 칸 · 제약을 받으려고 시작할 때 다시 만든다(비어 있을 때만, app/reminders/schema.py).
"""
from datetime import date, datetime

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.clock import now
from app.core.db import Base


class Reminder(Base):
    """리마인더 알림 발송 기록 한 줄 = 항목 하나를 한 시각(slot)에 알린 것(또는 알리려다 건너뛴 것).

    항목 자체(지금 챙길 것)는 저장하지 않고 매번 DB 값으로 다시 계산한다(app/reminders/rules.py). 여기에는 '언제 몇 번 알렸나'만
    남는다. 같은 항목 · 규칙 · 시각에는 1건만 저장한다(중복 0, 구조도 12절 #12 · 명세 reminders.md 4.2절 8번).
    - 업무 항목: (task_id, rule, slot) 유일. 업무가 없는 항목(보낸 메일 · 약속 · 날짜)은 (user_id, subject_kind, subject_id, rule, slot).
    - rule은 발송 시각 규칙(R-아침 · R-기한 · R-나중에 · R-회의 · R-즉시 · R-복귀 · R-퇴근 · R-주간), type은 리마인더 유형 코드.
    - notify_count는 이 항목의 몇 번째 알림인지(1~3), state는 이 알림 뒤 항목 상태(3번째면 quiet).
    - skipped_reason이 있으면 보내지 않은 줄이다(발송 직전 재확인 · 부재 중). 알림 횟수에 세지 않는다.
    """

    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(20))  # 리마인더 유형(overdue 등, app/reminders/types.py)
    subject_kind: Mapped[str] = mapped_column(String(12))  # task | sent_mail | commitment | day
    subject_id: Mapped[int] = mapped_column(Integer)  # 업무 · 메일 · 약속 id, day는 YYYYMMDD
    rule: Mapped[str] = mapped_column(String(20))  # R-아침 | R-기한 | R-나중에 | R-회의 | R-즉시 | R-복귀 | R-퇴근 | R-주간
    slot: Mapped[str] = mapped_column(String(25))  # 규칙별 발송 시각 "2026-11-06T09:00"
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True)  # 근무 시간 · 조용한 시간을 반영해 실제로 보낼 시각
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    channel: Mapped[str | None] = mapped_column(String(20))  # center(알림 한 건) | digest(묶음 알림에 들어감)
    skipped_reason: Mapped[str | None] = mapped_column(String(100))  # 발송 직전 완료 · 제외 · 미룸 · 부재 중이면 건너뛴 이유
    notify_count: Mapped[int] = mapped_column(Integer, default=0)
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime)
    state: Mapped[str] = mapped_column(String(10), default="active")
    notification_id: Mapped[int | None] = mapped_column(ForeignKey("notifications.id", ondelete="SET NULL"))

    __table_args__ = (
        UniqueConstraint("task_id", "rule", "slot"),
        UniqueConstraint("user_id", "subject_kind", "subject_id", "rule", "slot"),
        CheckConstraint("subject_kind IN ('task', 'sent_mail', 'commitment', 'day')", name="ck_reminders_subject_kind"),
        CheckConstraint("state IN ('active', 'done', 'dismissed', 'quiet')", name="ck_reminders_state"),
    )


class Notification(Base):
    """알림 센터. reminder는 리마인더 한 건, reply_confirm은 Outlook 답장 감지 뒤 "완료할까요?"(D48 (나) 경로),
    digest는 여러 건을 하나로 묶은 알림(같은 분에 3건 이상 · 부재 중 복귀 · 퇴근 · 주간 회고, 명세 4.2 · 4.3절)."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(15), default="reminder")
    type: Mapped[str | None] = mapped_column(String(20))  # 리마인더 유형. digest는 묶음 이름(digest · away_return · evening · weekly)
    group: Mapped[str | None] = mapped_column(String(10))  # 리마인더 묶음(due · waiting …). digest는 비어 있다
    reminder_key: Mapped[str | None] = mapped_column(String(100))  # 항목 키(overdue:task:12). digest는 비어 있다
    reminder_keys: Mapped[list] = mapped_column(JSON, default=list)  # digest에 들어간 항목 키
    reminder_id: Mapped[int | None] = mapped_column(Integer)  # 발송 기록(reminders.id). 서로 가리켜 외래 키는 reminders 쪽에만 둔다
    rule: Mapped[str | None] = mapped_column(String(20))  # 발송 시각 규칙(R-아침 등)
    task_ids: Mapped[list] = mapped_column(JSON, default=list)  # reply_confirm이 묻는 업무 · 알림이 가리키는 업무
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text)  # 둘째 줄(이유)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime)  # reply_confirm에 예 · 아니오로 답한 시각
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)

    __table_args__ = (
        CheckConstraint("kind IN ('reminder', 'reply_confirm', 'digest')", name="ck_notifications_kind"),
    )


class Commitment(Base):
    """약속(명세 3.1절). 내가 보낸 메일의 "금요일까지 드리겠습니다"(who=me), 상대 답장의 "보내 드릴게요"(who=them).
    업무(tasks)와 섞지 않는다. 섞으면 대시보드 미처리 수와 '업무 누락 0' 기준이 흔들린다. 리마인더에서만 쓴다."""

    __tablename__ = "commitments"

    id: Mapped[int] = mapped_column(primary_key=True)
    mail_id: Mapped[int] = mapped_column(ForeignKey("mails.id", ondelete="CASCADE"), index=True)
    who: Mapped[str] = mapped_column(String(5))  # me | them
    text: Mapped[str] = mapped_column(Text)  # 무엇을 하겠다
    due_raw: Mapped[str | None] = mapped_column(String(100))
    due_at: Mapped[datetime | None] = mapped_column(DateTime)
    evidence_text: Mapped[str | None] = mapped_column(Text)  # 본문에 글자 그대로 있던 문장
    status: Mapped[str] = mapped_column(String(10), default="open")
    source: Mapped[str] = mapped_column(String(10), default="exaone")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    __table_args__ = (
        CheckConstraint("who IN ('me', 'them')", name="ck_commitments_who"),
        CheckConstraint("status IN ('open', 'done', 'dismissed')", name="ck_commitments_status"),
        CheckConstraint("source IN ('exaone', 'rule')", name="ck_commitments_source"),
    )


class ReminderSignal(Base):
    """ai /signals가 돌려준 신호(AI-24). due_change: 같은 대화의 새 메일이 기한을 바꿨다 · resolved: 끝났다고 한다 ·
    question: 이 메일이 나에게 질문한다(끊긴 대화 판정). 자동으로 적용하지 않고 사용자가 버튼을 누를 때만 쓴다(D36 · D48)."""

    __tablename__ = "reminder_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    mail_id: Mapped[int] = mapped_column(ForeignKey("mails.id", ondelete="CASCADE"), index=True)  # 신호가 나온 메일
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)  # question은 비어 있다
    kind: Mapped[str] = mapped_column(String(12))
    new_due_raw: Mapped[str | None] = mapped_column(String(100))
    new_due_at: Mapped[datetime | None] = mapped_column(DateTime)
    reason: Mapped[str | None] = mapped_column(String(20))  # resolved: done_by_other | cancelled | not_needed
    evidence_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    __table_args__ = (
        CheckConstraint("kind IN ('due_change', 'resolved', 'question')", name="ck_reminder_signals_kind"),
        CheckConstraint("status IN ('open', 'applied', 'rejected')", name="ck_reminder_signals_status"),
    )


class ReminderFeedback(Base):
    """리마인더 항목에 사용자가 준 답(명세 4.2절 6번). 숨기기(다음 R-아침까지)는 제안 카드 숨김(suggestion_hides)을 같이 쓰고,
    여기에는 오래 남는 답만 둔다: not_mine(같은 발신자 · 유형은 알림 대신 목록에만) · wrong_signal · keep(신호를 거절)
    · stop_waiting(그만 기다리기). 신고 건수는 AI 정밀도 측정에 쓴다. ref_id는 그 답이 가리킨 메일(답장 감지는 그 답장)."""

    __tablename__ = "reminder_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(100), index=True)
    type: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(String(15))
    sender: Mapped[str | None] = mapped_column(String(255))  # not_mine: 그 업무 메일의 발신자(소문자)
    ref_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    __table_args__ = (
        CheckConstraint("reason IN ('not_mine', 'wrong_signal', 'keep', 'stop_waiting')", name="ck_reminder_feedback_reason"),
    )


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    keys_enc: Mapped[str] = mapped_column(Text)  # 암호화 저장
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class SignalCheck(Base):
    """메일 한 통의 ai /signals 호출 상태(BE-12). 같은 메일을 두 번 부르지 않고, 실패하면 정해진 규칙으로 다시 부른다(AI-D19):
    quota는 시도로 세지 않고 다음에 · model_failed · bad_output은 시도로 세어 3번까지 · empty_body는 다시 부르지 않음 ·
    ai가 꺼짐(연결 실패 · 제한 시간)은 queued로 남김 · ai에 /signals가 없음(404)은 skipped."""

    __tablename__ = "signal_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    mail_id: Mapped[int] = mapped_column(ForeignKey("mails.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(10), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        CheckConstraint("status IN ('queued', 'done', 'failed', 'skipped')", name="ck_signal_checks_status"),
    )


class BriefingHeadline(Base):
    """요약 · 회고 맨 위 머리 문장(AI-29, ai io_spec 3절). 정한 시각에 한 번 미리 만들어 둔다(모델 1회 수 분).
    화면 · 대화는 이것을 읽는다. 모델이 실패하면 ai가 준 코드 문장을 저장한다(source=code, fallback에 사유)."""

    __tablename__ = "briefing_headlines"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # morning | evening | weekly
    day: Mapped[date] = mapped_column(Date)  # 브리핑 날짜(주간은 그 주 금요일)
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(10))  # exaone | code
    prompt_version: Mapped[str | None] = mapped_column(String(50))
    fallback: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    __table_args__ = (UniqueConstraint("user_id", "kind", "day"),)


import app.reminders.schema  # noqa: E402,F401  create_all 직후 예전 DB의 표를 맞춘다(BE-12)
