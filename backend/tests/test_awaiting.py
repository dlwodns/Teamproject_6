"""응답 대기(BE-13 · 기획 detail 5절): GET /api/awaiting · 대시보드 awaiting · 에이전트 T06.
판정은 reminders/rules.awaiting_requests 하나라 리마인더 '회신 미수신'과 같은 메일이 나온다."""
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.ai_client.client import get_ai_client
from app.core.db import engine
from app.dev.seed import load
from app.main import app
from app.models import Account, Contact, Mail, ReminderFeedback, User, UserSettings
from app.schemas.ai import PlanResult
from app.services.awaiting import list_awaiting
from tests.clock_util import move_to

NOW = datetime(2026, 11, 11, 14, 0)  # 수요일 오후
DEMO = Path(__file__).resolve().parents[2] / "data" / "dummy" / "demo_mails.json"


@pytest.fixture(autouse=True)
def fixed_clock():
    move_to(NOW)
    yield
    move_to(None)


def _base(db, **settings):
    db.add(User(id=1, name="이준호"))
    db.flush()
    db.add(Account(id=1, user_id=1, provider="dummy", email="me@cne.com"))
    db.add(UserSettings(user_id=1, **settings))
    db.add(Contact(user_id=1, email="park@cne.com", name="박지호", position="매니저"))
    db.flush()


def _mail(db, mid, conv, *, sent_at, direction="sent", sender="me@cne.com", to=("park@cne.com",), category="요청",
          subject="견적 요청드립니다"):
    db.add(Mail(id=mid, account_id=1, source_id=f"M-{mid}", direction=direction, sender=sender, recipients=list(to),
                subject=subject, sent_at=sent_at, category=category, conversation_id=conv))
    db.flush()


def _ids(db, **kw):
    db.commit()
    return [a.mail_id for a in list_awaiting(db, 1, NOW, **kw)]


# ---------- 판정(기획 detail 5절 경계 규칙) ----------

def test_request_without_reply_for_72_hours_is_waiting(db):
    _base(db)
    _mail(db, 1, "c1", sent_at=NOW - timedelta(hours=72))  # 정확히 72시간 → 넣는다
    _mail(db, 2, "c2", sent_at=NOW - timedelta(hours=71, minutes=59))  # 아직 3일이 안 됨
    assert _ids(db) == [1]


def test_reply_from_other_person_removes_it_but_my_copy_does_not(db):
    _base(db)
    _mail(db, 1, "c1", sent_at=NOW - timedelta(days=5))
    _mail(db, 2, "c1", sent_at=NOW - timedelta(days=4), direction="received", sender="park@cne.com", category="회신")
    _mail(db, 3, "c3", sent_at=NOW - timedelta(days=5))
    _mail(db, 4, "c3", sent_at=NOW - timedelta(days=4), direction="received", sender="me@cne.com")  # 내 사본
    assert _ids(db) == [3]


def test_rerequest_after_reply_counts_from_last_request(db):
    _base(db)
    _mail(db, 1, "c1", sent_at=NOW - timedelta(days=9))
    _mail(db, 2, "c1", sent_at=NOW - timedelta(days=8), direction="received", sender="park@cne.com", category="회신")
    _mail(db, 3, "c1", sent_at=NOW - timedelta(days=4), subject="추가 자료 요청드립니다")  # 회신 뒤 다시 요청
    db.commit()
    assert [(a.mail_id, a.days) for a in list_awaiting(db, 1, NOW)] == [(3, 4)]  # 이전 회신으로 풀리지 않는다


def test_one_of_many_replies_removes_it_and_label_shows_others(db):
    _base(db)
    _mail(db, 1, "c1", sent_at=NOW - timedelta(days=5), to=("park@cne.com", "kim@cne.com"))
    _mail(db, 2, "c2", sent_at=NOW - timedelta(days=5), to=("park@cne.com", "kim@cne.com", "lee@cne.com"))
    _mail(db, 3, "c2", sent_at=NOW - timedelta(days=4), direction="received", sender="kim@cne.com", category="회신")
    db.commit()
    rows = list_awaiting(db, 1, NOW)
    assert [(a.mail_id, a.to) for a in rows] == [(1, "박지호 매니저 외 1명")]


