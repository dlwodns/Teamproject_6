"""T14 재촉 메일(시연 장면 ⑦): 응답 대기 → 재촉 미리보기(확인 카드) → 확인 → 발송. 발송은 늘 확인(D37)."""
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.ai_client.client import get_ai_client
from app.core.db import engine
from app.dev.seed import load
from app.main import app
from app.models import Account, ActionPreview, Mail, User
from app.schemas.ai import PlanResult
from tests.clock_util import move_to

DEMO = Path(__file__).resolve().parents[2] / "data" / "dummy" / "demo_mails.json"
AT = datetime(2026, 10, 20, 9, 0)  # 시연 시각 B — 응답 대기 2통(장면 ⑥)


class FakeAI:
    def __init__(self):
        self.action, self.target, self.params = "T14", {}, {"template_kind": "nudge"}

    def plan(self, text, actions, *, now, selected_mail_ids=None, last_result_ids=None):
        target = dict(self.target)
        if last_result_ids and "awaiting_reply" not in target:  # '그 2건' → 직전 결과(메일 id)
            target["mail_ids"] = [str(i) for i in last_result_ids]
        return PlanResult.model_validate({"source": "rule", "rules_version": "test", "action": self.action,
                                          "params": self.params if self.action == "T14" else {}, "target": target})


@pytest.fixture
def ai():
    fake = FakeAI()
    app.dependency_overrides[get_ai_client] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_ai_client, None)


@pytest.fixture
def demo(db):
    load(engine, AT.isoformat(), DEMO)
    move_to(AT)
    yield db
    move_to(None)


def _awaiting(client):
    return client.get("/api/awaiting").json()


def _scene6(client, ai) -> list[int]:
    ai.action = "T06"
    r = client.post("/api/agent/command", json={"text": "답장 안 온 메일 있어?"}).json()
    assert r["kind"] == "awaiting" and len(r["awaiting"]) == 2
    ai.action = "T14"
    return [a["mail_id"] for a in r["awaiting"]]


def test_scene_6_then_7_preview_confirm_send(client, demo, ai):
    ids = _scene6(client, ai)
    card = client.post("/api/agent/command", json={"text": "그 2건 재촉 메일 보내줘", "last_result_ids": ids}).json()
    assert card["kind"] == "confirm" and card["action"] == "T14" and card["title"] == "재촉 메일 2통을 보내시겠습니까?"
    assert [s["mail_id"] for s in card["sends"]] == ids and card["preview_id"] and card["expires_at"].endswith("+09:00")
    first = card["sends"][0]
    orig = demo.get(Mail, ids[0])
    assert first["subject"] == f"[확인 요청] {orig.subject}" and first["to"] == _awaiting(client)[0]["to"]
    assert f"{first['to']}님" in first["body"] and f"'{orig.subject}'" in first["body"] and "이준호 드림" in first["body"]
    # 확인 전에는 아무것도 보내지 않는다(D37). 기록 탭에 확인 기다림 줄
    assert demo.scalars(select(Mail).where(Mail.source_id.like("sent-%"))).all() == []
    row = client.get("/api/actions/history").json()["items"][0]
    assert row["state"] == "waiting" and row["text"] == "재촉 메일 2건 보내기 — 확인을 기다려요"

    done = client.post("/api/actions/execute", json={"preview_id": card["preview_id"]})
    assert done.status_code == 200, done.text
    out = done.json()
    assert len(out["sent_mail_ids"]) == 2 and out["skipped"] == [] and out["action_id"] is None
    demo.expire_all()
    sent = demo.get(Mail, out["sent_mail_ids"][0])
    assert (sent.direction, sent.category, sent.recipients, sent.conversation_id, sent.subject) == \
        ("sent", "요청", orig.recipients, orig.conversation_id, f"[확인 요청] {orig.subject}")
    # 재촉은 새 요청 → 응답 대기에서 빠지고, 기준일(3일)이 지나도 답이 없으면 다시 뜬다
    assert _awaiting(client) == []
    move_to(AT + timedelta(days=3, minutes=1))  # 그사이 기준일을 넘긴 다른 보낸 메일도 함께 뜬다
    later = {a["mail_id"] for a in _awaiting(client)}
    assert set(out["sent_mail_ids"]) <= later and not set(ids) & later  # 재촉 메일이 대기, 원래 메일은 빠짐
    # 한 번만 실행된다
    assert client.post("/api/actions/execute", json={"preview_id": card["preview_id"]}).status_code == 409


