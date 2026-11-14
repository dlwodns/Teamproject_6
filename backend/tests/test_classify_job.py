"""메일 분류 연결 (PL-16): 기억 → 분류 요청 → ai /classify → 업무 저장. ai는 httpx 가짜 응답으로 대신한다(INF-9)."""
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest

from app.ai_client.client import AIClient, get_ai_client
from app.ai_client.payload import build_classify_request
from tests.clock_util import move_to
from app.jobs import classify
from app.main import app
from app.jobs import worker
from app.models import Account, ClassifyJob, Contact, Mail, MailCheck, MailingList, Task, User, UserSettings

NOW = datetime(2026, 11, 11, 14, 0)
AI_DIR = Path(__file__).resolve().parents[2] / "ai"
BODY = "이준호 팀장님, 견적서를 내일까지 회신 부탁드립니다.\n\n정태성 담당"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    move_to(NOW)
    src = tmp_path / "dummy.json"
    src.write_text(json.dumps({"mails": [{"mail": {"id": "M-1", "body": BODY}},
                                         {"mail": {"id": "M-2", "body": "공유드립니다."}}]}), encoding="utf-8")
    monkeypatch.setenv("DUMMY_MAIL_SOURCE", str(src))
    yield
    move_to(None)
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
    # 개인정보 가리기(BE-6): 이름은 성만 남기고, 주소는 앞부분만 바꾸고 도메인은 남긴다. 같은 값은 같은 대체어
    assert "이준호" not in json.dumps(sent, ensure_ascii=False) and "taesung.jung" not in json.dumps(sent)
    assert sent["body"] == BODY.replace("이준호", "이◯1").replace("정태성", "정◯2")
    assert sent["from"].endswith("@lgcns.example") and sent["owner"]["name"] == "이◯1"
    assert sent["owner"]["email"] in sent["to"]  # '나에게 왔나' 판별이 그대로 된다
    assert sent["owner"]["position"] == "팀장" and sent["owner"]["team"] == "클라우드전환1팀"
    lists = sent["owner"]["role_lists"] + sent["owner"]["team_lists"]
    assert len(set(lists)) == 2 and set(lists) <= set(sent["owner"]["member_of"])
    assert all(a.endswith("@lgcns.example") and not a.startswith(("cloud", "all")) for a in sent["owner"]["member_of"])
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


def test_masked_names_in_ai_answer_are_restored_before_saving(client, db):
    """ai는 가린 글자로 답한다(할 일 · 근거 문장). 저장할 때는 원래 이름 · 주소로 되돌린다 — 근거 문장이 본문에 그대로 있어야
    형광펜(FE-5b)이 찾는다."""
    _base(db)
    classify.enqueue(db, db.get(Mail, 1))
    db.commit()

    def echo(body):  # 가린 주소 · 이름(이◯1)을 그대로 섞어 답한다
        return httpx.Response(200, json=_result(body["mail_id"], tasks=[{
            "type": "회신요청", "text": f"{body['from']}에게 견적서 회신", "due_raw": None, "due_at": None,
            "due_time_stated": False, "evidence": body["body"].splitlines()[0]}]))

    fake = FakeAI(echo)
    assert classify.run_next(db, fake.client())["status"] == "done"
    db.expire_all()
    t = db.query(Task).one()
    assert t.text == "taesung.jung@lgcns.example에게 견적서 회신"
    assert t.evidence_text == BODY.splitlines()[0] and t.evidence_text in BODY


def test_pii_mask_off_sends_original(client, db, monkeypatch):
    monkeypatch.setenv("PII_MASK", "0")
    _base(db)
    classify.enqueue(db, db.get(Mail, 1))
    db.commit()
    fake = FakeAI(_ok)
    classify.run_next(db, fake.client())
    assert fake.seen[0]["body"] == BODY and fake.seen[0]["from"] == "taesung.jung@lgcns.example"


def test_memory_change_while_queued_is_used(client, db):
    _base(db)
    classify.enqueue(db, db.get(Mail, 1))
    db.commit()
    client.patch("/api/agent/memory/people/5", json={"is_superior": False})  # 대기 중에 기억이 바뀜
    fake = FakeAI(_ok)
    classify.run_next(db, fake.client())
    assert fake.seen[0]["sender"]["is_superior"] is False


def _down(_):
    raise httpx.ConnectError("refused")


