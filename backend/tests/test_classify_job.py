"""메일 분류 연결 (PL-16): 기억 → 분류 요청 → ai /classify → 업무 저장. ai는 httpx 가짜 응답으로 대신한다(INF-9)."""
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest

from app.ai_client.client import AIClient, get_ai_client
from app.ai_client.payload import build_classify_request
from app.core import clock
from app.jobs import classify
from app.main import app
from app.models import Account, ClassifyJob, Contact, Mail, MailingList, Task, User, UserSettings

NOW = datetime(2026, 11, 11, 14, 0)
AI_DIR = Path(__file__).resolve().parents[2] / "ai"
BODY = "이준호 팀장님, 견적서를 내일까지 회신 부탁드립니다.\n\n정태성 담당"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    clock.set_dev_now(NOW)
    src = tmp_path / "dummy.json"
    src.write_text(json.dumps({"mails": [{"mail": {"id": "M-1", "body": BODY}},
                                         {"mail": {"id": "M-2", "body": "공유드립니다."}}]}), encoding="utf-8")
    monkeypatch.setenv("DUMMY_MAIL_SOURCE", str(src))
    yield
    clock.set_dev_now(None)
    app.dependency_overrides.clear()


def _base(db):
    db.add(User(id=1, name="이준호", department="클라우드전환1팀", position="팀장"))
    db.flush()
    db.add(Account(id=1, user_id=1, provider="dummy", email="junho.lee@lgcns.example"))
    db.add(Contact(id=5, user_id=1, email="taesung.jung@lgcns.example", name="정태성", position="담당", is_superior=True))
    db.add(MailingList(user_id=1, address="cloud-leaders@lgcns.example", kind="role"))
    db.add(MailingList(user_id=1, address="cloud1@lgcns.example", kind="team"))
    db.add(MailingList(user_id=1, address="all@lgcns.example", kind="all"))
    db.flush()
    for i, (sender, direction) in enumerate([("taesung.jung@lgcns.example", "received"),
                                             ("x@lgcns.example", "received"),
                                             ("junho.lee@lgcns.example", "sent"),
                                             ("noreply@lgcns.example", "received")], 1):
        db.add(Mail(id=i, account_id=1, source_id=f"M-{i}", direction=direction, sender=sender,
                    recipients=["junho.lee@lgcns.example"], subject="견적 회신 요청", sent_at=NOW - timedelta(hours=3)))
    db.commit()


def _result(mail_id, **kw):
    out = {"mail_id": str(mail_id), "category": "회신", "action_types": ["회신요청"],
           "tasks": [{"type": "회신요청", "text": "견적서 회신", "due_raw": "내일까지", "due_at": "2026-11-12T18:00:00",
                      "due_time_stated": False, "evidence": "견적서를 내일까지 회신 부탁드립니다."}],
           "checks": [], "lane": "할 일", "mentioned_me": True, "urgent": False, "is_follow_up": False,
           "priority": "P1", "source": "exaone", "confidence": None, "model": "k-exaone_v2.5",
           "prompt_version": "classify_v7", "rules_version": "conditions_v1", "fallback": None}
    out.update(kw)
    return out


class FakeAI:
    def __init__(self, respond):
        self.seen = []
        self.respond = respond

    def client(self) -> AIClient:
        def handler(req: httpx.Request):
            body = json.loads(req.content)
            self.seen.append(body)
            return self.respond(body)
        return AIClient("http://ai.test", transport=httpx.MockTransport(handler))


def _ok(body):
    return httpx.Response(200, json=_result(body["mail_id"]))


def test_enqueue_filters(db):
    _base(db)
    got = [classify.enqueue(db, db.get(Mail, i)) for i in (1, 2, 3, 4, 1)]
    db.commit()
    assert [j is not None for j in got] == [True, True, False, False, False]  # 보낸 메일 · noreply · 중복 제외


def test_run_next_sends_memory_and_saves_tasks(client, db):
    _base(db)
    classify.enqueue(db, db.get(Mail, 1))
    db.commit()
    fake = FakeAI(_ok)
    out = classify.run_next(db, fake.client())
    assert out["status"] == "done" and out["tasks"] == 1
    sent = fake.seen[0]
    assert sent["body"] == BODY and sent["from"] == "taesung.jung@lgcns.example"
    assert sent["owner"]["position"] == "팀장" and sent["owner"]["team"] == "클라우드전환1팀"
    assert sent["owner"]["role_lists"] == ["cloud-leaders@lgcns.example"]
    assert sent["owner"]["team_lists"] == ["cloud1@lgcns.example"]
    assert sorted(sent["owner"]["member_of"]) == ["all@lgcns.example", "cloud-leaders@lgcns.example",
                                                  "cloud1@lgcns.example"]
    assert sent["sender"] == {"is_superior": True, "is_favorite": False}
    db.expire_all()
    t = db.query(Task).one()
    assert (t.text, t.due_raw, t.due_source, t.priority, t.mentioned_me, t.source) == \
        ("견적서 회신", "내일까지", "model", "P1", True, "exaone")
    assert t.evidence_text.startswith("견적서를") and t.due_at == datetime(2026, 11, 12, 18, 0)
    assert db.get(Mail, 1).category == "회신"
    job = db.query(ClassifyJob).one()
    assert (job.status, job.model, job.prompt_version) == ("done", "k-exaone_v2.5", "classify_v7")
    # 분류 결과가 바로 제안 카드로 이어진다(기한은 28시간 뒤라 임박이 아니고, 상급자 메일 3시간 경과)
    cards = client.get("/api/suggestions").json()["suggestions"]
    assert [c["rule"] for c in cards] == ["priority_sender"]
    assert cards[0]["title"] == "정태성 담당님 메일을 받은 지 3시간 지났어요."


