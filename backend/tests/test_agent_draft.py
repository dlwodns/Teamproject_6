"""에이전트 T07 회신 초안: 대상 메일 하나 → 개인정보 가리기 → ai /draft → 되돌려 초안 카드(보내지 않음, D37)."""
import json
from datetime import datetime

import pytest

from app.ai_client.client import AIError, get_ai_client
from app.main import app
from app.models import Account, Contact, Mail, Task, User, UserSettings
from app.schemas.ai import DraftResult, PlanResult

BODY = "이준호 팀장님, 견적서를 내일까지 회신 부탁드립니다.\n\n김민석 팀장 / 010-1234-5678"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    src = tmp_path / "dummy.json"
    src.write_text(json.dumps({"mails": [{"mail": {"id": f"M-{i}", "body": BODY}} for i in (1, 2, 3)]}), encoding="utf-8")
    monkeypatch.setenv("DUMMY_MAIL_SOURCE", str(src))
    yield
    app.dependency_overrides.pop(get_ai_client, None)


def _base(db):
    db.add(User(id=1, name="이준호"))
    db.add(User(id=2, name="박서연"))
    db.flush()
    db.add(Account(id=1, user_id=1, provider="dummy", email="junho.lee@cne.com"))
    db.add(Account(id=2, user_id=2, provider="dummy", email="park@cne.com"))
    db.add(Contact(user_id=1, email="minseok.kim@cne.com", name="김민석", position="팀장"))
    db.flush()
    for mid, acc, sender in [(1, 1, "minseok.kim@cne.com"), (2, 1, "minseok.kim@cne.com"), (3, 2, "x@cne.com")]:
        db.add(Mail(id=mid, account_id=acc, source_id=f"M-{mid}", direction="received", sender=sender,
                    recipients=["junho.lee@cne.com"], subject=f"견적 요청 {mid}", sent_at=datetime(2026, 11, 11, 9, mid)))
    db.flush()
    db.add(Task(id=1, mail_id=1, text="견적서 회신", status="pending"))
    db.commit()


class FakeAI:
    def __init__(self, target, *, draft_error=None, source="exaone"):
        self.target, self.draft_error, self.source, self.drafts = target, draft_error, source, []

    def plan(self, text, actions, *, now, selected_mail_ids=None, last_result_ids=None):
        target = {**self.target, "mail_ids": [str(i) for i in (selected_mail_ids or [])]} if selected_mail_ids else self.target
        return PlanResult.model_validate({"source": "rule", "rules_version": "test", "action": "T07",
                                          "action_name": "회신_초안", "target": target, "params": {"tone": "polite"}})

    def draft(self, payload):
        self.drafts.append(payload)
        if self.draft_error:
            raise self.draft_error
        # 모델처럼: 가린 이름(김◯◯)을 그대로 써서 답한다
        return DraftResult(subject=f"RE: {payload['mail']['subject']}", source=self.source,
                           body=f"{(payload['mail']['body'].splitlines() or [''])[-1].split(' /')[0]}님, 견적서는 내일까지 보내 드리겠습니다.\n{payload['signer']} 드림")


def _install(fake):
    app.dependency_overrides[get_ai_client] = lambda: fake
    return fake


