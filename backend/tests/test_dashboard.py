"""대시보드 원자료 API (BE-3): GET /api/dashboard.

- 시연 DB와 같은 원본(data/dummy/demo_mails.json)을 시연 시각 B(2026-10-20 09:00 KST)로 메모리 DB에 적재해
  scripts/demo_expected.py 실행 결과와 맞춘다. 기존 demo*.db 파일은 쓰지 않는다.
- 응답이 FE adapter 계약(frontend/src/api/adapter.ts)을 지키는지 검사한다.
- BE-4 서비스로 상태를 바꾼 뒤 다시 조회하면 숫자가 바뀌는지 본다.
"""
import re
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core import clock
from app.core.db import engine
from app.dev import seed
from app.models import Mail, Task
from app.services import task_status

SOURCE = Path(__file__).resolve().parents[2] / "data" / "dummy" / "demo_mails.json"
AS_OF_B = datetime(2026, 10, 20, 9, 0, 0)  # BE-D15: 시간대 없는 KST

# scripts/demo_expected.py --source ../data/dummy/demo_mails.json --as-of 2026-10-20T09:00 실행 결과(2026-11-12 확인)
EXPECTED_ALL_MAILS = 115  # 스크립트 "mails": 받은 메일 + 보낸 메일
EXPECTED_RECEIVED_MAILS = 100  # API mails[]: 받은 메일만(보낸 메일 15통 제외)
EXPECTED_TASKS = 62
EXPECTED_SENDER_TASKS = 3
EXPECTED_SENDER_MAIL_IDS = ["M-0026", "M-0040", "M-0089"]
EXPECTED_DUE_TODAY_REMAINING = 9
EXPECTED_OVERDUE = 9
EXPECTED_NO_DUE = 17

CATEGORIES = {"회신", "요청", "검토", "공지", "기타"}
STATUSES = {"pending", "done", "excluded", "snoozed"}
ISO_WITH_OFFSET = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})$")  # adapter.ts


@pytest.fixture
def seeded(db, monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: AS_OF_B)
    seed.load(engine, AS_OF_B, SOURCE)  # conftest의 메모리 DB
    return db


def _get(client) -> dict:
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    return r.json()


def _pending(body: dict) -> list[dict]:
    return [t for t in body["tasks"] if t["status"] == "pending"]


def _status_count(body: dict, status: str) -> int:
    return sum(1 for t in body["tasks"] if t["status"] == status)


def test_matches_demo_expected(client, seeded):
    body = _get(client)
    assert body["as_of"] == "2026-10-20T09:00:00+09:00"

    # 스크립트의 전체 메일 수(115)는 DB 기준, API는 받은 메일(100)만
    assert seeded.scalar(select(func.count()).select_from(Mail)) == EXPECTED_ALL_MAILS
    assert len(body["mails"]) == EXPECTED_RECEIVED_MAILS
    assert {m["direction"] for m in body["mails"]} == {"received"}
    assert len(body["tasks"]) == EXPECTED_TASKS

    as_of = datetime.fromisoformat(body["as_of"])
    pending = _pending(body)
    assert len(pending) == EXPECTED_TASKS  # 시드 직후 모두 미처리
    dues = [datetime.fromisoformat(t["due_at"]) for t in pending if t["due_at"]]
    assert sum(1 for d in dues if d.date() == as_of.date() and d >= as_of) == EXPECTED_DUE_TODAY_REMAINING
    assert sum(1 for d in dues if d < as_of) == EXPECTED_OVERDUE
    assert sum(1 for t in pending if t["due_at"] is None) == EXPECTED_NO_DUE

    # '김 팀장'(성 + 직급) → 연락처 이메일 → 그 발신자 메일의 미처리 업무
    kim = {c["email"] for c in body["contacts"] if (c["name"] or "").startswith("김") and c["position"] == "팀장"}
    mails = {m["id"]: m for m in body["mails"]}
    sender_tasks = [t for t in pending if mails[t["mail_id"]]["sender"] in kim]
    assert len(sender_tasks) == EXPECTED_SENDER_TASKS
    assert sorted({mails[t["mail_id"]]["source_id"] for t in sender_tasks}) == EXPECTED_SENDER_MAIL_IDS