def test_memory_change_while_queued_is_used(client, db):
    _base(db)
    classify.enqueue(db, db.get(Mail, 1))
    db.commit()
    client.patch("/api/agent/memory/people/5", json={"is_superior": False})  # 대기 중에 기억이 바뀜
    fake = FakeAI(_ok)
    classify.run_next(db, fake.client())
    assert fake.seen[0]["sender"]["is_superior"] is False


def test_ai_down_retries_then_fails_and_is_counted(client, db):
    _base(db)
    classify.enqueue(db, db.get(Mail, 1))
    db.commit()

    def down(_):
        raise httpx.ConnectError("refused")
    ai = FakeAI(down).client()
    assert [classify.run_next(db, ai)["status"] for _ in range(3)] == ["queued", "queued", "failed"]
    assert classify.run_next(db, ai) is None
    assert client.get("/api/classify/status").json() == {"queued": 0, "running": 0, "done": 0, "failed": 1}
    assert db.query(Task).count() == 0 and db.query(Mail).count() == 4  # 메일은 남는다(누락 0)


def test_fallback_result_is_retried_not_saved(db):
    _base(db)
    classify.enqueue(db, db.get(Mail, 1))
    db.commit()
    fake = FakeAI(lambda b: httpx.Response(200, json=_result(b["mail_id"], tasks=[], source="rule",
                                                             fallback="timeout")))
    out = classify.run_next(db, fake.client())
    assert out["status"] == "queued" and out["error"] == "fallback" and db.query(Task).count() == 0


def test_read_body_off_and_body_unavailable(db):
    _base(db)
    db.add(UserSettings(user_id=1, read_body=False))
    db.add(Mail(id=9, account_id=1, source_id="M-없음", direction="received", sender="a@lgcns.example",
                subject="s", sent_at=NOW))
    db.commit()
    classify.enqueue(db, db.get(Mail, 1))
    db.commit()
    fake = FakeAI(_ok)
    classify.run_next(db, fake.client())
    assert fake.seen[0]["body"] == ""  # 본문 읽기 꺼짐
    db.get(UserSettings, 1).read_body = True
    classify.enqueue(db, db.get(Mail, 9))
    db.commit()
    out = classify.run_next(db, fake.client())
    assert out["error"] == "body_unavailable" and out["status"] == "queued" and len(fake.seen) == 1


def test_existing_tasks_are_not_duplicated(db):
    _base(db)
    db.add(Task(mail_id=1, text="이미 있는 업무", status="done"))
    classify.enqueue(db, db.get(Mail, 1))
    db.commit()
    classify.run_next(db, FakeAI(_ok).client())
    assert [t.text for t in db.query(Task)] == ["이미 있는 업무"]


def test_wrong_mail_id_is_bad_response(db):
    _base(db)
    classify.enqueue(db, db.get(Mail, 1))
    db.commit()
    out = classify.run_next(db, FakeAI(lambda b: httpx.Response(200, json=_result(999))).client())
    assert out["error"] == "bad_response" and db.query(Task).count() == 0


def test_requeue_running_on_start(db):
    _base(db)
    db.add(ClassifyJob(mail_id=1, status="running"))
    db.commit()
    assert classify.requeue_running(db) == 1 and db.query(ClassifyJob).one().status == "queued"


def test_dev_endpoints(client, db, monkeypatch):
    _base(db)
    fake = FakeAI(_ok)
    app.dependency_overrides[get_ai_client] = fake.client
    assert client.post("/api/dev/classify/enqueue", json={}).json() == {"enqueued": 2}
    r = client.post("/api/dev/classify/run?limit=5").json()["results"]
    assert [x["status"] for x in r] == ["done", "done"]
    monkeypatch.setenv("APP_MODE", "prod")
    assert client.post("/api/dev/classify/run", headers={"X-User-Id": "1"}).status_code == 404


def test_payload_matches_ai_contract(db):
    """만든 요청이 ai 쪽 ClassifyRequest로 읽히고, ai가 받는 owner · sender 칸을 모두 채우는지(backend는 ai를 import하지 않아
    ai 폴더에서 따로 띄운 파이썬으로 확인한다, D34)."""
    _base(db)
    payload = build_classify_request(db, db.get(Mail, 1), BODY)
    code = ("import sys, json; from app.schemas.classify import ClassifyRequest as R, OwnerProfile as O, SenderFlags as S;"
            "d = json.load(sys.stdin); R.model_validate(d);"
            "print(json.dumps({'owner': sorted(set(O.model_fields) - set(d['owner'])),"
            " 'sender': sorted(set(S.model_fields) - set(d['sender']))}))")
    from fastapi.encoders import jsonable_encoder

    import sys as _sys
    out = subprocess.run([_sys.executable, "-c", code], cwd=AI_DIR, input=json.dumps(jsonable_encoder(payload)),
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == {"owner": [], "sender": []}  # ai가 받는 칸 중 빠진 것 없음
