"""메일 기억하기 (PL-16, 11-11 결정: 설정으로 켬 · 끔, 사내 메일만, 켜면 항목마다 묻지 않고 넣음)."""
import json
from datetime import datetime, timedelta

import pytest

from app.core import clock
from app.dev import seed
from app.models import Account, ActionLog, Contact, Mail, MailingList, Task, User, UserSettings

NOW = datetime(2026, 11, 11, 14, 0)
SIG = "감사합니다.\n\n**********\n{name} {pos} / Taesung Jung\n클라우드사업부 / 클라우드전환담당\nE-Mail : {email}\nPhone : 02-0000-1001\n**********"


@pytest.fixture(autouse=True)
def fixed_clock():
    clock.set_dev_now(NOW)
    yield
    clock.set_dev_now(None)


def _base(db, position="팀장"):
    db.add(User(id=1, name="이준호", department="클라우드전환1팀", position=position))
    db.flush()
    db.add(Account(id=1, user_id=1, provider="dummy", email="junho.lee@lgcns.example"))
    db.commit()


def _mail(db, mid, sender="taesung.jung@lgcns.example", to=("junho.lee@lgcns.example",), cc=()):
    db.add(Mail(id=mid, account_id=1, source_id=f"M-{mid}", direction="received", sender=sender, recipients=list(to),
                cc=list(cc), subject="요청", sent_at=NOW - timedelta(hours=3), category="요청"))
    db.add(Task(mail_id=mid, text="자료 제출"))
    db.commit()


def _ingest(client, mid, body=""):
    r = client.post("/api/dev/scenario/ingest", json={"mail_id": mid, "body": body})
    assert r.status_code == 200, r.text
    return r.json()["learned"]


def _on(client):
    assert client.patch("/api/agent/settings", json={"learn_from_mail": True}).json() == {"learn_from_mail": True}


def _sig(name="정태성", pos="담당", email="taesung.jung@lgcns.example"):
    return SIG.format(name=name, pos=pos, email=email)


def test_on_by_default_and_off_learns_nothing(client, db):
    _base(db)
    _mail(db, 1)
    _mail(db, 2)
    assert client.get("/api/agent/settings").json() == {"learn_from_mail": True}  # 기본 켜짐(11-11)
    assert client.get("/api/agent/memory").json()["learn_from_mail"] is True
    client.patch("/api/agent/settings", json={"learn_from_mail": False})
    assert _ingest(client, 1, _sig()) == []
    assert db.query(Contact).count() == 0
    client.patch("/api/agent/settings", json={"learn_from_mail": True})
    assert [x["action"] for x in _ingest(client, 2, _sig())] == ["memory_people"]


def test_signature_makes_superior_and_shows_everywhere(client, db):
    _base(db)
    _mail(db, 1)
    _on(client)
    learned = _ingest(client, 1, _sig())
    assert [x["action"] for x in learned] == ["memory_people"]
    m = client.get("/api/agent/memory").json()
    p = m["people"][0]
    assert (p["name"], p["position"], p["is_superior"]) == ("정태성", "담당", True)
    assert p["origin"]["text"] == "11/11 메일에서 알게 됐어요"
    item = client.get("/api/actions/history").json()["items"][0]
    assert item["text"] == "메일 서명에서 정태성 담당님을 상급자로 알게 됐어요"
    assert item["via_label"] == "메일에서 알게 됨" and item["auto"] and item["can_undo"]
    cards = client.get("/api/suggestions").json()["suggestions"]
    assert [c["rule"] for c in cards] == ["priority_sender"]
    assert cards[0]["title"].startswith("정태성 담당님 메일을 받은 지")


def test_same_rank_fills_position_only(client, db):
    _base(db)
    _mail(db, 1, sender="minseok.kim@lgcns.example")
    _on(client)
    _ingest(client, 1, _sig("김민석", "팀장", "minseok.kim@lgcns.example"))
    c = db.query(Contact).one()
    assert (c.position, c.is_superior) == ("팀장", False)
    assert client.get("/api/actions/history").json()["items"][0]["text"] == "메일 서명에서 김민석 팀장님의 직급을 알게 됐어요"


def test_external_and_quoted_signatures_are_ignored(client, db):
    _base(db)
    _mail(db, 1, sender="minho.jang@hanbitbank.example")
    _mail(db, 2)
    _on(client)
    assert _ingest(client, 1, _sig("장민호", "차장", "minho.jang@hanbitbank.example")) == []  # 사외 메일
    quoted = "네 확인했습니다.\n\n-----Original Message-----\n" + _sig("한상우", "사업단장", "sangwoo.han@lgcns.example")
    assert _ingest(client, 2, quoted) == []  # 다른 사람 주소의 서명(인용)
    assert db.query(Contact).count() == 0


