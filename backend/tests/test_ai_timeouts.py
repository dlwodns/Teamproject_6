"""AI-28: ai 대기 시간을 백그라운드(분류 · 문맥 기억 · 신호)와 대화형(명령 · 다듬기 · 요약)으로 나눈다.
백그라운드는 AI_BACKGROUND_TIMEOUT_S(기본 310 = ai 백그라운드 300 + 10), 대화형은 화면 140초에 맞춰 130초 고정."""
from datetime import timedelta

import httpx
import pytest

from app.ai_client.client import TIMEOUT_S, AIClient
from app.core.config import check_settings
from app.jobs import classify


def _client(seen: dict):
    def handler(req: httpx.Request):
        seen[req.url.path] = req.extensions["timeout"]["read"]
        return httpx.Response(404)  # 응답 형식은 보지 않는다(대기 시간만 확인)
    return AIClient("http://127.0.0.1:8001", transport=httpx.MockTransport(handler))


def _call_all(c: AIClient):
    for call in (lambda: c.classify({}), lambda: c.extract_memory({}), lambda: c.signals({}),
                 lambda: c.polish({}), lambda: c.summarize({}), lambda: c.draft({})):
        try:
            call()
        except Exception:  # noqa: BLE001 - 404 응답이라 AIError가 나는 것이 정상
            pass
    try:
        from datetime import datetime
        c.plan("x", [], now=datetime(2026, 11, 17, 9, 0))
    except Exception:  # noqa: BLE001
        pass


def test_background_calls_use_setting_and_interactive_stay_130(monkeypatch):
    monkeypatch.setenv("AI_BACKGROUND_TIMEOUT_S", "610")
    seen: dict = {}
    _call_all(_client(seen))
    assert seen["/classify"] == seen["/memory/extract"] == seen["/signals"] == 610.0
    assert seen["/agent/plan"] == seen["/polish"] == seen["/draft"] == TIMEOUT_S == 130.0
    assert seen["/summarize"] == 620.0  # 머리 문장은 정한 시각의 백그라운드 작업만 부른다(AI-29): ai 600초 + 여유


def test_default_is_310_ai_background_plus_10(monkeypatch):
    monkeypatch.delenv("AI_BACKGROUND_TIMEOUT_S", raising=False)
    seen: dict = {}
    _call_all(_client(seen))
    assert seen["/classify"] == 310.0 and seen["/agent/plan"] == 130.0


def test_stale_job_window_follows_background_timeout(monkeypatch):
    monkeypatch.setenv("AI_BACKGROUND_TIMEOUT_S", "610")
    assert classify.stale_after() == timedelta(seconds=610 * 2 + 60)  # 길게 기다리는 작업을 멈춘 것으로 잘못 되살리지 않게
    monkeypatch.delenv("AI_BACKGROUND_TIMEOUT_S")
    assert classify.stale_after() == timedelta(seconds=310 * 2 + 60)


@pytest.mark.parametrize(("raw", "ok"), [("", True), ("130", True), ("190", True), ("610", True), (" 600 # 메모", True),
                                         ("29", False), ("1801", False), ("abc", False), ("nan", False)])
def test_setting_is_checked_at_startup(monkeypatch, raw, ok):
    monkeypatch.setenv("AI_BACKGROUND_TIMEOUT_S", raw)
    assert (not any(e.startswith("AI_BACKGROUND_TIMEOUT_S") for e in check_settings())) is ok
