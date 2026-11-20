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
    assert second == {"text": KO, "lang": "en", "source": "saved", "fallback": None}
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
