"""메일 번역 POST /api/mails/{id}/translate (AI-32): 누를 때만 ai를 한 번 부르고 저장, 다시 누르면 저장한 것. ai는 httpx 가짜 응답."""
import httpx

from app.ai_client.client import AIClient, get_ai_client
from app.main import app
from app.models import Mail
from tests.test_classify_job import _base, env  # noqa: F401  같은 메일함 · 더미 본문

KO = "견적서를 내일까지 회신 부탁드립니다."


def _ai(calls, respond):
    def handler(req: httpx.Request):
        calls.append(req.url.path)
        return respond(req)
    return AIClient("http://ai.test", transport=httpx.MockTransport(handler))


def test_translate_once_then_saved(client, db):
    _base(db)
    calls = []
    ok = {"text": KO, "lang": "en", "source": "exaone", "prompt_version": "translate_v1", "fallback": None}
    app.dependency_overrides[get_ai_client] = lambda: _ai(calls, lambda r: httpx.Response(200, json=ok))
    first = client.post("/api/mails/1/translate").json()
    second = client.post("/api/mails/1/translate").json()
    assert first["text"] == KO and first["source"] == "exaone"
    assert second == {"text": KO, "lang": "en", "source": "saved", "fallback": None, "truncated": False}
    assert calls == ["/translate"]  # 두 번째는 부르지 않는다
    assert db.get(Mail, 1).translation["text"] == KO


def test_not_translated_is_not_saved(client, db):
    _base(db)
    calls = []
    no = {"text": "", "lang": "ko", "source": "none", "prompt_version": "translate_v1", "fallback": "이미 한국어"}
    app.dependency_overrides[get_ai_client] = lambda: _ai(calls, lambda r: httpx.Response(200, json=no))
    assert client.post("/api/mails/1/translate").json()["fallback"] == "이미 한국어"
    db.expire_all()
    assert db.get(Mail, 1).translation is None
    app.dependency_overrides[get_ai_client] = lambda: _ai(calls, lambda r: httpx.Response(503))
    assert client.post("/api/mails/1/translate").status_code == 503


def test_read_body_off_hides_and_clears_saved_translation(client, db):
    _base(db)
    calls = []
    ok = {"text": KO, "lang": "en", "source": "exaone", "prompt_version": "translate_v1", "fallback": None}
    app.dependency_overrides[get_ai_client] = lambda: _ai(calls, lambda r: httpx.Response(200, json=ok))
    client.post("/api/mails/1/translate")
    assert client.patch("/api/settings", json={"read_body": False}).status_code == 200
    db.expire_all()
    assert db.get(Mail, 1).translation is None  # 끄는 순간 지운다
    r = client.post("/api/mails/1/translate").json()
    assert r["source"] == "none" and r["text"] == ""


# ---- [요약] POST /api/mails/{id}/summary (AI-45) ----

REPLY = ("네, 견적서는 금요일까지 다시 보내 드리겠습니다. 단가표도 함께 첨부하겠습니다.\n\n"
         "From: 김민수 <minsu@example.com>\n계약서 초안을 월요일까지 검토해 주세요.")
SUM = {"text": "견적서를 금요일까지 다시 보낸다.", "source": "exaone", "prompt_version": "assist_v4", "fallback": None,
       "mail_summary": {"lang": "ko", "gist": "견적서를 금요일까지 다시 보낸다.", "asks": [], "due_text": "금요일까지"}}


def test_summary_once_without_quoted_mail_then_saved(client, db, monkeypatch):
    _base(db)
    db.get(Mail, 1).summary = None
    db.commit()
    sent = []
    monkeypatch.setattr("app.api.translate.fetch_body", lambda db, mail: REPLY)
    app.dependency_overrides[get_ai_client] = lambda: _ai(sent, lambda r: (sent.append(r.read().decode()), httpx.Response(200, json=SUM))[1])
    first = client.post("/api/mails/1/summary").json()
    second = client.post("/api/mails/1/summary").json()
    assert first == second == SUM["mail_summary"]
    assert sent[0] == "/summarize" and len(sent) == 2  # 두 번째는 저장한 것(부르지 않음)
    assert "견적서" in sent[1] and "계약서 초안" not in sent[1]  # 인용된 앞 메일은 보내지 않는다
    db.expire_all()
    assert db.get(Mail, 1).summary["gist"] == SUM["mail_summary"]["gist"]


def test_summary_none_or_ai_down(client, db, monkeypatch):
    _base(db)
    db.get(Mail, 1).summary = None
    db.commit()
    monkeypatch.setattr("app.api.translate.fetch_body", lambda db, mail: REPLY)
    none = {**SUM, "text": "", "mail_summary": None, "fallback": "모델 실패"}
    app.dependency_overrides[get_ai_client] = lambda: _ai([], lambda r: httpx.Response(200, json=none))
    r = client.post("/api/mails/1/summary")
    assert r.status_code == 200 and r.json() is None
    app.dependency_overrides[get_ai_client] = lambda: _ai([], lambda r: httpx.Response(503))
    assert client.post("/api/mails/1/summary").status_code == 503
    assert client.post("/api/mails/999/summary").status_code == 404
