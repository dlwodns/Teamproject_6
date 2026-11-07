"""시작 시 설정 검사(INF-4)."""
import pytest

from app.core.config import check_settings, ensure_settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("LLM_BACKEND", "LLM_TIMEOUT_S", "ROUTER_THRESHOLD", "OLLAMA_BASE_URL", "LLAMACPP_BASE_URL"):
        monkeypatch.delenv(name, raising=False)


def test_check_settings_ok_by_default():
    assert check_settings() == []


def test_check_settings_rejects_bad_values(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "openai")
    monkeypatch.setenv("ROUTER_THRESHOLD", "1.5")
    monkeypatch.setenv("LLM_TIMEOUT_S", "0")
    monkeypatch.setenv("OLLAMA_BASE_URL", "localhost:11434")
    errors = check_settings()
    assert [e.split(":")[0] for e in errors] == ["LLM_BACKEND='openai'", "LLM_TIMEOUT_S", "ROUTER_THRESHOLD", "OLLAMA_BASE_URL"]


def test_check_settings_reports_non_numbers(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT_S", "2m")
    assert check_settings() == ["LLM_TIMEOUT_S='2m': 숫자여야 한다"]
    with pytest.raises(RuntimeError, match="LLM_TIMEOUT_S"):
        ensure_settings()