def test_ai_down_stays_queued_not_counted(client, db):
    # 구조도 12절 #17: ai 중지 → 작업은 queued로 남고 '분류 대기 N건'. 시도 횟수에 세지 않는다(#44 리뷰)
    _base(db)
    classify.enqueue(db, db.get(Mail, 1))
    db.commit()
    ai = FakeAI(_down).client()
    outs = [classify.run_next(db, ai) for _ in range(5)]
    assert {o["status"] for o in outs} == {"queued"} and {o["error"] for o in outs} == {"unavailable"}
    job = db.query(ClassifyJob).one()
    assert job.attempts == 0 and job.started_at is not None  # 마지막으로 꺼낸 시각(다음에 꺼낼 순서)
    assert client.get("/api/classify/status").json() == {"queued": 1, "running": 0, "done": 0, "failed": 0,
                                                         "rule_only": 0}
    assert db.query(Mail).count() == 4  # 메일은 남는다(누락 0)


def test_bad_response_counts_then_fails_and_retry(client, db):
    _base(db)
    classify.enqueue(db, db.get(Mail, 1))
    db.commit()
    ai = FakeAI(lambda b: httpx.Response(500, json={"detail": "x"})).client()
    assert [classify.run_next(db, ai)["status"] for _ in range(3)] == ["queued", "queued", "failed"]
    assert classify.run_next(db, ai) is None
    assert client.get("/api/classify/status").json()["failed"] == 1
    # [다시 시도]: failed → queued, 시도 횟수 0부터
    assert client.post("/api/classify/retry", json={}).json() == {"requeued": 1}
    job = db.query(ClassifyJob).one()
    db.refresh(job)
    assert job.status == "queued" and job.attempts == 0
    assert classify.run_next(db, FakeAI(_ok).client())["status"] == "done"


def test_worker_waits_after_failure(db, monkeypatch):
    # 실패 뒤에는 쉬고(False), 분류를 마쳤을 때만 바로 다음 작업(True). ai가 꺼져 있을 때 몇 ms 안에 거듭 부르지 않는다
    _base(db)
    classify.enqueue(db, db.get(Mail, 1))
    classify.enqueue(db, db.get(Mail, 2))
    db.commit()
    monkeypatch.setattr(worker, "SessionLocal", lambda: _Same(db))
    assert worker._tick(FakeAI(_down).client()) is False
    assert worker._tick(FakeAI(_ok).client()) is True
    assert worker._tick(FakeAI(_ok).client()) is True
    assert worker._tick(FakeAI(_ok).client()) is False  # 대기 작업 없음


class _Same:
    """작업자가 여는 세션 대신 시험 세션을 그대로 쓴다(닫지 않음)."""
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *a):
        return False


def test_fallback_saves_rule_result_and_marks_for_reclassify(client, db):
    # ai가 모델 실패로 규칙 결과만 내도 규칙이 찾은 할 일 · 확인 칸을 저장한다(source=rule). 엑사원 재분류 대상으로 표시
    _base(db)
    classify.enqueue(db, db.get(Mail, 1))
    classify.enqueue(db, db.get(Mail, 2))
    db.commit()
    rule = {"tasks": [{"text": "견적서 회신", "due_raw": "내일까지", "due_at": "2026-11-12T18:00:00"}],
            "source": "rule", "model": None, "prompt_version": None, "fallback": "timeout"}
    rule_check = {"tasks": [], "lane": "확인", "kind": "K12", "source": "rule", "model": None, "fallback": "timeout",
                  "checks": [{"text": "결과 공유 확인", "reason": "완료 보고", "source": "rule"}]}
    answers = {"1": rule, "2": rule_check}
    fake = FakeAI(lambda b: httpx.Response(200, json=_result(b["mail_id"], **answers[str(b["mail_id"])])))
    out = classify.run_next(db, fake.client())
    assert out["status"] == "done" and out["rule_only"] is True and out["tasks"] == 1
    classify.run_next(db, fake.client())
    t = db.query(Task).one()
    assert (t.source, t.due_source, t.text) == ("rule", "rule", "견적서 회신")
    c = db.query(MailCheck).one()
    assert (c.mail_id, c.reason, c.source) == (2, "완료 보고", "rule")
    assert db.get(Mail, 2).lane == "확인" and db.get(Mail, 2).kind == "K12"
    assert client.get("/api/classify/status").json() == {"queued": 0, "running": 0, "done": 2, "failed": 0,
                                                         "rule_only": 2}
    # 사용자가 1번 메일 업무를 완료 → 그 메일은 엑사원 결과로 바꾸지 않는다. 2번(손대지 않음)은 바꾼다
    r = client.patch(f"/api/tasks/{t.id}", json={"status": "done"})
    assert r.status_code == 200, r.text
    assert client.post("/api/classify/retry", json={"rule_only": True}).json() == {"requeued": 2}
    fake2 = FakeAI(_ok)
    classify.run_next(db, fake2.client())
    classify.run_next(db, fake2.client())
    db.expire_all()
    by_mail = {x.mail_id: x for x in db.query(Task)}
    assert by_mail[1].source == "rule" and by_mail[1].status == "done"
    assert by_mail[2].source == "exaone" and db.query(MailCheck).count() == 0
    assert db.get(Mail, 2).category_source == "exaone"
    assert client.get("/api/classify/status").json()["rule_only"] == 0


