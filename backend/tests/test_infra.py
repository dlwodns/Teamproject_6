"""시작 시 설정 검사(INF-4)."""
import pytest

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
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "  ")
    errors = check_settings(Settings(mail_source="outlook_graph"))
    assert [e.split(":")[0] for e in errors] == ["MS_GRAPH_CLIENT_SECRET", "TOKEN_ENCRYPTION_KEY"]
    assert not any("id-123" in e for e in errors)


def test_ensure_settings_stops_startup(monkeypatch):
    monkeypatch.setenv("APP_MODE", "staging")
    with pytest.raises(RuntimeError, match="APP_MODE='staging'"):
        ensure_settings()

