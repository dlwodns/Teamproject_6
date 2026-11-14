"""GET /api/mails/{id} — 메일 한 통 보기(#55 리뷰): 본문은 원본에서, 다른 사용자 메일은 404, 본문을 못 가져오면 503."""
import json
from datetime import datetime

import pytest

from app.models import Account, Mail, Task, User

BODY = "이준호 팀장님, 견적서를 내일까지 회신 부탁드립니다.\n\n정태성 담당"


@pytest.fixture(autouse=True)
def src(tmp_path, monkeypatch):
    path = tmp_path / "dummy.json"
    path.write_text(json.dumps({"mails": [{"mail": {"id": "M-1", "body": BODY}}]}), encoding="utf-8")
    monkeypatch.setenv("DUMMY_MAIL_SOURCE", str(path))


def _base(db):
    db.add_all([User(id=1, name="이준호"), User(id=2, name="다른 사용자")])
    db.flush()
    db.add_all([Account(id=1, user_id=1, provider="dummy", email="junho.lee@lgcns.example"),
                Account(id=2, user_id=2, provider="dummy", email="other@lgcns.example")])
    db.flush()
    at = datetime(2026, 10, 20, 9, 30)
    db.add_all([
        Mail(id=1, account_id=1, source_id="M-1", direction="received", sender="taesung.jung@lgcns.example",
             recipients=["junho.lee@lgcns.example"], cc=["cloud1@lgcns.example"], subject="견적 회신 요청", sent_at=at,
             category="회신", lane="할 일"),
        Mail(id=2, account_id=1, source_id="M-없음", direction="received", sender="x@lgcns.example", subject="원본 없음", sent_at=at),
        Mail(id=3, account_id=2, source_id="M-1", direction="received", sender="x@lgcns.example", subject="남의 메일", sent_at=at),
    ])
    db.flush()
    db.add_all([Task(id=10, mail_id=1, text="견적서 회신", due_raw="내일까지", due_at=datetime(2026, 10, 21, 18, 0),
                     due_source="model", evidence_text="견적서를 내일까지 회신 부탁드립니다."),
                Task(id=11, mail_id=1, text="이미 끝낸 일", status="done")])
    db.commit()


def test_mail_detail_has_body_and_tasks(client, db):
    _base(db)
    r = client.get("/api/mails/1")
    assert r.status_code == 200
    j = r.json()
    assert j["body"] == BODY and j["subject"] == "견적 회신 요청" and j["direction"] == "received"
    assert j["received_at"] == "2026-10-20T09:30:00+09:00"  # D47: +09:00
    assert j["to"] == ["junho.lee@lgcns.example"] and j["cc"] == ["cloud1@lgcns.example"]
    assert j["category"] == "회신" and j["lane"] == "할 일"
    assert [t["id"] for t in j["tasks"]] == [10, 11]  # 상태와 상관없이 이 메일의 업무 모두
    assert j["tasks"][0]["evidence_text"] == "견적서를 내일까지 회신 부탁드립니다."  # 본문에 그대로 있는 근거 문장
    assert j["tasks"][0]["evidence_text"] in j["body"]
    assert j["tasks"][0]["due_at"] == "2026-10-21T18:00:00+09:00"


def test_other_users_mail_and_missing_mail_are_404(client, db):
    _base(db)
    assert client.get("/api/mails/3").status_code == 404  # 다른 사용자 메일(같은 원본 id여도)
    assert client.get("/api/mails/3", headers={"X-User-Id": "2"}).status_code == 200
    assert client.get("/api/mails/999").status_code == 404
    assert client.get("/api/mails/0").status_code == 422


def test_body_not_found_is_503_not_empty(client, db):
    _base(db)
    r = client.get("/api/mails/2")
    assert r.status_code == 503  # 빈 본문을 보여 주지 않는다


def test_prod_mode_needs_user_header(client, db, monkeypatch):
    _base(db)
    monkeypatch.setenv("APP_MODE", "prod")  # 운영 모드: 화면이 X-User-Id를 붙여야 한다(FE #63 VITE_USER_ID)
    assert client.get("/api/mails/1").status_code == 401
    assert client.get("/api/mails/1", headers={"X-User-Id": "1"}).status_code == 200


def test_reply_polish_sends_notes_with_original_and_hides_others_mail(client, db):
    """11-15 [업무 문체로 다듬기]: 쓴 글 + 원 메일을 ai /draft로 보내고 다듬은 본문만 돌려준다. 남의 메일은 404, ai가 안 되면 503."""
    from app.ai_client.client import AIError, get_ai_client
    from app.main import app
    from app.schemas.ai import DraftResult

    sent = []

    class Fake:
        def draft(self, payload):
            sent.append(payload)
            if payload["topic"] == "boom":
                raise AIError("unavailable", "down")
            return DraftResult(subject="RE: 견적 회신 요청", body="내일까지 견적서를 송부드리겠습니다.", source="exaone")

    _base(db)
    app.dependency_overrides[get_ai_client] = lambda: Fake()
    try:
        r = client.post("/api/mails/1/reply-polish", json={"notes": "내일까지 보낼게요"})
        assert r.status_code == 200 and r.json() == {"body": "내일까지 견적서를 송부드리겠습니다.", "source": "exaone", "fallback": None}
        p = sent[0]
        assert p["kind"] == "reply" and p["topic"] == "내일까지 보낼게요" and p["mail"]["body"] == BODY and p["signer"] == "이준호"
        assert client.post("/api/mails/3/reply-polish", json={"notes": "x"}).status_code == 404
        assert client.post("/api/mails/1/reply-polish", json={"notes": ""}).status_code == 422
        assert client.post("/api/mails/1/reply-polish", json={"notes": "boom"}).status_code == 503
    finally:
        app.dependency_overrides.pop(get_ai_client, None)
