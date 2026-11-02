import json

import httpx
import pytest

from app.core.config import Settings
from app.llm.client import LlamaCppClient, LLMError, OllamaClient, build_client, parse_json


def make_client(handler):
    return OllamaClient(Settings(), transport=httpx.MockTransport(handler))


def test_chat_json_sends_bench_options():
    seen = {}

    def handler(req: httpx.Request):
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"message": {"content": '{"a": 1}'}})

    out = make_client(handler).chat_json("sys", "user", {"type": "object"})
    assert out == {"a": 1}
    assert seen["options"] == {"temperature": 0} and seen["stream"] is False and seen["think"] is False
    assert seen["format"] == {"type": "object"}
    assert seen["model"] == "hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:Q4_K_M"


def test_http_error_becomes_llm_error_without_body():
    def handler(req):
        return httpx.Response(500, text="secret mail body")

    with pytest.raises(LLMError) as e:
        make_client(handler).chat_text("s", "u")
    assert "secret" not in str(e.value)


def test_parse_json_strips_wrapping_text():
    assert parse_json('결과: {"x": "y"} 입니다') == {"x": "y"}
    with pytest.raises(LLMError):
        parse_json("그냥 문장")


def test_health_reports_model_ready():
    def handler(req):
        return httpx.Response(200, json={"models": [{"name": Settings().model}]})

    assert make_client(handler).health()["model_ready"] is True


def test_health_unreachable():
    def handler(req):
        raise httpx.ConnectError("down")

    assert make_client(handler).health() == {"reachable": False, "model_ready": False, "error": "ConnectError"}


def test_llamacpp_sends_schema_and_reads_choice():
    seen = {}

    def handler(req: httpx.Request):
        seen["path"] = req.url.path
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"a": 1}'}}]})

    out = LlamaCppClient(Settings(), transport=httpx.MockTransport(handler)).chat_json("sys", "user", {"type": "object"})
    assert out == {"a": 1} and seen["path"] == "/v1/chat/completions"
    assert seen["temperature"] == 0 and seen["stream"] is False
    assert seen["response_format"]["json_schema"]["schema"] == {"type": "object"}


def test_llamacpp_error_without_body():
    def handler(req):
        return httpx.Response(500, text="secret mail body")

    with pytest.raises(LLMError) as e:
        LlamaCppClient(Settings(), transport=httpx.MockTransport(handler)).chat_text("s", "u")
    assert "secret" not in str(e.value)


def test_llamacpp_health_loading():
    def handler(req):
        return httpx.Response(503, json={"error": {"message": "Loading model"}})

    h = LlamaCppClient(Settings(), transport=httpx.MockTransport(handler)).health()
    assert h["reachable"] is True and h["model_ready"] is False


def test_build_client_backend():
    assert isinstance(build_client(Settings(llm_backend="llamacpp")), LlamaCppClient)
    assert isinstance(build_client(Settings()), OllamaClient)


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["llm"]["model_ready"] is True


PINNED = Settings(model_digest="abc123", ollama_version="0.34.0")


def ollama_server(digest="abc123", version="0.34.0", chats=None):
    def handler(req: httpx.Request):
        if req.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": Settings().model, "digest": digest}]})
        if req.url.path == "/api/version":
            return httpx.Response(200, json={"version": version})
        if chats is not None:
            chats.append(req.url.path)
        return httpx.Response(200, json={"message": {"content": "ok"}})
    return handler


def test_pin_match_allows_call():
    chats = []
    c = OllamaClient(PINNED, transport=httpx.MockTransport(ollama_server(chats=chats)))
    assert c.chat_text("s", "u") == "ok" and c.chat_text("s", "u") == "ok"
    assert chats == ["/api/chat", "/api/chat"]  # 고정값 확인은 처음 한 번만


@pytest.mark.parametrize("server", [ollama_server(digest="other"), ollama_server(version="0.12.0")])
def test_pin_mismatch_blocks_call(server):
    c = OllamaClient(PINNED, transport=httpx.MockTransport(server))
    with pytest.raises(LLMError, match="고정값과 다름"):
        c.chat_text("s", "u")
    h = c.health()
    assert h["reachable"] is True and h["model_ready"] is False and h["pin_mismatch"]


def test_pin_rechecked_after_call_failure():
    state = {"digest": "abc123", "fail": False}

    def handler(req: httpx.Request):
        if req.url.path == "/api/chat" and state["fail"]:
            raise httpx.ConnectError("tunnel down")
        return ollama_server(digest=state["digest"])(req)

    c = OllamaClient(PINNED, transport=httpx.MockTransport(handler))
    assert c.chat_text("s", "u") == "ok"
    state["fail"] = True
    with pytest.raises(LLMError):
        c.chat_text("s", "u")
    state.update(fail=False, digest="swapped")  # 터널이 다시 붙었는데 PC 모델이 바뀐 경우
    with pytest.raises(LLMError, match="고정값과 다름"):
        c.chat_text("s", "u")


def test_uds_setting_uses_unix_socket_transport():
    c = OllamaClient(Settings(ollama_uds="/nonexistent/ollama.sock"))
    assert c.health() == {"reachable": False, "model_ready": False, "error": "ConnectError"}
