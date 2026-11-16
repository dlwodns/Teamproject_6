from app.core.clock import now
from app.models import User


def test_now_is_naive_kst():
    assert now().tzinfo is None


def test_db_time_comparable_with_now(db):
    # DB에서 읽은 시각과 now()를 비교해도 오류가 나지 않아야 한다(기한 경과 · 리마인더 판정)
    db.add(User(id=1, name="테스트"))
    db.commit()
    db.expire_all()
    assert db.get(User, 1).created_at <= now()


# ---------- 시연 시각(CLOCK_START) · offset ----------
# 실제 sleep 없이 실제 시각을 대는 곳(clock._utc_now)만 바꿔 시간을 흐르게 한다.
from datetime import datetime, timedelta, timezone  # noqa: E402

import pytest  # noqa: E402

from app.core import clock  # noqa: E402
from app.core.config import Settings, check_settings, ensure_settings  # noqa: E402

REAL = datetime(2026, 11, 12, 5, 30, tzinfo=timezone.utc)  # = 2026-11-12 14:30 KST
DEMO = datetime(2026, 10, 20, 9, 0)


@pytest.fixture
def fake_real(monkeypatch):
    """실제 시각을 손으로 정한다. 끝나면 offset과 시각 공급을 되돌린다."""
    saved = clock.get_offset()
    state = {"t": REAL}
    monkeypatch.setattr(clock, "_utc_now", lambda: state["t"])
    try:
        yield state
    finally:
        clock.set_offset(saved)


def test_without_clock_start_returns_real_kst(fake_real):
    assert clock.init_clock("") == timedelta(0)
    assert clock.now() == datetime(2026, 11, 12, 14, 30)  # UTC 05:30 → KST 14:30, OS 시간대와 무관


def test_real_now_unpatched_is_kst():
    before = datetime.now(clock.KST).replace(tzinfo=None)
    assert before - timedelta(seconds=1) <= clock.real_now() <= before + timedelta(seconds=5)


@pytest.mark.parametrize("raw", ["2026-10-20T09:00:00", "2026-10-20T09:00:00+09:00", "2026-10-20T00:00:00Z",
                                 " 2026-10-20T09:00 "])
def test_inputs_mean_same_kst(raw):
    assert clock.parse_clock_start(raw) == DEMO


def test_starts_at_clock_start_and_flows(fake_real):
    clock.init_clock("2026-10-20T09:00")
    assert clock.now() == DEMO and clock.now().tzinfo is None
    fake_real["t"] = REAL + timedelta(minutes=90, seconds=7)
    assert clock.now() == DEMO + timedelta(minutes=90, seconds=7)


def test_set_offset_replaces_and_shows_in_now(fake_real):
    clock.init_clock("2026-10-20T09:00")
    clock.set_offset(clock.get_offset() + timedelta(days=1))  # BE-14: 하루 앞으로
    assert clock.now() == DEMO + timedelta(days=1)
    clock.set_offset(timedelta(0))  # 바꿔 넣는다(더하지 않는다)
    assert clock.now() == datetime(2026, 11, 12, 14, 30)
    with pytest.raises(TypeError):
        clock.set_offset(3600)


def test_reinit_does_not_accumulate(fake_real):
    for _ in range(3):
        clock.init_clock("2026-10-20T09:00")
    assert clock.now() == DEMO
    fake_real["t"] = REAL + timedelta(hours=2)  # 2시간 뒤 다시 정하면 그 시점에서 다시 09:00
    clock.init_clock("2026-10-20T09:00")
    assert clock.now() == DEMO


def test_reinit_empty_resets_offset(fake_real):
    clock.init_clock("2026-10-20T09:00")
    assert clock.init_clock(None) == timedelta(0) and clock.init_clock("  ") == timedelta(0)
    assert clock.now() == datetime(2026, 11, 12, 14, 30)


@pytest.mark.parametrize("raw", ["2026/10/20 09:00", "tomorrow", "2026-13-01T09:00", "2026-10-20T25:00"])
def test_bad_clock_start_fails_settings_check(raw, monkeypatch):
    errors = check_settings(Settings(clock_start=raw))
    assert len(errors) == 1 and errors[0].startswith(f"CLOCK_START={raw!r}: ISO 8601")
    monkeypatch.setenv("CLOCK_START", raw)
    with pytest.raises(RuntimeError, match="CLOCK_START"):
        ensure_settings()


def test_good_clock_start_passes_settings_check():
    assert check_settings(Settings(clock_start="2026-10-20T00:00:00Z")) == []


def test_server_start_sets_offset(monkeypatch, fake_real, db):
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setenv("CLOCK_START", "2026-10-20T09:00")
    with TestClient(app):
        assert clock.now() == DEMO
    monkeypatch.delenv("CLOCK_START")
    with TestClient(app):  # 다시 띄우면 다시 정한다. 비었으니 0
        assert clock.get_offset() == timedelta(0)


def test_patching_now_still_works(monkeypatch, fake_real):
    # 시각을 고정하려면 지금처럼 clock.now를 바꾸거나 시각을 인자로 넘긴다. offset과 섞이지 않는다
    clock.init_clock("2026-10-20T09:00")
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 3, 9, 0))
    assert clock.now() == datetime(2026, 11, 3, 9, 0)
