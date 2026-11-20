"""AI-28 · AI-D24: 백그라운드 호출(분류 · 기억 추출 · 신호)은 LLM_BACKGROUND_TIMEOUT_S(기본 300),
대화형(명령 해석 · 다듬기 · 요약)은 LLM_TIMEOUT_S(기본 120). backend는 각각 310 · 130초를 기다린다."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.deps import llm_background_dep, llm_dep, settings_dep
from app.core.config import Settings, check_settings
from app.llm.client import DisabledClient, ExaoneApiClient, OllamaClient, Timed, with_timeout
from app.main import app

SETTINGS = Settings(llm_backend="ollama")  # 기본: 대화형 120 · 백그라운드 300


@pytest.fixture
def seen():
    got: dict[str, float] = {}

    def handler(req: httpx.Request):
        got.setdefault(req.headers.get("x-test-path", "?"), req.extensions["timeout"]["read"])
        content = json.dumps({"action": None, "reason": "unsupported", "facts": [], "signals": []})
        return httpx.Response(200, json={"message": {"content": content}, "done": True})

    llm = OllamaClient(SETTINGS, transport=httpx.MockTransport(handler))
    app.dependency_overrides[llm_dep] = lambda: llm
    app.dependency_overrides[settings_dep] = lambda: SETTINGS
    yield got, llm
    app.dependency_overrides.clear()


def _timeout_of(client: TestClient, got: dict, path: str, body: dict) -> float:
    got.clear()
    client.post(path, json=body)
    assert got, f"{path}가 모델을 부르지 않았다"
    return next(iter(got.values()))


def test_background_endpoints_use_180_and_interactive_120(seen):
    got, _ = seen
    c = TestClient(app)
    mail = {"subject": "Quote", "body": "Please send the quote by tomorrow.", "sender": "user1@cne.com"}
    assert _timeout_of(c, got, "/classify", {"mail_id": 1, "from": "user1@cne.com", "to": ["user2@cne.com"],
                                             "subject": "견적", "body": "견적서를 내일까지 회신 부탁드립니다.",
                                             "received_at": "2026-11-11T09:00:00", "owner": {"email": "user2@cne.com"}}) == 300
    assert _timeout_of(c, got, "/memory/extract", {"mail_id": 1, "from": "user1@cne.com", "subject": "s",
                                                   "body": "저는 한빛은행 전환을 맡고 있습니다.",
                                                   "owner": {"email": "user2@cne.com"}}) == 300
    assert _timeout_of(c, got, "/agent/plan", {"text": "김◯◯ 팀장 건 다 처리했어",
                                               "actions": [{"id": "T03", "name": "일괄_완료", "description": "완료"}],
                                               "context": {"now": "2026-11-11T09:00:00"}}) == 120
    assert _timeout_of(c, got, "/polish", {"text": "확인했습니다", "style": "polite", "mail": mail}) == 120


def test_timed_shares_state_with_the_one_client():
    """감싸도 같은 클라이언트라 하루 한도 · 키 거절 상태가 /health와 갈라지지 않는다."""
    api = ExaoneApiClient(Settings(exaone_api_key="k"), transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    t = with_timeout(api, 180)
    assert isinstance(t, Timed) and t.model == api.model
    api.quota_exhausted = True
    assert t.quota_exhausted is True and t.health() == api.health()


def test_exaone_deadline_uses_the_given_timeout(monkeypatch):
    api = ExaoneApiClient(Settings(exaone_api_key="k", llm_timeout_s=120), transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})), sleep=lambda s: None)
    used = []
    real = api._http.post
    monkeypatch.setattr(api._http, "post", lambda *a, **k: used.append(k["timeout"]) or real(*a, **k))
    with_timeout(api, 180).chat_json("s", "u", {"type": "object"})
    api.chat_json("s", "u", {"type": "object"})
    assert used[0] > 170 and used[1] <= 120  # 백그라운드는 180초 안에서, 대화형은 120초 안에서


@pytest.mark.parametrize("llm", [DisabledClient(SETTINGS), object()])
def test_clients_without_timeout_pass_through(llm):
    assert with_timeout(llm, 180) is llm  # LLM 꺼짐 · 테스트 가짜는 그대로


def test_background_dep_wraps(seen):
    _, llm = seen
    wrapped = llm_background_dep(llm, SETTINGS)
    assert isinstance(wrapped, Timed) and wrapped._seconds == 300


@pytest.mark.parametrize(("bg", "ok"), [("", True), ("180", True), ("120", True), ("60", False), ("abc", False)])
def test_setting_check(monkeypatch, bg, ok):
    monkeypatch.setenv("LLM_TIMEOUT_S", "120")
    if bg:
        monkeypatch.setenv("LLM_BACKGROUND_TIMEOUT_S", bg)
    else:
        monkeypatch.delenv("LLM_BACKGROUND_TIMEOUT_S", raising=False)
    assert (not any("LLM_BACKGROUND_TIMEOUT_S" in e for e in check_settings())) is ok
