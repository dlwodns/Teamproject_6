"""DB 규칙 중 테이블 제약으로 막는 것 (구조도 v3.1 9 · 12절)."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.core.db import engine
from app.models import Account, ActionLog, Mail, Notification, Reminder, Task, User, UserSettings

TABLES = {
    "users", "accounts", "contacts", "mails", "classify_jobs", "tasks", "reminders", "notifications",
    "push_subscriptions", "action_log", "action_previews", "settings", "templates",
}
T0 = datetime(2026, 11, 3, 9, 0)


def _mail(db, source_id="M-0001", **kw) -> Mail:
    if db.get(User, 1) is None:  # 외래 키 순서대로 하나씩 넣는다(relationship이 없어 순서를 알아서 정하지 않는다)
        db.add(User(id=1, name="테스트"))
        db.flush()
        db.add(Account(id=1, user_id=1, provider="dummy", email="me@example.com"))
        db.flush()
    mail = Mail(account_id=1, source_id=source_id, direction=kw.pop("direction", "received"),
                sender="lead@example.com", subject="견적 검토 요청", sent_at=T0, **kw)
    db.add(mail)
    db.flush()
    return mail


def test_all_tables_created(db):
    assert TABLES <= set(inspect(engine).get_table_names())


def test_task_defaults_pending(db):
    task = Task(mail_id=_mail(db).id, text="견적 검토")
    db.add(task)
    db.commit()
    assert task.status == "pending"
    assert task.due_source == "none"


def test_resync_same_mail_rejected(db):
    # 재동기화 중복 저장 0건(#2): 같은 계정 · 같은 원본 id는 한 번만
    _mail(db, "M-0001")
    with pytest.raises(IntegrityError):
        _mail(db, "M-0001")


def test_unknown_task_status_rejected(db):
    # #18: archived 같은 상태는 저장되지 않는다
    db.add(Task(mail_id=_mail(db).id, text="x", status="archived"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_snoozed_needs_until(db):
    mail_id = _mail(db).id
    db.commit()  # 아래 rollback에 메일까지 지워지지 않게
    db.add(Task(mail_id=mail_id, text="x", status="snoozed"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(Task(mail_id=mail_id, text="x", status="snoozed", snoozed_until=T0 + timedelta(days=3)))
    db.commit()


def test_reminder_same_slot_once(db):
    # #12: 같은 task · rule · slot 2회 예약 → 1건만
    task = Task(mail_id=_mail(db).id, text="x")
    db.add(task)
    db.flush()
    db.add(Reminder(task_id=task.id, rule="R-기한", slot="2026-11-06T15:00", scheduled_at=T0))
    db.commit()
    db.add(Reminder(task_id=task.id, rule="R-기한", slot="2026-11-06T15:00", scheduled_at=T0))
    with pytest.raises(IntegrityError):
        db.commit()


def test_mail_category_limited_to_five(db):
    with pytest.raises(IntegrityError):
        _mail(db, category="보고")  # D39: 회신 · 요청 · 검토 · 공지 · 기타만


def test_action_log_source_limited(db):
    _mail(db)
    db.add(ActionLog(user_id=1, action="T03", source="claude"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_foreign_keys_enforced(db):
    db.add(Task(mail_id=999, text="x"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_reply_auto_source_allowed(db):
    # D48: '오늘 하루 보지 않기' 기간의 답장은 바로 완료하고 source = reply_auto로 남긴다
    _mail(db)
    db.add(ActionLog(user_id=1, action="reply_complete", source="reply_auto"))
    db.commit()


def test_reply_confirm_skip_until_saved(db):
    _mail(db)
    db.add(UserSettings(user_id=1, reply_confirm_skip_until=datetime(2026, 11, 8, 8, 30)))
    db.commit()
    db.expire_all()
    s = db.get(UserSettings, 1)
    assert s.reply_confirm_skip_until == datetime(2026, 11, 8, 8, 30)
    assert s.remind_time == "08:30"  # 다음 R-아침 시각의 기본값


def test_notification_kinds(db):
    # D48 (나) 경로: Outlook 답장 감지 → 알림 센터 "완료할까요?"
    _mail(db)
    db.add(Notification(user_id=1, title="리마인더"))
    db.add(Notification(user_id=1, kind="reply_confirm", task_ids=[1, 2], title="완료할까요?"))
    db.commit()
    assert {n.kind for n in db.query(Notification)} == {"reminder", "reply_confirm"}
    db.add(Notification(user_id=1, kind="push", title="x"))
    with pytest.raises(IntegrityError):
        db.commit()
