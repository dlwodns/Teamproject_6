"""서비스 안 답장 보내기 POST /api/mails/{id}/reply (BE-5 · D48 (가)). 보낸 메일로 같은 대화에 남기고,
화면 시트로 이미 물은 업무는 답장 감지 알림(reply_confirm)으로 다시 묻지 않는다."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Account, Mail, Task, User
from app.reminders import engine
from tests.clock_util import move_to

NOW = datetime(2026, 11, 11, 14, 0)
BODY = {"account": "사내", "subject": "RE: 견적 회신 요청", "content": "확인했습니다. 내일까지 보내 드리겠습니다.",
        "template_key": None}


@pytest.fixture(autouse=True)
def fixed_clock():
    move_to(NOW)
    yield
    move_to(None)


def _base(db, provider="dummy"):
    db.add(User(id=1, name="이준호"))
    db.add(User(id=2, name="박서연"))
    db.flush()
    db.add(Account(id=1, user_id=1, provider=provider, email="me@cne.com"))
    db.add(Account(id=2, user_id=2, provider="dummy", email="park@cne.com"))
    db.flush()
    db.add(Mail(id=1, account_id=1, source_id="M-1", direction="received", sender="kim@cne.com", recipients=["me@cne.com"],
                subject="견적 회신 요청", sent_at=NOW - timedelta(hours=3), category="회신", conversation_id="c1"))
    db.add(Mail(id=2, account_id=2, source_id="M-2", direction="received", sender="x@cne.com", recipients=["park@cne.com"],
                subject="남의 메일", sent_at=NOW - timedelta(hours=3), conversation_id="c2"))
    db.add(Mail(id=3, account_id=1, source_id="M-3", direction="sent", sender="me@cne.com", recipients=["lee@cne.com"],
                subject="자료 요청", sent_at=NOW - timedelta(hours=3), category="요청", conversation_id="c3"))
    db.flush()
    db.add(Task(id=1, mail_id=1, text="견적 회신", status="pending"))
    db.add(Task(id=2, mail_id=1, text="단가표 첨부", status="pending"))
    db.commit()


def _types(db, at=NOW):
    db.expire_all()
    return {(i["type"], i["task_id"]) for i in engine.items(db, 1, at)}


def test_send_records_sent_mail_in_same_conversation(client, db):
    _base(db)
    r = client.post("/api/mails/1/reply", json=BODY)
    assert r.status_code == 200, r.text
    assert r.json()["sent_at"] == "2026-11-11T14:00:00+09:00"
    sent = db.get(Mail, r.json()["id"])
    assert (sent.direction, sent.sender, sent.recipients, sent.conversation_id, sent.subject, sent.account_id) == \
        ("sent", "me@cne.com", ["kim@cne.com"], "c1", "RE: 견적 회신 요청", 1)
    assert db.get(Task, 1).status == "pending"  # 완료는 화면 시트(예) · '오늘 다시 보지 않음'이 한다(D48)


def test_in_app_reply_is_not_asked_again_by_reply_detection(client, db):
    _base(db)
    assert client.post("/api/mails/1/reply", json=BODY).status_code == 200
    assert not {t for t, _ in _types(db, NOW + timedelta(minutes=1))} & {"reply_confirm"}  # (가)로 물었다 → (나) 안 물음
    # 서비스 밖(Outlook)에서 다른 답장을 또 보내면 그 답장으로는 다시 묻는다(BE-12 규칙 그대로)
    db.add(Mail(account_id=1, source_id="M-out", direction="sent", sender="me@cne.com", recipients=["kim@cne.com"],
                subject="RE: 견적 회신 요청", sent_at=NOW + timedelta(minutes=5), conversation_id="c1"))
    db.commit()
    assert ("reply_confirm", 1) in _types(db, NOW + timedelta(minutes=6))


def test_reply_without_re_prefix_is_not_awaiting_reply(client, db):
    _base(db)
    r = client.post("/api/mails/1/reply", json={**BODY, "subject": "견적 보내 드립니다"})  # 제목에서 RE:를 지움
    assert r.status_code == 200
    later = NOW + timedelta(days=5)
    no_reply = {i["mail_id"] for i in (engine.items(db, 1, later)) if i["type"] == "no_reply"}
    assert r.json()["id"] not in no_reply and 3 in no_reply  # 내 답장은 요청이 아니다(응답 대기 · 회신 미수신에 안 들어감)


@pytest.mark.parametrize(("mail_id", "status"), [(2, 404), (999, 404), (3, 422)])  # 남의 메일 · 없는 메일 · 보낸 메일
def test_wrong_mail(client, db, mail_id, status):
    _base(db)
    assert client.post(f"/api/mails/{mail_id}/reply", json=BODY).status_code == status
    assert db.scalars(select(Mail).where(Mail.source_id.like("sent-%"))).all() == []


def test_disconnected_outlook_account_is_409(client, db):
    _base(db, provider="outlook_graph")  # 토큰 없음 = 연결을 끊었거나 아직 연결 전(BE-7)
    r = client.post("/api/mails/1/reply", json=BODY)
    assert r.status_code == 409  # 다시 연결하라고 알린다
    assert db.scalars(select(Mail).where(Mail.direction == "sent", Mail.conversation_id == "c1")).all() == []


@pytest.mark.parametrize("body", [{**BODY, "content": "   "}, {**BODY, "subject": ""}, {**BODY, "to": "x@y.z"},
                                  {**BODY, "subject": "가" * 256}, {k: v for k, v in BODY.items() if k != "content"}])
def test_bad_request_is_422_and_nothing_sent(client, db, body):
    _base(db)
    assert client.post("/api/mails/1/reply", json=body).status_code == 422
    assert db.scalars(select(Mail).where(Mail.direction == "sent", Mail.conversation_id == "c1")).all() == []
