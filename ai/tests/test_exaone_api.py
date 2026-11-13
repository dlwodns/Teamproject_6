"""엑사원 API 호출부(AI-22, D52). 실제 API는 부르지 않는다 — httpx.MockTransport가 API 자리에서 응답한다.

각 테스트는 '입력(설정 · API 응답) → 기대 결과' 한 쌍이다.
"""
import json

import httpx
import pytest

from app.core.config import Settings, check_settings, get_settings
from app.llm.client import (ExaoneApiClient, LlamaCppClient, LLMError, LLMQuotaError, OllamaClient, build_client)
from app.pipeline.classify import classify
from app.schemas.classify import ClassifyRequest, SenderFlags
from tests.test_review21 import OWNER

KEY = "test-key-not-real"
SETTINGS = Settings(exaone_api_key=KEY)


def ok(content='{"a": 1}', **usage):
    return httpx.Response(200, json={"choices": [{"message": {"content": content, "reasoning_content": "생각"}, "finish_reason": "stop"}],
                                     "usage": {"prompt_tokens": 900, "completion_tokens": 700, "reasoning_tokens": 500, **usage}},
                          headers={"x-day-rate-limit": "100", "x-day-rate-limit-remaining": "57"})


def client(handler, settings=SETTINGS, sleeps=None):
    return ExaoneApiClient(settings, transport=httpx.MockTransport(handler),
                           sleep=(sleeps.append if sleeps is not None else lambda s: None))


# --- 설정값 하나로 바꿔 끼우기 ---------------------------------------------------------------

@pytest.mark.parametrize("value, cls", [(None, ExaoneApiClient), ("exaone_api", ExaoneApiClient),
                                        ("ollama", OllamaClient), ("llamacpp", LlamaCppClient),
                                        ("ollama   # 로컬", OllamaClient)])
def test_backend_switch_by_env(monkeypatch, value, cls):
    """입력: LLM_BACKEND만 바꾼다(없음 · exaone_api · ollama · llamacpp · 주석 붙은 값) → 기대: 그 실행기가 만들어진다. 기본은 API."""
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    if value is not None:
        monkeypatch.setenv("LLM_BACKEND", value)
    assert isinstance(build_client(get_settings()), cls)
    assert check_settings() == []


def test_api_model_separate_from_local_model(monkeypatch):
    """입력: .env에 로컬 모델 이름(EXAONE_MODEL)만 있다 → 기대: API는 k-exaone_v2.5를 부른다(이름이 섞이지 않는다)."""
    monkeypatch.setenv("EXAONE_MODEL", "hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:Q4_K_M")
    monkeypatch.delenv("EXAONE_API_MODEL", raising=False)
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    assert build_client(get_settings()).model == "k-exaone_v2.5"


def test_bad_reasoning_effort_rejected(monkeypatch):
    """입력: EXAONE_REASONING_EFFORT=fast → 기대: 설정 오류(서비스가 뜨지 않는다)."""
    monkeypatch.setenv("EXAONE_REASONING_EFFORT", "fast")
    assert [e.split("=")[0] for e in check_settings()] == ["EXAONE_REASONING_EFFORT"]


# --- 요청 모양 ---------------------------------------------------------------------------------

def test_request_shape():
    """입력: 스키마를 준 chat_json → 기대: 문서 주소 · Bearer 키 · temperature 0 · 상한 4096 · strict 스키마, 추론 강도는 보내지 않음(기본 max)."""
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["auth"] = str(req.url), req.headers["authorization"]
        seen.update(json.loads(req.content))
        return ok()

    c = client(handler)
    assert c.chat_json("sys", "user", {"type": "object", "properties": {"x": {"type": "object"}}}) == {"a": 1}
    assert seen["url"] == "https://api.exaone.ai/v1/chat/completions" and seen["auth"] == f"Bearer {KEY}"
    assert seen["model"] == "k-exaone_v2.5" and seen["temperature"] == 0 and seen["max_tokens"] == 4096 and seen["stream"] is False
    assert "reasoning_effort" not in seen
    sch = seen["response_format"]["json_schema"]
    assert sch["strict"] is True and sch["schema"]["additionalProperties"] is False
    assert sch["schema"]["properties"]["x"]["additionalProperties"] is False
    assert c.last_stats == {"prompt_tokens": 900, "gen_tokens": 700, "reasoning_tokens": 500, "cost": 0.0}
    assert c.day_limit == {"limit": "100", "remaining": "57"}


def test_reasoning_effort_sent_when_set():
    """입력: 추론 강도 low → 기대: 요청에 reasoning_effort low."""
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return ok()

    client(handler, Settings(exaone_api_key=KEY, exaone_reasoning_effort="low")).chat_text("s", "u")
    assert seen["reasoning_effort"] == "low" and "response_format" not in seen


def test_leading_newline_trimmed():
    """입력: 답 앞에 줄바꿈("\\n\\n안녕") → 기대: '안녕'(문서: content 앞에 줄바꿈이 붙을 수 있다)."""
    assert client(lambda r: ok("\n\n안녕")).chat_text("s", "u") == "안녕"


# --- 실패 처리 --------------------------------------------------------------------------------

def test_no_key_fails_without_calling():
    """입력: 키 없음 → 기대: API를 부르지 않고 LLMError, health는 준비 안 됨 · 이유 '키 없음'."""
    called = []
    c = client(lambda r: called.append(1) or ok(), Settings())
    with pytest.raises(LLMError, match="EXAONE_API_KEY 없음"):
        c.chat_json("s", "u", {"type": "object"})
    assert not called
    h = c.health()
    assert h["model_ready"] is False and h["error"] == "EXAONE_API_KEY 없음"