def test_saves_classify_columns(db):
    # #30 칸: mails.kind · lane, tasks.urgent · is_follow_up(업무마다 복사)
    _base(db)
    classify.enqueue(db, db.get(Mail, 1))
    db.commit()
    fake = FakeAI(lambda b: httpx.Response(200, json=_result(b["mail_id"], kind="K03", urgent=True,
                                                             is_follow_up=True)))
    classify.run_next(db, fake.client())
    m, t = db.get(Mail, 1), db.query(Task).one()
    assert (m.kind, m.lane, t.urgent, t.is_follow_up) == ("K03", "할 일", True, True)


def test_unexpected_error_does_not_leave_running(db, monkeypatch):
    # 본문 파일 오류 · 저장 실패 같은 AIError 밖 예외도 running으로 남기지 않는다(실패로 세고 다시 시도)
    _base(db)
    classify.enqueue(db, db.get(Mail, 1))
    db.commit()

    def broken(*_):
        raise OSError("본문 파일을 읽지 못함")
    monkeypatch.setattr(classify, "fetch_body", broken)
    out = classify.run_next(db, FakeAI(_ok).client())
    job = db.query(ClassifyJob).one()
    assert out["error"] == "error" and job.status == "queued" and job.attempts == 1 and "OSError" in job.error


def test_requeue_stale_running(db):
    _base(db)
    db.add(ClassifyJob(id=1, mail_id=1, status="running", started_at=NOW - timedelta(minutes=10)))
    db.add(ClassifyJob(id=2, mail_id=2, status="running", started_at=NOW - timedelta(seconds=30)))
    db.commit()
    assert classify.requeue_stale(db) == 1
    db.expire_all()
    assert db.get(ClassifyJob, 1).status == "queued" and db.get(ClassifyJob, 2).status == "running"


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


def test_timeout_mail_does_not_block_others(db):
    # 제한 시간 초과는 시도 횟수에 세지 않아 그 작업이 계속 queued로 남는다. 그 메일만 늘 느리면(긴 본문 등) 맨 앞에서
    # 계속 다시 꺼내져 뒤 메일이 영영 분류되지 않았다. 다시 꺼낼 때는 오래 기다린 작업부터 본다
    _base(db)
    classify.enqueue(db, db.get(Mail, 1))
    classify.enqueue(db, db.get(Mail, 2))
    db.commit()

    def slow_on_1(b):
        if str(b["mail_id"]) == "1":
            raise httpx.ReadTimeout("느림")
        return _ok(b)
    ai = FakeAI(slow_on_1).client()
    outs = [classify.run_next(db, ai) for _ in range(3)]
    assert [(o["mail_id"], o["status"]) for o in outs] == [(1, "queued"), (2, "done"), (1, "queued")]
    assert db.get(ClassifyJob, 1).attempts == 0  # 여전히 세지 않는다


def test_sender_flags_found_when_address_has_capitals(db):
    # 시드 · Outlook은 주소를 받은 그대로(대문자 섞임) 저장한다. 제안 카드는 소문자로 맞춰 찾는데, 분류 요청은 보낸 사람만
    # 소문자로 바꿔 글자 그대로 찾아서 상급자 표시가 ai에 가지 않았다
    _base(db)
    db.add(Contact(id=6, user_id=1, email="Sangwoo.Han@lgcns.example", name="한상우", is_superior=True))
    db.add(Mail(id=7, account_id=1, source_id="M-7", direction="received", sender="Sangwoo.Han@lgcns.example",
                recipients=["junho.lee@lgcns.example"], subject="보고", sent_at=NOW))
    db.commit()
    assert build_classify_request(db, db.get(Mail, 7), "")["sender"] == {"is_superior": True, "is_favorite": False}
