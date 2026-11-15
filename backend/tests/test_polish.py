"""답장 AI 다듬기 POST /api/mails/{id}/polish — 가려서 보내고 되돌려 준다. ai는 httpx 가짜 응답(INF-9)."""
import json
from datetime import datetime

import httpx
import pytest

from app.ai_client.client import AIClient, get_ai_client
from app.main import app
from app.models import Account, Contact, Mail, User, UserSettings

BODY = "이준호 팀장님, 견적서를 내일까지 회신 부탁드립니다.\n\n정태성 담당 / 010-1234-5678"
MINE = "정태성 담당님, 확인했습니다 내일 오후3시까지 보내드릴게요"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    src = tmp_path / "dummy.json"
    src.write_text(json.dumps({"mails": [{"mail": {"id": "M-1", "body": BODY}}]}), encoding="utf-8")
    monkeypatch.setenv("DUMMY_MAIL_SOURCE", str(src))
    yield
    app.dependency_overrides.clear()


def _base(db):
    db.add(User(id=1, name="이준호", position="팀장"))
    db.add(User(id=2, name="박서연"))
    db.flush()
    db.add(Account(id=1, user_id=1, provider="dummy", email="junho.lee@lgcns.example"))
    db.add(Account(id=2, user_id=2, provider="dummy", email="park@lgcns.example"))
    db.add(Contact(user_id=1, email="taesung.jung@lgcns.example", name="정태성"))
    db.flush()
    db.add(Mail(id=1, account_id=1, source_id="M-1", direction="received", sender="taesung.jung@lgcns.example",
                recipients=["junho.lee@lgcns.example"], subject="견적 회신 요청", sent_at=datetime(2026, 11, 11, 9, 0)))
    db.add(Mail(id=2, account_id=2, source_id="M-1", direction="received", sender="x@lgcns.example",
                recipients=["park@lgcns.example"], subject="남의 메일", sent_at=datetime(2026, 11, 11, 9, 0)))
    db.commit()


class FakeAI:
    def __init__(self, respond):
        self.seen, self.respond = [], respond

    def install(self):
        def handler(req: httpx.Request):
            body = json.loads(req.content)
            self.seen.append((req.url.path, body))
            return self.respond(body)
        app.dependency_overrides[get_ai_client] = lambda: AIClient("http://ai.test", transport=httpx.MockTransport(handler))
        return self


def _polished(body):  # 모델처럼: 가린 이름을 그대로 쓰고 문장만 고친다
    text = body["text"].replace("확인했습니다 내일 오후3시까지 보내드릴게요", "확인했습니다. 내일 오후 3시까지 보내 드리겠습니다.")
    return httpx.Response(200, json={"text": text, "style": body["style"], "changed": True, "source": "exaone",
                                     "prompt_version": "polish_v1"})


def test_polish_masks_what_goes_out_and_restores_what_comes_back(client, db):
    _base(db)
    fake = FakeAI(_polished).install()
    r = client.post("/api/mails/1/polish", json={"text": f"  {MINE}  ", "style": "polite"})
    assert r.status_code == 200
    assert r.json() == {"text": "정태성 담당님, 확인했습니다. 내일 오후 3시까지 보내 드리겠습니다.", "style": "polite",
                        "changed": True, "source": "exaone", "fallback": None}
    path, sent = fake.seen[0]
    out = json.dumps(sent, ensure_ascii=False)
    assert path == "/polish" and sent["style"] == "polite"
    for secret in ("정태성", "이준호", "taesung.jung", "010-1234-5678"):  # 개인정보 가리기(BE-6)
        assert secret not in out
    assert sent["text"] == "정◯◯ 담당님, 확인했습니다 내일 오후3시까지 보내드릴게요"  # 앞뒤 공백을 지움
    assert sent["mail"]["body"].startswith("이◯◯ 팀장님") and "[전화번호 1]" in sent["mail"]["body"]
    assert sent["mail"]["sender"].endswith("@lgcns.example")


def test_ai_could_not_polish_returns_my_text_with_reason(client, db):
    _base(db)
    FakeAI(lambda b: httpx.Response(200, json={"text": b["text"], "style": b["style"], "changed": False, "source": "none",
                                               "prompt_version": "polish_v1", "fallback": "받은 글에 없던 숫자 1개"})).install()
    r = client.post("/api/mails/1/polish", json={"text": MINE, "style": "concise"}).json()
    assert r == {"text": MINE, "style": "concise", "changed": False, "source": "none", "fallback": "받은 글에 없던 숫자 1개"}


def test_body_reading_off_sends_subject_only(client, db):
    _base(db)
    db.add(UserSettings(user_id=1, read_body=False))
    db.commit()
    fake = FakeAI(_polished).install()
    assert client.post("/api/mails/1/polish", json={"text": MINE, "style": "polite"}).status_code == 200
    assert fake.seen[0][1]["mail"]["body"] == "" and fake.seen[0][1]["mail"]["subject"] == "견적 회신 요청"


@pytest.mark.parametrize("mail_id", [2, 999])  # 남의 메일 · 없는 메일
def test_not_my_mail_is_404_and_ai_is_not_called(client, db, mail_id):
    _base(db)
    fake = FakeAI(_polished).install()
    assert client.post(f"/api/mails/{mail_id}/polish", json={"text": MINE, "style": "polite"}).status_code == 404
    assert fake.seen == []


def test_ai_down_is_503(client, db):
    _base(db)

    def down(_):
        raise httpx.ConnectError("refused")
    FakeAI(down).install()
    r = client.post("/api/mails/1/polish", json={"text": MINE, "style": "polite"})
    assert r.status_code == 503 and "다시 시도" in r.json()["detail"]


@pytest.mark.parametrize("body", [{"text": "   ", "style": "polite"}, {"text": MINE, "style": "funny"},
                                  {"text": MINE}, {"text": MINE, "style": "polite", "tone": "x"},
                                  {"text": "가" * 4001, "style": "polite"}])
def test_bad_request_is_422_and_ai_is_not_called(client, db, body):
    _base(db)
    fake = FakeAI(_polished).install()
    assert client.post("/api/mails/1/polish", json=body).status_code == 422
    assert fake.seen == []
