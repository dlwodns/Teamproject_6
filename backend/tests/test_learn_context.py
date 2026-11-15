"""문맥 기억(모델, BE-D21): 분류 뒤 ai /memory/extract → 연락처의 맡은 일 · 소속 → 제안 카드 · 에이전트가 아는 것.
엑사원 대신 httpx 가짜 응답(INF-9)."""
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.encoders import jsonable_encoder

from app.ai_client.client import AIClient
from tests.clock_util import move_to
from app.jobs import classify
from app.models import Account, ActionLog, Contact, ContactFact, Mail, User
from app.services import learn

NOW = datetime(2026, 11, 11, 14, 0)
AI_DIR = Path(__file__).resolve().parents[2] / "ai"
BODY = "안녕하세요, 금융사업팀 김민준 팀장입니다.\n저는 한빛은행 2단계 전환을 맡고 있습니다.\n견적 회신 부탁드립니다."
FACT = {"kind": "works_on", "value": "한빛은행 2단계 전환", "evidence": "저는 한빛은행 2단계 전환을 맡고 있습니다."}


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    move_to(NOW)
    src = tmp_path / "dummy.json"
    src.write_text(json.dumps({"mails": [{"mail": {"id": f"M-{i}", "body": BODY}} for i in (1, 2, 3)]}), encoding="utf-8")
    monkeypatch.setenv("DUMMY_MAIL_SOURCE", str(src))
    monkeypatch.setenv("MEMORY_EXTRACT", "1")
    yield
    move_to(None)


def _base(db):
    db.add(User(id=1, name="이준호", department="클라우드전환1팀", position="팀장"))
    db.flush()
    db.add(Account(id=1, user_id=1, provider="dummy", email="junho.lee@lgcns.example"))
    db.add(Contact(id=6, user_id=1, email="minjun.kim@lgcns.example", name="김민준", position="팀장"))
    db.flush()
    for i, sender in [(1, "minjun.kim@lgcns.example"), (2, "minho.jang@hanbitbank.example"),
                      (3, "minjun.kim@lgcns.example")]:
        db.add(Mail(id=i, account_id=1, source_id=f"M-{i}", direction="received", sender=sender,
                    recipients=["junho.lee@lgcns.example"], subject="견적", sent_at=NOW - timedelta(hours=1)))
        db.flush()
        classify.enqueue(db, db.get(Mail, i))
    db.commit()


class FakeAI:
    def __init__(self, facts=(FACT,), extract_status=200):
        self.paths, self.extract_bodies = [], []
        self.facts, self.extract_status = list(facts), extract_status

    def client(self) -> AIClient:
        def handler(req: httpx.Request):
            body = json.loads(req.content)
            self.paths.append(req.url.path)
            if req.url.path == "/classify":
                return httpx.Response(200, json={
                    "mail_id": str(body["mail_id"]), "category": "회신", "action_types": ["회신요청"],
                    "tasks": [{"text": "견적 회신", "due_at": "2026-11-11T18:00:00"}], "mentioned_me": True,
                    "urgent": False, "is_follow_up": False, "priority": "P2", "source": "exaone",
                    "rules_version": "conditions_v1"})
            self.extract_bodies.append(body)
            if self.extract_status != 200:
                return httpx.Response(self.extract_status)
            return httpx.Response(200, json={"mail_id": str(body["mail_id"]), "facts": self.facts, "source": "exaone",
                                             "model": "k-exaone_v2.5", "prompt_version": "memory_v1"})
        return AIClient("http://ai.test", transport=httpx.MockTransport(handler))


def test_switch_off_means_no_extract_call(db, monkeypatch):
    monkeypatch.setenv("MEMORY_EXTRACT", "")
    _base(db)
    fake = FakeAI()
    assert classify.run_next(db, fake.client())["status"] == "done"
    assert fake.paths == ["/classify"] and db.query(ContactFact).count() == 0