def test_selected_mail_draft_is_masked_out_and_restored_back(client, db):
    _base(db)
    fake = _install(FakeAI({}))
    r = client.post("/api/agent/command", json={"text": "이거 회신 초안 써줘", "selected_mail_ids": [1]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "draft" and body["action"] == "T07" and body["title"] == "김민석 팀장님께 보낼 회신 초안입니다"
    assert body["draft"] == {"mail_id": 1, "to": "김민석 팀장", "subject": "RE: 견적 요청 1",
                             "text": "김민석 팀장님, 견적서는 내일까지 보내 드리겠습니다.\n이준호 드림"}
    sent = json.dumps(fake.drafts[0], ensure_ascii=False)
    for secret in ("김민석", "이준호", "minseok.kim", "010-1234-5678"):  # 개인정보 가리기(BE-6)
        assert secret not in sent
    assert fake.drafts[0]["kind"] == "reply" and fake.drafts[0]["tone"] == "polite"
    assert db.get(Task, 1).status == "pending"  # 초안은 아무것도 바꾸지 않는다


def test_sender_only_uses_latest_mail_even_without_open_task(client, db):
    # 보낸 사람만 말하면 업무와 관계없이 그 사람의 가장 최근 받은 메일(2번, 업무 없음) — 메일이 있는데 '없다'고 하지 않는다(#204 리뷰)
    _base(db)
    _install(FakeAI({"sender": "김 팀장"}))
    r = client.post("/api/agent/command", json={"text": "김 팀장 메일 회신 초안"}).json()
    assert r["kind"] == "draft" and r["draft"]["mail_id"] == 2
    assert any("김민석 팀장님의 가장 최근 메일" in x for x in r["notes"])


def test_two_people_match_asks(client, db):
    _base(db)
    db.add(Contact(user_id=1, email="seoyeon.kim@cne.com", name="김서연", position="팀장"))
    db.commit()
    fake = _install(FakeAI({"sender": "김 팀장"}))
    r = client.post("/api/agent/command", json={"text": "김 팀장 메일 회신 초안"}).json()
    assert r["kind"] == "ask" and r["title"].startswith("'김 팀장'에 맞는 분이 2명입니다") and fake.drafts == []


def test_task_based_filter_says_its_scope_when_empty(client, db):
    _base(db)
    db.get(Task, 1).status = "done"
    db.commit()
    fake = _install(FakeAI({"category": "회신"}))  # 분류 · 기간 조건은 끝나지 않은 업무가 있는 메일에서 찾는다
    r = client.post("/api/agent/command", json={"text": "회신 메일 초안"}).json()
    assert r["kind"] == "empty" and r["title"].startswith("끝나지 않은 업무가 있는 메일 중") and fake.drafts == []


def test_non_numeric_mail_id_asks_not_500(db):
    # API 경로는 PlanResult가 먼저 막는다. 실행기를 직접 부르는 곳(MCP 등)을 위한 방어 — 숫자 변환 줄만 감싼다(#204 리뷰)
    from app.agent import executor

    _base(db)
    fake = FakeAI({})
    r = executor.run(db, 1, {"action": "T07", "action_name": "회신_초안", "target": {"mail_ids": ["x"]}, "params": {}}, ai=fake)
    assert r.kind == "ask" and fake.drafts == []


@pytest.mark.parametrize(("payload", "target", "kind", "title"), [
    ({"selected_mail_ids": [1, 2]}, {}, "ask", "메일이 2통입니다. 회신 초안을 쓸 메일을 하나만 골라 주십시오"),
    ({}, {}, "ask", "회신 초안을 쓸 메일을 골라 주십시오"),  # 대상 조건 없음
    ({"selected_mail_ids": [3]}, {}, "empty", "회신 초안을 쓸 메일을 찾지 못했습니다"),  # 남의 메일
    ({}, {"sender": "박 상무"}, "empty", "회신 초안을 쓸 메일을 찾지 못했습니다"),
])
def test_ask_or_empty_without_calling_draft(client, db, payload, target, kind, title):
    _base(db)
    fake = _install(FakeAI(target))
    r = client.post("/api/agent/command", json={"text": "회신 초안 써줘", **payload}).json()
    assert (r["kind"], r["title"]) == (kind, title) and fake.drafts == []


def test_body_reading_off_sends_subject_only(client, db):
    _base(db)
    db.add(UserSettings(user_id=1, read_body=False))
    db.commit()
    fake = _install(FakeAI({}))
    client.post("/api/agent/command", json={"text": "이거 초안", "selected_mail_ids": [1]})
    assert fake.drafts[0]["mail"]["body"] == "" and fake.drafts[0]["mail"]["subject"] == "견적 요청 1"


def test_template_fallback_is_noted(client, db):
    _base(db)
    _install(FakeAI({}, source="template"))
    r = client.post("/api/agent/command", json={"text": "이거 초안", "selected_mail_ids": [1]}).json()
    assert r["kind"] == "draft" and "모델을 쓰지 못해 기본 문장으로 작성했습니다" in r["notes"]


def test_ai_down_during_draft_is_503(client, db):
    _base(db)
    _install(FakeAI({}, draft_error=AIError("unavailable", "down")))
    r = client.post("/api/agent/command", json={"text": "이거 초안", "selected_mail_ids": [1]})
    assert r.status_code == 503
