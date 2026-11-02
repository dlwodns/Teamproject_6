import json

import httpx
import pytest

from app.core.config import Settings
from app.llm.client import LLMError, OllamaClient, parse_json


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


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok" and r.json()["llm"]["model_ready"] is True
