"""backend 외부 송신 허용 목록 · 기록(구조도 10절 · 시연 ⑧). backend가 밖으로 보내는 것은 ai 서비스 호출뿐이다."""
import httpx
import pytest

from app.ai_client.client import AIClient, AIError
from app.core import egress


@pytest.fixture(autouse=True)
def fresh():
    egress.reset()
    yield
    egress.reset()


def _ok(req: httpx.Request):
    return httpx.Response(200, json={"status": "ok"})


@pytest.mark.parametrize(("url", "kind"), [
    ("http://127.0.0.1:8001", "local"), ("http://localhost:8001", "local"), ("http://ai:8001", "local"),
    ("http://ai.railway.internal:8001", "local"), ("https://cne-ai.up.railway.app", "ai_service"),  # 공개 주소여도 우리 ai
])
def test_ai_service_calls_are_local_or_own_service(url, kind):
    AIClient(url, transport=httpx.MockTransport(_ok)).health()
    snap = egress.snapshot(url)
    assert snap[kind] == 1 and snap["blocked"] == 0


def test_other_external_host_is_blocked_before_sending(caplog):
    """ai 주소가 아닌 외부 호스트로는 보내지 않는다(허용 목록 밖). 연결 실패처럼 AIError."""
    sent: list = []
    hooks = egress.hooks("http://127.0.0.1:8001")  # 허용 목록: 없음(ai가 로컬)
    c = httpx.Client(base_url="https://api.example.com", transport=httpx.MockTransport(lambda r: sent.append(r) or _ok(r)),
                     event_hooks=hooks)
    with caplog.at_level("WARNING", logger="app.egress"), pytest.raises(egress.EgressBlocked):
        c.post("/x", json={"body": "비밀 본문"})
    assert sent == [] and egress.snapshot("http://127.0.0.1:8001")["blocked"] == 1
    assert "api.example.com" in caplog.text and "비밀 본문" not in caplog.text


def test_blocked_is_ai_error_for_callers():
    assert issubclass(egress.EgressBlocked, httpx.TransportError)  # ai_client는 TransportError를 AIError(unavailable)로
    c = AIClient("https://cne-ai.up.railway.app", transport=httpx.MockTransport(_ok))
    c._http.event_hooks = egress.hooks("http://127.0.0.1:8001")  # 설정과 다른 주소로 보내려는 상황
    with pytest.raises(AIError):
        c.classify({"mail_id": 1})