def test_facts_flow_to_memory_cards_and_history(client, db):
    _base(db)
    fake = FakeAI()
    out = classify.run_next(db, fake.client())
    assert out["status"] == "done" and out["learned"] == 1
    assert fake.paths == ["/classify", "/memory/extract"]
    sent = fake.extract_bodies[0]
    # 개인정보 가리기(BE-6): 보낸 사람 이름 · 주소 · 내 이름은 가려서 보내고, 근거 문장은 본문 그대로라 ai가 확인할 수 있다
    assert sent["sender_name"] == "김◯◯" and sent["body"] == BODY.replace("김민준", "김◯◯")
    assert sent["from"].endswith("@lgcns.example") and "minjun" not in sent["from"] and sent["owner"]["name"] == "이◯◯"
    assert sent["owner"]["position"] == "팀장"
    person = client.get("/api/agent/memory").json()["people"][0]
    assert person["facts"] == [{"kind": "works_on", "label": "맡은 일", "value": "한빛은행 2단계 전환",
                                "evidence": FACT["evidence"]}]
    assert person["used_by"] == ["제안 카드"] and person["origin"]["text"] == "11/11 메일에서 알게 됐어요"
    item = client.get("/api/actions/history").json()["items"][0]
    assert item["text"] == "메일에서 김민준님의 맡은 일(한빛은행 2단계 전환)을 알게 됐어요"
    assert item["via_label"] == "메일에서 알게 됨" and item["auto"] and item["can_undo"]
    card = client.get("/api/suggestions").json()["suggestions"][0]
    assert card["title"].startswith("김민준 팀장님(한빛은행 2단계 전환 담당) '견적 회신'")
    # 되돌리면 사라지고, 사용자가 거절한 것으로 보아 다음 메일에서 다시 배우지 않는다
    client.post(f"/api/actions/{item['action_id']}/undo")
    assert db.query(ContactFact).count() == 0
    classify.run_next(db, fake.client())  # 메일 2: 사외
    classify.run_next(db, fake.client())  # 메일 3: 같은 사람
    assert db.query(ContactFact).count() == 0 and fake.paths.count("/memory/extract") == 1


def test_external_sender_is_not_sent_to_extract(db):
    _base(db)
    fake = FakeAI()
    db.get(Mail, 1).sender = "x@other.example"
    db.commit()
    classify.run_next(db, fake.client())
    assert fake.paths == ["/classify"]


def test_extract_failure_keeps_classification(db):
    _base(db)
    fake = FakeAI(extract_status=500)
    out = classify.run_next(db, fake.client())
    assert out["status"] == "done" and out["learned"] == 0 and db.query(ContactFact).count() == 0
    assert db.query(ActionLog).count() == 0


def test_learn_setting_off_and_same_value(db):
    _base(db)
    learn.set_enabled(db, 1, False)
    db.commit()
    fake = FakeAI()
    classify.run_next(db, fake.client())
    assert fake.paths == ["/classify"]
    learn.set_enabled(db, 1, True)
    db.commit()
    classify.run_next(db, fake.client())  # 메일 2: 사외 → 안 부름
    classify.run_next(db, fake.client())  # 메일 3 → 배움
    assert db.query(ContactFact).count() == 1
    assert learn.learn_context(db, 1, db.get(Mail, 3), BODY, fake.client()) == []  # 같은 값이면 기록 없음


def test_user_can_edit_and_delete_facts(client, db):
    _base(db)
    classify.run_next(db, FakeAI(facts=[FACT, {"kind": "org", "value": "금융사업팀",
                                               "evidence": "안녕하세요, 금융사업팀 김민준 팀장입니다."}]).client())
    r = client.patch("/api/agent/memory/people/6", json={"facts": {"works_on": "한빛은행 3단계", "org": None}})
    assert r.status_code == 200
    facts = r.json()["memory"]["people"][0]["facts"]
    assert [(f["kind"], f["value"], f["evidence"]) for f in facts] == [("works_on", "한빛은행 3단계", None)]
    # 근거 문장은 기록 스냅숏에 남지 않는다: 화면에서 지우면 어디에도 없다(#44 리뷰)
    logs = json.dumps([[x.params_json, x.before_json] for x in db.query(ActionLog)], ensure_ascii=False)
    assert "김민준 팀장입니다" not in logs and FACT["evidence"] not in logs
    assert client.patch("/api/agent/memory/people/6", json={"facts": {"birthday": "5월"}}).status_code == 422
    assert client.patch("/api/agent/memory/people/6", json={"facts": {"org": "가" * 41}}).status_code == 422
    client.post(f"/api/actions/{r.json()['action_id']}/undo")
    facts = client.get("/api/agent/memory").json()["people"][0]["facts"]
    assert {f["kind"]: f["value"] for f in facts} == {"works_on": "한빛은행 2단계 전환", "org": "금융사업팀"}


def test_payload_matches_ai_contract(db):
    _base(db)
    fake = FakeAI()
    classify.run_next(db, fake.client())
    code = ("import sys, json; from app.schemas.memory import MemoryExtractRequest as R; "
            "R.model_validate(json.load(sys.stdin)); print('ok')")
    out = subprocess.run([sys.executable, "-c", code], cwd=AI_DIR, capture_output=True, text=True, timeout=60,
                         input=json.dumps(jsonable_encoder(fake.extract_bodies[0])))
    assert out.returncode == 0 and out.stdout.strip() == "ok", out.stderr