def test_all_waiting_partial_pick_and_reply_in_between(client, demo, ai):
    ai.target = {"awaiting_reply": True}  # "답장 안 온 거 전부 재촉해"
    card = client.post("/api/agent/command", json={"text": "답장 안 온 거 재촉 메일 보내줘"}).json()
    a, b = [s["mail_id"] for s in card["sends"]]
    # 미리보기 뒤 실행 전에 a 대화에 답이 옴 → a는 보내지 않는다(발송 직전 재확인)
    orig = demo.get(Mail, a)
    demo.add(Mail(account_id=orig.account_id, source_id="M-reply", direction="received", sender=orig.recipients[0],
                  recipients=[orig.sender], subject=f"RE: {orig.subject}", sent_at=AT, conversation_id=orig.conversation_id))
    demo.commit()
    out = client.post("/api/actions/execute", json={"preview_id": card["preview_id"], "mail_ids": [a, b]}).json()
    assert len(out["sent_mail_ids"]) == 1 and out["skipped"] == [{"mail_id": a, "reason": "no_longer_waiting"}]


@pytest.mark.parametrize(("body", "status"), [
    ({"mail_ids": [999]}, 422),  # 미리보기 밖
    ({"mail_ids": []}, 422),
    ({"task_ids": [1]}, 422),  # 재촉 미리보기는 mail_ids로
])
def test_execute_validation(client, demo, ai, body, status):
    ids = _scene6(client, ai)
    card = client.post("/api/agent/command", json={"text": "재촉", "last_result_ids": ids}).json()
    assert client.post("/api/actions/execute", json={"preview_id": card["preview_id"], **body}).status_code == status
    assert demo.get(ActionPreview, card["preview_id"]).used_at is None  # 거절되면 미리보기는 그대로


def test_mail_ids_on_task_preview_is_422(client, demo):
    pid = client.post("/api/tasks/bulk/preview", json={"task_ids": [1, 2], "status": "done"}).json()["preview_id"]
    assert client.post("/api/actions/execute", json={"preview_id": pid, "mail_ids": [1]}).status_code == 422


def test_expired_preview_is_409(client, demo, ai):
    ids = _scene6(client, ai)
    card = client.post("/api/agent/command", json={"text": "재촉", "last_result_ids": ids}).json()
    move_to(AT + timedelta(minutes=6))
    assert client.post("/api/actions/execute", json={"preview_id": card["preview_id"]}).status_code == 409


@pytest.mark.parametrize(("target", "params", "kind"), [
    ({}, {"template_kind": "nudge"}, "ask"),  # 대상 없음
    ({"mail_ids": ["1"]}, {"template_kind": "nudge"}, "empty"),  # 받은 메일 · 응답 대기 아님
    ({"awaiting_reply": True}, {"template_kind": "send"}, "unsupported"),  # 일반 템플릿은 P2
])
def test_ask_empty_unsupported(client, demo, ai, target, params, kind):
    ai.target, ai.params = target, params
    r = client.post("/api/agent/command", json={"text": "재촉"}).json()
    assert r["kind"] == kind and not r.get("preview_id")


def test_outlook_account_cannot_send_yet(client, db, ai):
    db.add(User(id=1, name="이준호"))
    db.flush()
    db.add(Account(id=1, user_id=1, provider="outlook_graph", email="me@cne.com"))
    db.flush()
    db.add(Mail(id=1, account_id=1, source_id="M-1", direction="sent", sender="me@cne.com", recipients=["p@cne.com"],
                subject="자료 요청", sent_at=datetime(2026, 11, 1, 9, 0), category="요청", conversation_id="c1"))
    db.commit()
    move_to(datetime(2026, 11, 11, 9, 0))
    ai.target = {"awaiting_reply": True}
    r = client.post("/api/agent/command", json={"text": "재촉"}).json()
    move_to(None)
    assert r["kind"] == "unsupported" and "Outlook" in r["title"]


def test_other_users_preview_is_404(client, demo, ai):
    ids = _scene6(client, ai)
    card = client.post("/api/agent/command", json={"text": "재촉", "last_result_ids": ids}).json()
    demo.add(User(id=2, name="박서연"))
    demo.commit()
    r = client.post("/api/actions/execute", json={"preview_id": card["preview_id"]}, headers={"X-User-Id": "2"})
    assert r.status_code == 404
