"""DB 규칙 중 테이블 제약으로 막는 것 (구조도 v3.1 9 · 12절)."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.core.db import engine, make_engine
from app.models import Account, ActionLog, Mail, MailCheck, Notification, Reminder, Task, User, UserSettings
from app.reminders import schema

TABLES = {
    "users", "accounts", "contacts", "mails", "classify_jobs", "tasks", "reminders", "notifications",
    "push_subscriptions", "action_log", "action_previews", "settings", "templates", "mail_checks",
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
    row = dict(user_id=1, task_id=task.id, type="due_soon", subject_kind="task", subject_id=task.id, rule="R-기한",
               slot="2026-11-06T15:00", scheduled_at=T0)
    db.add(Reminder(**row))
    db.commit()
    db.add(Reminder(**row))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    # 업무가 없는 항목(보낸 메일 · 약속 · 날짜)은 (user_id, subject_kind, subject_id, rule, slot)로 막는다(BE-12)
    other = dict(user_id=1, task_id=None, type="no_reply", subject_kind="sent_mail", subject_id=99, rule="R-아침",
                 slot="2026-11-07T08:30", scheduled_at=T0)
    db.add(Reminder(**other))
    db.commit()
    db.add(Reminder(**other))
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


def test_classify_columns_defaults(db):
    # #21: kind · lane은 분류 응답 그대로, 분류 전이면 비어 있다. urgent · is_follow_up은 업무마다 복사(기본 False)
    mail = _mail(db)
    task = Task(mail_id=mail.id, text="견적 검토")
    db.add(task)
    db.commit()
    assert mail.kind is None and mail.lane is None
    assert task.urgent is False and task.is_follow_up is False


def test_mail_lane_limited(db):
    _mail(db, "M-0001", kind="K03", lane="확인")
    db.commit()
    with pytest.raises(IntegrityError):
        _mail(db, "M-0002", lane="나중에")  # 할 일 · 확인 · 참고만


def test_mail_check_one_per_mail(db):
    # 확인 칸 항목은 메일 1통에 최대 1개(mail_id 유일), reason은 ai CheckReason 다섯 가지만
    mail_id = _mail(db).id
    db.add(MailCheck(mail_id=mail_id, text="결과 공유", reason="완료 보고", source="exaone"))
    db.commit()
    db.add(MailCheck(mail_id=mail_id, text="또", reason="읽고 확인"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    other = _mail(db, "M-0002").id
    db.add(MailCheck(mail_id=other, text="x", reason="회신 요청"))
    with pytest.raises(IntegrityError):
        db.commit()


def test_old_sqlite_file_is_upgraded():
    # BE-12(BE-D33): 예전 DB의 reminders · notifications(비어 있을 때만) · settings를 create_all 직후 맞춘다
    eng = make_engine("sqlite://")
    with eng.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR(100))"))
        conn.execute(text("CREATE TABLE reminders (id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL, rule VARCHAR(20), "
                          "slot VARCHAR(25), scheduled_at DATETIME)"))
        conn.execute(text("CREATE TABLE notifications (id INTEGER PRIMARY KEY, user_id INTEGER, kind VARCHAR(15), "
                          "title VARCHAR(255), CHECK (kind IN ('reminder', 'reply_confirm')))"))
        conn.execute(text("CREATE TABLE settings (user_id INTEGER PRIMARY KEY, remind_time VARCHAR(5))"))
        conn.execute(text("INSERT INTO settings VALUES (1, '08:30')"))
        done = schema.upgrade(conn)
        assert done == ["notifications 다시 만듦", "reminders 다시 만듦", "settings.work_start 더함", "settings.work_end 더함",
                        "settings.work_days 더함", "settings.away_until 더함", "settings.reminder_mute 더함"]
        assert conn.execute(text("SELECT work_start, work_days FROM settings")).one() == ("09:00", "1-5")
        assert schema.upgrade(conn) == []  # 두 번째는 할 일이 없다
        conn.execute(text("DROP TABLE notifications"))
        conn.execute(text("CREATE TABLE notifications (id INTEGER PRIMARY KEY, kind VARCHAR(15))"))
        conn.execute(text("INSERT INTO notifications VALUES (1, 'reminder')"))
        with pytest.raises(schema.SchemaError):  # 행이 있는 예전 표는 지우지 않고 멈춘다
            schema.upgrade(conn)