def test_day_quota_exhausted_stops():
    """입력: 429 + 하루 남은 횟수 0 → 기대: 다시 부르지 않고 LLMQuotaError(LLMError의 한 종류라 서비스는 규칙 결과로 대신)."""
    calls = []

    def handler(req):
        calls.append(1)
        return httpx.Response(429, headers={"x-day-rate-limit": "100", "x-day-rate-limit-remaining": "0"})

    c = client(handler)
    with pytest.raises(LLMQuotaError):
        c.chat_json("s", "u", {"type": "object"})
    assert len(calls) == 1 and c.health()["model_ready"] is False and c.health()["error"] == "하루 호출 한도 소진"


def test_busy_429_retried_then_ok():
    """입력: 서버 혼잡 429(하루 한도는 남음, retry-after 2) 두 번 뒤 200 → 기대: 2초씩 쉬고 세 번째에 결과."""
    replies = [httpx.Response(429, headers={"retry-after": "2", "x-day-rate-limit-remaining": "40"}),
               httpx.Response(503), ok()]
    sleeps = []
    c = client(lambda r: replies.pop(0), sleeps=sleeps)
    assert c.chat_json("s", "u", {"type": "object"}) == {"a": 1}
    assert sleeps == [2.0, 6.0] and c.retries == 2


def test_busy_429_gives_up_after_three():
    """입력: 혼잡 429만 계속 → 기대: 세 번 다시 부른 뒤 LLMError(한도 소진으로 보지 않음)."""
    c = client(lambda r: httpx.Response(429, headers={"x-day-rate-limit-remaining": "40"}))
    with pytest.raises(LLMError, match="HTTP 429") as e:
        c.chat_text("s", "u")
    assert not isinstance(e.value, LLMQuotaError) and c.retries == 3


def test_retry_never_passes_timeout():
    """입력: 제한 시간 5초인데 retry-after 30 → 기대: 기다리지 않고 바로 실패(backend 130초 안에 끝나게)."""
    sleeps = []
    c = client(lambda r: httpx.Response(503, headers={"retry-after": "30"}),
               Settings(exaone_api_key=KEY, llm_timeout_s=5), sleeps=sleeps)
    with pytest.raises(LLMError):
        c.chat_text("s", "u")
    assert sleeps == []


def test_schema_rejected_falls_back_once():
    """입력: 스키마 강제에 400 → 기대: 강제 없이 다시 불러 앞뒤 글이 붙은 JSON도 꺼내고, 다음 호출부터는 처음부터 강제 없이."""
    bodies = []

    def handler(req):
        b = json.loads(req.content)
        bodies.append("response_format" in b)
        return httpx.Response(400, json={"result_code": 400}) if "response_format" in b else ok('결과: {"a": 2} 입니다')

    c = client(handler)
    assert c.chat_json("s", "u", {"type": "object"}) == {"a": 2}
    assert c.chat_json("s", "u", {"type": "object"}) == {"a": 2}
    assert bodies == [True, False, False]


@pytest.mark.parametrize("resp, msg", [
    (httpx.Response(401, text="secret mail body"), "키 거절"),
    (httpx.Response(500, text="secret mail body"), "HTTP 500"),
    (httpx.Response(200, json={"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}), "빈 응답: finish=length"),
    (httpx.Response(200, json={"oops": 1}), "응답 형식 오류"),
])
def test_errors_without_body_or_key(resp, msg):
    """입력: 401 · 500(본문에 메일 글자) · 빈 답(상한에 걸림) · 형식 다른 응답 → 기대: LLMError, 메시지에 본문 · 키가 없다."""
    with pytest.raises(LLMError, match=msg) as e:
        client(lambda r: resp).chat_text("s", "u")
    assert "secret" not in str(e.value) and KEY not in str(e.value)


def test_connection_error():
    """입력: 연결 끊김 → 기대: LLMError('ConnectError')."""
    def handler(req):
        raise httpx.ConnectError("down")

    with pytest.raises(LLMError, match="ConnectError"):
        client(handler).chat_text("s", "u")


def test_health_does_not_call_api():
    """입력: 키 있음 · health → 기대: API를 부르지 않고(한도 아낌) 준비됨."""
    called = []
    h = client(lambda r: called.append(1) or ok()).health()
    assert not called and h["model_ready"] is True and h["backend"] == "exaone_api"


# --- 파이프라인에 그대로 꽂힌다 ----------------------------------------------------------------

def test_classify_raises_on_quota():
    """입력: 분류 중 하루 한도 소진 → 기대: 규칙으로 메우지 않고 LLMQuotaError가 올라간다(backend가 한도가 풀린 뒤 다시 부른다, AI-D19)."""
    c = client(lambda r: httpx.Response(429, headers={"x-day-rate-limit-remaining": "0"}))
    req = ClassifyRequest(**{"from": "a@corp.example"}, mail_id="m1", to=[OWNER.email], cc=[], subject="자료 요청",
                          body="금요일까지 보고서 보내 주세요.", attachments=[], received_at="2026-11-13T09:00",
                          owner=OWNER, sender=SenderFlags())
    with pytest.raises(LLMQuotaError):
        classify(req, c, Settings(exaone_api_key=KEY))
