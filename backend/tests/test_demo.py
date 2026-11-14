"""시연 도구 — 시간 이동 (BE-14 · BE-D23). DEMO_TOOLS=true일 때만 경로가 생기고, APP_MODE와 관계없다."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import demo
from app.core import clock
from app.core.config import check_settings
from app.main import app as main_app

REAL = datetime(2026, 11, 14, 5, 0, tzinfo=timezone.utc)  # = 2026-11-14 14:00 KST


@pytest.fixture
def fake_real(monkeypatch):
    """실제 시각을 손으로 정한다(sleep 없이 시간을 흐르게). 끝나면 offset을 되돌린다."""
    saved = clock.get_offset()
    state = {"t": REAL}
    monkeypatch.setattr(clock, "_utc_now", lambda: state["t"])
    clock.set_offset(timedelta(0))
    try:
        yield state
    finally:
        clock.set_offset(saved)


@pytest.fixture
def demo_client(monkeypatch, fake_real):
    monkeypatch.setenv("DEMO_TOOLS", "true")
    monkeypatch.delenv("CLOCK_START", raising=False)
    app = FastAPI()
    assert demo.install(app)
    return TestClient(app)


# ---------- 등록 조건 ----------

def test_main_app_has_no_clock_route_without_demo_tools(client):
    # 테스트 환경은 APP_MODE=dev지만 DEMO_TOOLS가 없다 → 경로 자체가 없다(dev여도 404)
    assert client.get("/api/dev/clock").status_code == 404
    assert client.post("/api/dev/clock", json={"forward_minutes": 60}).status_code == 404
    assert "/api/dev/clock" not in main_app.openapi()["paths"]


@pytest.mark.parametrize(("mode", "flag", "installed"), [
    ("dev", "", False), ("dev", "false", False), ("dev", "1", True),
    ("prod", "true", True),  # APP_MODE와 관계없다(prod 시연 서버는 프록시 기본 인증으로 막는다)
    ("prod", "", False),
])
def test_install_depends_only_on_demo_tools(monkeypatch, mode, flag, installed):
    monkeypatch.setenv("APP_MODE", mode)
    monkeypatch.setenv("DEMO_TOOLS", flag)
    app = FastAPI()
    assert demo.install(app) is installed
    assert (TestClient(app).get("/api/dev/clock").status_code == 200) is installed


@pytest.mark.parametrize("bad", ["yes", "ture", "enabled"])
def test_demo_tools_typo_stops_server(monkeypatch, bad):
    monkeypatch.setenv("DEMO_TOOLS", bad)
    assert any(e.startswith("DEMO_TOOLS=") for e in check_settings())


def test_demo_tools_valid_values_pass(monkeypatch):
    for ok in ("", "0", "1", "on", "off", "true", "false", " TRUE "):
        monkeypatch.setenv("DEMO_TOOLS", ok)
        assert not any(e.startswith("DEMO_TOOLS=") for e in check_settings())


# ---------- 시간 이동 ----------

def test_get_shows_service_time(demo_client):
    r = demo_client.get("/api/dev/clock").json()
    assert r == {"now": "2026-11-14T14:00:00+09:00", "offset_seconds": 0, "clock_start": None}


@pytest.mark.parametrize("at", ["2026-10-20T09:00", "2026-10-20T09:00:00+09:00", "2026-10-20T00:00:00Z"])
def test_move_to_time_any_zone(demo_client, fake_real, at):
    r = demo_client.post("/api/dev/clock", json={"at": at})
    assert r.status_code == 200 and r.json()["now"] == "2026-10-20T09:00:00+09:00"
    assert clock.now() == datetime(2026, 10, 20, 9, 0)
    fake_real["t"] = REAL + timedelta(minutes=10)  # 옮긴 뒤에도 실제 시간만큼 흐른다(멈춘 시각이 아님)
    assert clock.now() == datetime(2026, 10, 20, 9, 10)


def test_forward_adds_to_current_offset(demo_client):
    demo_client.post("/api/dev/clock", json={"at": "2026-10-20T09:00"})
    r = demo_client.post("/api/dev/clock", json={"forward_minutes": 180}).json()
    assert r["now"] == "2026-10-20T12:00:00+09:00"
    r = demo_client.post("/api/dev/clock", json={"forward_minutes": 60 * 24}).json()
    assert r["now"] == "2026-10-21T12:00:00+09:00"


@pytest.mark.parametrize("body", [
    {}, {"at": "2026-10-20T09:00", "forward_minutes": 10},  # 둘 다 없음 · 둘 다
    {"forward_minutes": 0}, {"forward_minutes": -60},  # 뒤로는 at으로만
    {"forward_minutes": 60 * 24 * 30 + 1},  # 한 번에 30일 넘게
    {"at": "어제"}, {"minutes": 10},  # 틀린 시각 · 없는 칸
    {"at": "9999-12-31T23:59"}, {"at": "0001-01-01T00:00"}, {"at": "1999-12-31T23:59"},  # 흐르다 넘치는 끝 시각
    {"at": "9999-12-31T23:59:00-12:00"},  # KST로 바꾸다 넘침(500이 아니라 422)
    {"forward_minutes": True}, {"forward_minutes": "60"}, {"forward_minutes": 1.5},  # 숫자만
])
def test_bad_move_is_422_and_keeps_time(demo_client, body):
    before = clock.now()
    assert demo_client.post("/api/dev/clock", json=body).status_code == 422
    assert clock.now() == before


def test_forward_cannot_pass_2099(demo_client):
    demo_client.post("/api/dev/clock", json={"at": "2099-12-30T00:00"})
    assert demo_client.post("/api/dev/clock", json={"forward_minutes": 60 * 24 * 2}).status_code == 422
    assert demo_client.get("/api/dev/clock").json()["now"] == "2099-12-30T00:00:00+09:00"


def test_reset_goes_back_to_clock_start(demo_client, monkeypatch):
    monkeypatch.setenv("CLOCK_START", "2026-10-20T09:00")
    demo_client.post("/api/dev/clock", json={"at": "2026-12-01T18:00"})
    r = demo_client.post("/api/dev/clock/reset").json()
    assert r["now"] == "2026-10-20T09:00:00+09:00" and r["clock_start"] == "2026-10-20T09:00"


def test_reset_without_clock_start_is_real_time(demo_client):
    demo_client.post("/api/dev/clock", json={"forward_minutes": 600})
    r = demo_client.post("/api/dev/clock/reset").json()
    assert r == {"now": "2026-11-14T14:00:00+09:00", "offset_seconds": 0, "clock_start": None}
