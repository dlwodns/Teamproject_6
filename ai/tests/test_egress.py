"""외부 송신 허용 목록 · 송신 기록 (구조도 10절 · 12절 #19 · 시연 ⑧ "로컬 모드면 외부 LLM 호출 0건").
실제 서버는 부르지 않는다 — httpx.MockTransport가 자리에서 응답하고, event hook은 그대로 돈다."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import llm_dep
from app.core import egress
from app.core.config import Settings
from app.llm.client import ExaoneApiClient, LLMError, OllamaClient
from app.main import app

OLLAMA = Settings(llm_backend="ollama")
API = Settings(exaone_api_key="test-key-not-real")  # 기본 llm_backend = exaone_api


@pytest.fixture(autouse=True)
def fresh():
    egress.reset()
    yield
    egress.reset()
    app.dependency_overrides.clear()


@pytest.mark.parametrize(("host", "local"), [
    ("localhost", True), ("127.0.0.1", True), ("::1", True), ("ai.railway.internal", True), ("ollama", True), ("ai", True),
    ("app.localhost", True), ("api.exaone.ai", False), ("api.example.com", False),
    # 사설망 · 공인 IP 판정 — 문서용 예시 주소(실제 서버 주소 아님)
    ("10.1.2.3", True), ("172.20.1.5", True), ("192.168.0.9", True),  # boundary-ok
    ("1.1.1.1", False), ("172.32.0.1", False),  # boundary-ok
])
def test_is_local(host, local):
    assert egress.is_local(host) is local


def test_allow_list_comes_from_settings():
    assert egress.allowed_hosts(API) == {"api.exaone.ai"}  # 엑사원 API 모드(D53)
    assert egress.allowed_hosts(OLLAMA) == frozenset()  # 로컬 모드: 외부 허용 없음
    assert egress.allowed_hosts(Settings(exaone_api_base_url="http://127.0.0.1:9000/v1")) == frozenset()  # 로컬 중계


def _ollama_handler(calls):
    def handler(req: httpx.Request):
        calls.append(req.url.host)
        content = json.dumps({"action": None, "reason": "unsupported", "text": "다듬은 글", "subject": "RE: 확인",
                              "body": "확인했습니다."}, ensure_ascii=False)
        return httpx.Response(200, json={"message": {"content": content}, "done": True})
    return handler


def test_local_mode_whole_service_path_has_zero_external_calls():
    """구조도 12절 #19: 로컬 모드로 서비스 경로(분류 · 명령 해석 · 초안 · 다듬기 · 메일 요약)를 돌려도 외부 송신 0건."""
    calls: list[str] = []
    llm = OllamaClient(OLLAMA, transport=httpx.MockTransport(_ollama_handler(calls)))
    app.dependency_overrides[llm_dep] = lambda: llm
    c = TestClient(app)
    mail = {"subject": "견적 요청", "body": "견적서를 내일까지 회신 부탁드립니다.", "sender": "user1@cne.com"}
    c.post("/classify", json={"mail_id": 1, "from": "user1@cne.com", "to": ["user2@cne.com"], "subject": "견적 요청",
                              "body": "견적서를 내일까지 회신 부탁드립니다.", "received_at": "2026-11-11T09:00:00",
                              "owner": {"email": "user2@cne.com"}})
    c.post("/agent/plan", json={"text": "김◯◯ 팀장 건 다 처리했어", "actions": [{"id": "T03", "name": "일괄_완료", "description": "완료"}],
                                "context": {"now": "2026-11-11T09:00:00"}})
    c.post("/draft", json={"kind": "reply", "mail": mail})
    c.post("/polish", json={"text": "확인했습니다", "style": "polite", "mail": mail})
    c.post("/summarize", json={"kind": "mail", "mail": mail})
    snap = egress.snapshot(OLLAMA)
    assert calls and set(calls) == {"localhost"}  # 모델 호출은 실제로 일어났다(로컬로만)
    assert snap["external"] == 0 and snap["blocked"] == 0 and snap["local"] == len(calls)
    assert snap["mode"] == "local_only" and snap["allow"] == []


def test_api_mode_records_external_host_without_body():
    def handler(req: httpx.Request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "{\"text\": \"x\"}"}}]})
    llm = ExaoneApiClient(API, transport=httpx.MockTransport(handler), sleep=lambda s: None)
    llm.chat_json("system", "user", {"type": "object"})
    snap = egress.snapshot(API)
    assert snap["external"] == 1 and snap["external_hosts"] == {"api.exaone.ai": 1} and snap["mode"] == "external_allowed"


def test_external_call_outside_allow_list_is_blocked_before_sending(caplog):
    """로컬 모드인데 외부 모델 클라이언트가 만들어진 경우(설정 실수): 보내기 전에 막고 연결 실패처럼 다룬다."""
    sent: list = []
    misconfigured = Settings(llm_backend="ollama", exaone_api_key="test-key-not-real")
    llm = ExaoneApiClient(misconfigured, transport=httpx.MockTransport(lambda r: sent.append(r) or httpx.Response(200)),
                          sleep=lambda s: None)
    with caplog.at_level("WARNING", logger="app.egress"), pytest.raises(LLMError):
        llm.chat_json("system", "비밀 본문", {"type": "object"})
    assert sent == []  # 나가지 않았다
    snap = egress.snapshot(misconfigured)
    assert snap["blocked"] == 1 and snap["blocked_hosts"] == {"api.exaone.ai": 1} and snap["external"] == 0
    assert "api.exaone.ai" in caplog.text and "비밀 본문" not in caplog.text and "test-key" not in caplog.text


def test_health_shows_egress():
    llm = OllamaClient(OLLAMA, transport=httpx.MockTransport(_ollama_handler([])))
    app.dependency_overrides[llm_dep] = lambda: llm
    body = TestClient(app).get("/health").json()
    assert set(body["egress"]) == {"mode", "allow", "local", "external", "blocked", "external_hosts", "blocked_hosts"}