def test_not_requests_and_stopped_waiting_are_excluded(db):
    _base(db)
    _mail(db, 1, "c1", sent_at=NOW - timedelta(days=5), category="공지")
    _mail(db, 2, "c2", sent_at=NOW - timedelta(days=5), subject="RE: 견적 요청드립니다")  # 내가 보낸 답장
    _mail(db, 3, "c3", sent_at=NOW - timedelta(days=5))
    _mail(db, 4, "c4", sent_at=NOW - timedelta(days=5))
    db.add(ReminderFeedback(user_id=1, key="no_reply:sent_mail:4", type="no_reply", reason="stop_waiting", created_at=NOW))  # '회신 대기 종료'
    assert _ids(db) == [3]


def test_setting_days_and_min_days_override(db):
    _base(db, awaiting_reply_days=7)
    _mail(db, 1, "c1", sent_at=NOW - timedelta(days=5))
    _mail(db, 2, "c2", sent_at=NOW - timedelta(days=8))
    assert _ids(db) == [2]  # 설정 7일
    assert _ids(db, min_days=3) == [2, 1]  # 오래 기다린 것부터


# ---------- API · 대시보드 ----------

def test_api_shape_and_validation(client, db):
    _base(db)
    _mail(db, 1, "c1", sent_at=datetime(2026, 11, 6, 10, 0))
    db.commit()
    r = client.get("/api/awaiting")
    assert r.status_code == 200
    assert r.json() == [{"mail_id": 1, "subject": "견적 요청드립니다", "to": "박지호 매니저",
                         "sent_at": "2026-11-06T10:00:00+09:00", "days": 5}]
    assert client.get("/api/awaiting?min_days=6").json() == []
    for bad in ("0", "31", "x"):
        assert client.get(f"/api/awaiting?min_days={bad}").status_code == 422


def test_dashboard_carries_awaiting_for_known_user_only(client, db):
    _base(db)
    _mail(db, 1, "c1", sent_at=NOW - timedelta(days=4))
    db.commit()
    assert [a["mail_id"] for a in client.get("/api/dashboard").json()["awaiting"]] == [1]
    assert client.get("/api/dashboard", headers={"X-User-Id": "99"}).json()["awaiting"] is None  # 모르는 사용자: 칸을 숨김


def test_same_mails_as_no_reply_reminder(client, db):
    _base(db)
    _mail(db, 1, "c1", sent_at=NOW - timedelta(days=4))
    _mail(db, 2, "c2", sent_at=NOW - timedelta(days=6))
    db.commit()
    reminders = sorted(i["mail_id"] for i in client.get("/api/reminders").json()["items"] if i["type"] == "no_reply")
    assert reminders == sorted(a["mail_id"] for a in client.get("/api/awaiting").json()) == [1, 2]


# ---------- 에이전트 T06 (시연 장면 ⑥: "답장 안 온 메일 있어?" → 3일 이상 무응답 2건) ----------

class FakeAI:
    def __init__(self, params=None):
        self.params = params or {}

    def plan(self, text, actions, *, now, selected_mail_ids=None, last_result_ids=None):
        return PlanResult.model_validate({"source": "rule", "rules_version": "test", "action": "T06",
                                          "action_name": "무응답_확인", "params": self.params})


@pytest.fixture
def ai():
    fake = FakeAI()
    app.dependency_overrides[get_ai_client] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_ai_client, None)


def test_t06_on_demo_data_lists_two(client, db, ai):
    load(engine, "2026-10-20T09:00", DEMO)  # 시연 데이터(보낸 메일 15통), 시각 B
    move_to(datetime(2026, 10, 20, 9, 0))
    r = client.post("/api/agent/command", json={"text": "답장 안 온 메일 있어?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "awaiting" and body["action"] == "T06"
    assert body["title"] == "보낸 지 3일이 넘도록 회신이 없는 요청 메일 2건입니다"
    assert [a["days"] for a in body["awaiting"]] == [5, 4]
    assert body["awaiting"] == client.get("/api/awaiting").json()  # 화면 목록과 같은 줄


def test_t06_min_days_and_empty_and_bad_value(client, db, ai):
    _base(db)
    _mail(db, 1, "c1", sent_at=NOW - timedelta(days=4))
    db.commit()
    ai.params = {"min_days": 5}
    r = client.post("/api/agent/command", json={"text": "5일 넘게 답 없는 거"}).json()
    assert r["kind"] == "empty" and r["title"] == "보낸 지 5일이 넘도록 회신이 없는 요청 메일은 없습니다"
    for bad in (0, 99, "닷새"):
        ai.params = {"min_days": bad}
        assert client.post("/api/agent/command", json={"text": "답 없는 거"}).json()["kind"] == "ask"
