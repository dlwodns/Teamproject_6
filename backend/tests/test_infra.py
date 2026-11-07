"""시작 시 설정 검사(INF-4) · 요청 ID(INF-12)."""
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import request_id
from app.core.config import Settings, check_settings, ensure_settings


def test_check_settings_ok_by_default():
    assert check_settings(Settings()) == []


def test_check_settings_rejects_bad_values():
    errors = check_settings(Settings(app_mode="production", mail_source="gmail", database_url="postgresql://x",
                                     ai_service_url="localhost:8001"))
    assert [e.split(":")[0] for e in errors] == ["APP_MODE='production'", "MAIL_SOURCE='gmail'", "DATABASE_URL", "AI_SERVICE_URL"]


def test_outlook_needs_secrets_without_showing_them(monkeypatch):
    monkeypatch.setenv("MS_GRAPH_CLIENT_ID", "id-123")
    monkeypatch.delenv("MS_GRAPH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("MS_GRAPH_REDIRECT_URI", raising=False)
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "  ")
    errors = check_settings(Settings(mail_source="outlook_graph"))
    assert [e.split(":")[0] for e in errors] == ["MS_GRAPH_CLIENT_SECRET", "MS_GRAPH_REDIRECT_URI", "TOKEN_ENCRYPTION_KEY"]
    assert not any("id-123" in e for e in errors)


def test_imap_is_not_accepted_yet():  # 커넥터가 없는데 imap으로 뜨면 나중에 조용히 실패한다
    assert [e.split(":")[0] for e in check_settings(Settings(mail_source="imap"))] == ["MAIL_SOURCE='imap'"]


def test_ensure_settings_stops_startup(monkeypatch):
    monkeypatch.setenv("APP_MODE", "staging")
    with pytest.raises(RuntimeError, match="APP_MODE='staging'"):
        ensure_settings()


def _app() -> FastAPI:
    app = FastAPI()
    request_id.install(app)

    @app.get("/rid")
    def rid() -> dict:  # 동기 엔드포인트(스레드풀)에서도 같은 ID가 보이는지
        return {"rid": request_id.current_request_id(), "headers": request_id.request_id_headers()}

    return app


def test_request_id_is_passed_through_and_logged_without_query(caplog):
    caplog.set_level(logging.INFO, logger="app.access")
    request_id.access_log.addHandler(caplog.handler)
    try:
        r = TestClient(_app()).get("/rid?sender=kim", headers={"X-Request-ID": "fe-abc_1.2"})
    finally:
        request_id.access_log.removeHandler(caplog.handler)
    assert r.headers["X-Request-ID"] == "fe-abc_1.2"
    assert r.json() == {"rid": "fe-abc_1.2", "headers": {"X-Request-ID": "fe-abc_1.2"}}
    assert caplog.messages and caplog.messages[-1].startswith("GET /rid 200 ")
    assert "kim" not in caplog.text  # 쿼리 문자열은 남기지 않는다


@pytest.mark.parametrize("incoming", ["", "a b", "x" * 65, "evil\nline"])
def test_request_id_rejects_bad_incoming_and_makes_new(incoming):
    r = TestClient(_app()).get("/rid", headers={"X-Request-ID": incoming} if incoming else {})
    rid = r.headers["X-Request-ID"]
    assert rid != incoming and len(rid) == 32 and r.json()["rid"] == rid


def test_no_request_id_outside_request():
    assert request_id.current_request_id() == "-" and request_id.request_id_headers() == {}


def test_app_returns_request_id(client):
    assert client.get("/health").headers["X-Request-ID"]