def test_follows_fe_adapter_contract(client, seeded):
    body = _get(client)
    assert set(body) == {"as_of", "contacts", "mails", "tasks"}
    assert ISO_WITH_OFFSET.match(body["as_of"])

    for c in body["contacts"]:
        assert isinstance(c["email"], str)
        assert c["name"] is None or isinstance(c["name"], str)
        assert c["position"] is None or isinstance(c["position"], str)
        assert isinstance(c["is_superior"], bool) and isinstance(c["is_favorite"], bool)

    mail_ids = [m["id"] for m in body["mails"]]
    assert all(type(i) is int for i in mail_ids)
    assert len(mail_ids) == len(set(mail_ids))
    for m in body["mails"]:
        assert m["direction"] in {"received", "sent"}
        assert "category" in m and (m["category"] is None or m["category"] in CATEGORIES)
        assert isinstance(m["source_id"], str) and isinstance(m["sender"], str) and isinstance(m["subject"], str)
        assert ISO_WITH_OFFSET.match(m["received_at"])

    task_ids = [t["id"] for t in body["tasks"]]
    assert all(type(i) is int for i in task_ids)
    assert len(task_ids) == len(set(task_ids))
    for t in body["tasks"]:
        assert type(t["mail_id"]) is int and t["mail_id"] in set(mail_ids)  # 참조 완전성(계약 비교 4절)
        assert t["status"] in STATUSES
        assert isinstance(t["text"], str) and isinstance(t["due_source"], str)
        for key in ("due_at", "seen_at"):
            assert t[key] is None or ISO_WITH_OFFSET.match(t[key]), key


def test_contract_allows_nulls(client, db, monkeypatch):
    # 분류 전 메일(category null) · 기한 없음 · seen_at 없음 · due_raw 없음은 null로 보낸다(필드를 빼지 않는다)
    monkeypatch.setattr(clock, "now", lambda: AS_OF_B)
    from app.models import Account, User

    db.add(User(id=1, name="테스트"))
    db.flush()
    db.add(Account(id=1, user_id=1, provider="dummy", email="me@example.com"))
    db.flush()
    db.add(Mail(id=1, account_id=1, source_id="M-1", direction="received", sender="a@example.com", subject="",
                sent_at=AS_OF_B))
    db.flush()
    db.add(Task(id=1, mail_id=1, text="할 일"))
    db.commit()
    body = _get(client)
    assert body["mails"][0]["category"] is None
    t = body["tasks"][0]
    assert t["due_at"] is None and t["seen_at"] is None and t["due_raw"] is None
    assert t["due_source"] == "none"


def test_excludes_sent_mails_and_their_tasks(client, db, monkeypatch):
    monkeypatch.setattr(clock, "now", lambda: AS_OF_B)
    from app.models import Account, User

    db.add(User(id=1, name="테스트"))
    db.flush()
    db.add(Account(id=1, user_id=1, provider="dummy", email="me@example.com"))
    db.flush()
    db.add_all([
        Mail(id=1, account_id=1, source_id="R-1", direction="received", sender="a@example.com", sent_at=AS_OF_B),
        Mail(id=2, account_id=1, source_id="S-1", direction="sent", sender="me@example.com", sent_at=AS_OF_B),
    ])
    db.flush()
    db.add_all([Task(id=1, mail_id=1, text="받은 메일 업무"), Task(id=2, mail_id=2, text="보낸 메일 업무")])
    db.commit()
    body = _get(client)
    assert [m["source_id"] for m in body["mails"]] == ["R-1"]
    assert [t["id"] for t in body["tasks"]] == [1]


def test_due_raw_preserved(client, seeded):
    body = _get(client)
    db_raw = dict(seeded.execute(select(Task.id, Task.due_raw)).all())
    assert {t["id"]: t["due_raw"] for t in body["tasks"]} == db_raw
    raws = [t["due_raw"] for t in body["tasks"]]
    assert any(isinstance(r, str) for r in raws) and any(r is None for r in raws)  # 두 경우 모두 있는 데이터
    # 예: '10/22(목)까지' 같은 원문 표현이 바뀌지 않고 그대로 온다
    t = next(t for t in body["tasks"] if t["due_raw"])
    assert t["due_raw"] == seeded.get(Task, t["id"]).due_raw


def test_counts_change_after_status_change(client, seeded):
    before = _get(client)
    target = _pending(before)[0]["id"]

    task_status.change_status(seeded, [target], "done")  # BE-4 서비스(버튼 · 에이전트가 같이 쓰는 함수)
    seeded.commit()

    after = _get(client)
    assert next(t for t in after["tasks"] if t["id"] == target)["status"] == "done"
    assert len(_pending(after)) == len(_pending(before)) - 1
    assert _status_count(after, "done") == _status_count(before, "done") + 1
    assert len(after["tasks"]) == len(before["tasks"])  # 완료해도 목록에서 빠지지 않는다(FE 상태별 집계용)
