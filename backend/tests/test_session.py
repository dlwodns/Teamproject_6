"""브라우저 세션(AUTH_MODE=session, INF-11 11-25) — 브라우저마다 사용자 하나, 헤더로 남의 사용자가 되지 않는다."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Account, Mail, User


@pytest.fixture
def session_mode(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "session")


def test_header_mode_is_unchanged(client):
    r = client.post("/api/session")
    assert r.json() == {"mode": "header", "user_id": None, "created": False}
    assert "cne_session" not in r.cookies


def test_each_browser_gets_own_user(db, session_mode):
    with TestClient(app) as a, TestClient(app) as b:
        ra, rb = a.post("/api/session").json(), b.post("/api/session").json()
        assert ra["created"] and rb["created"] and ra["user_id"] != rb["user_id"]
        again = a.post("/api/session").json()  # 같은 브라우저는 같은 사용자
        assert again == {"mode": "session", "user_id": ra["user_id"], "created": False}
        assert a.get("/api/accounts").status_code == 200


def test_header_is_ignored_in_session_mode(db, session_mode):
    db.add(User(id=1, name="시연"))
    db.commit()
    with TestClient(app) as c:
        assert c.get("/api/accounts", headers={"X-User-Id": "1"}).status_code == 401  # 쿠키 없이 헤더만으로는 못 들어온다
        uid = c.post("/api/session").json()["user_id"]
        assert uid != 1
        assert c.get("/api/accounts", headers={"X-User-Id": "1"}).status_code == 200  # 헤더는 무시하고 세션 사용자


def test_dashboard_shows_only_own_mail(db, session_mode):
    with TestClient(app) as a, TestClient(app) as b:
        ua = a.post("/api/session").json()["user_id"]
        b.post("/api/session")
        acc = Account(user_id=ua, provider="dummy", email="a@example.com")
        db.add(acc)
        db.flush()
        db.add(Mail(account_id=acc.id, source_id="s-a-1", direction="received", sender="x@example.com",
                    subject="A의 메일", sent_at=datetime(2026, 11, 25, 9, 0)))
        db.commit()
        subjects_a = [m["subject"] for m in a.get("/api/dashboard").json()["mails"]]
        subjects_b = [m["subject"] for m in b.get("/api/dashboard").json()["mails"]]
    assert "A의 메일" in subjects_a and "A의 메일" not in subjects_b
    with TestClient(app) as c:
        assert c.get("/api/dashboard").status_code == 401


def test_demo_link(db, session_mode, monkeypatch):
    with TestClient(app) as c:
        assert c.get("/api/session/demo", follow_redirects=False).status_code == 404  # 끄면 없음
        u = User(name="시연")
        db.add(u)
        db.commit()
        monkeypatch.setenv("DEMO_SHARE_USER_ID", str(u.id))
        r = c.get("/api/session/demo", follow_redirects=False)
        assert r.status_code == 303
        assert c.post("/api/session").json()["user_id"] == u.id


def test_bad_auth_mode_is_rejected(monkeypatch):
    from app.core.config import check_settings
    monkeypatch.setenv("AUTH_MODE", "cookie")
    monkeypatch.setenv("DEMO_SHARE_USER_ID", "x")
    errors = check_settings()
    assert any(e.startswith("AUTH_MODE") for e in errors) and any(e.startswith("DEMO_SHARE_USER_ID") for e in errors)