def test_mailing_list_learned_only_when_i_am_not_addressed(client, db):
    _base(db)
    _mail(db, 1, to=("cloud-leaders@lgcns.example",))
    _mail(db, 2, to=("junho.lee@lgcns.example", "team@lgcns.example"))
    _mail(db, 3, to=("a@lgcns.example", "b@lgcns.example"))
    _mail(db, 4, to=("partners@other.example",))
    _on(client)
    assert _ingest(client, 1) == []  # 보낸 사람 한 명에게서만 → 아직 넣지 않는다(숨은참조 1:1일 수 있음)
    for mid in (2, 3, 4):
        assert _ingest(client, mid) == []
    _mail(db, 5, sender="sangwoo.han@lgcns.example", to=("cloud-leaders@lgcns.example",))
    assert [x["action"] for x in _ingest(client, 5)] == ["memory_me"]  # 두 번째 보낸 사람에게서 확인
    assert [r.address for r in db.query(MailingList)] == ["cloud-leaders@lgcns.example"]
    assert client.get("/api/actions/history").json()["items"][0]["text"] == \
        "메일에서 내가 cloud-leaders@lgcns.example(직책 목록)에 속한 것을 알게 됐어요"


def test_bcc_one_to_one_is_not_a_mailing_list(client, db):
    # #44 리뷰: 숨은참조로 받은 1:1 메일(받는 사람은 동료 한 명)이 그 동료 주소를 내 팀 목록으로 넣으면 안 된다
    _base(db)
    db.add(Contact(id=7, user_id=1, email="minseok.kim@lgcns.example", name="김민석"))
    db.commit()
    _mail(db, 1, to=("minseok.kim@lgcns.example",))  # 연락처에 있는 사람
    _mail(db, 2, sender="sangwoo.han@lgcns.example", to=("minseok.kim@lgcns.example",))
    _mail(db, 3, sender="yujin.choi@lgcns.example", to=("junho.lee@lgcns.example",))  # 그 사람이 나에게 보낸 메일
    _mail(db, 4, to=("yujin.choi@lgcns.example",))
    _mail(db, 5, sender="sangwoo.han@lgcns.example", to=("yujin.choi@lgcns.example",))
    _on(client)
    for mid in (1, 2, 3, 4, 5):
        assert _ingest(client, mid) == []
    assert db.query(MailingList).count() == 0


def test_read_body_off_stops_signature_learning(client, db):
    # 설정 '본문 읽기'를 끄면 본문(서명)을 보는 학습도 하지 않는다(#44 리뷰)
    _base(db)
    db.add(UserSettings(user_id=1, read_body=False))
    db.commit()
    _mail(db, 1)
    _on(client)
    assert _ingest(client, 1, _sig()) == []
    assert db.query(Contact).count() == 0


def test_learn_source_is_separate_from_agent_commands(client, db):
    # 기록의 source는 mail_learn — '말로 시킨 행동'(agent_rule · agent_model) 수와 섞이지 않는다(#44 리뷰)
    _base(db)
    _mail(db, 1)
    _on(client)
    _ingest(client, 1, _sig())
    log = db.query(ActionLog).one()
    assert log.source == "mail_learn" and log.params_json["learned_by"] == "rule"
    item = client.get("/api/actions/history").json()["items"][0]
    assert item["via"] == "mail_learn" and item["auto"] is True


def test_user_undo_is_a_rejection(client, db):
    _base(db)
    _mail(db, 1)
    _mail(db, 2)
    _on(client)
    aid = _ingest(client, 1, _sig())[0]["action_id"]
    assert client.post(f"/api/actions/{aid}/undo").status_code == 200
    assert _ingest(client, 2, _sig()) == []  # 되돌린 것을 다음 메일에서 다시 넣지 않는다
    assert db.query(Contact).one().is_superior is False


def test_user_choice_is_not_overridden(client, db):
    _base(db)
    db.add(Contact(id=5, user_id=1, email="taesung.jung@lgcns.example", name="정태성"))
    db.commit()
    _mail(db, 1)
    client.patch("/api/agent/memory/people/5", json={"is_favorite": True})
    _on(client)
    assert _ingest(client, 1, _sig()) == []
    assert db.get(Contact, 5).is_superior is False


def test_turning_off_stops_learning(client, db):
    _base(db)
    _mail(db, 1)
    _on(client)
    client.patch("/api/agent/settings", json={"learn_from_mail": False})
    assert _ingest(client, 1, _sig()) == []
    assert client.patch("/api/agent/settings", json={"learn_from_mail": "yes"}).status_code == 422


def test_seed_learns_mailing_lists_by_default(tmp_path):
    from sqlalchemy.orm import Session

    data = json.loads(seed.DEFAULT_SOURCE.read_text(encoding="utf-8"))
    engine = seed.demo_engine(tmp_path / "demo_learn.db")
    clock.set_dev_now(None)
    report = seed.load(engine, "2026-12-31T23:59")  # 설정을 건드리지 않음 = 기본 켜짐
    assert report.learned > 0
    with Session(engine) as s:
        lists = {r.address for r in s.query(MailingList)}
        assert lists and lists <= set(data["mailbox"]["member_of"])
        assert s.query(ActionLog).filter(ActionLog.source == "mail_learn").count() == report.learned
