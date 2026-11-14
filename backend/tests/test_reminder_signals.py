"""리마인더 신호(ai /signals, AI-24) 받기 · 스케줄러 · 켜는 값 (BE-12, BE-D32 · BE-D33)."""
import json
from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.ai_client.client import AIClient
from app.jobs import scheduler, signals
from app.models import Commitment, Mail, ReminderSignal, SignalCheck
from tests.clock_util import move_to
from tests.test_reminders import NOW, _base, _by_key, _items, _mail, _notes, _sent, _task


@pytest.fixture(autouse=True)
def fixed_clock():
    move_to(NOW)
    yield
    move_to(None)


# ---------- AI 신호(/signals) ----------

SAMPLE = {  # AI-24 응답 그대로(ai/README.md /signals): ID는 문자열, 시각은 시간대 없는 KST
    "mail_id": "31",
    "commitments": [{"who": "them", "text": "보안 점검 결과 보내기", "due_raw": "내일 오전 중", "due_at": "2026-11-13T12:00:00",
                     "evidence": "보안 점검 결과는 제가 내일 오전 중에 보내 드리겠습니다."}],
    "due_changes": [{"task_id": "12", "new_due_raw": "11/20까지", "new_due_at": "2026-11-20T18:00:00",
                     "evidence": "이관 일정표는 11/20까지만 주셔도 됩니다."}],
    "resolved": [{"task_id": "13", "reason": "not_needed", "evidence": "계정 목록은 안 보내 주셔도 됩니다."}],
    "asks_me_question": True, "source": "exaone", "model": "k-exaone", "prompt_version": "signals_v1",
    "elapsed_ms": 31000, "dropped": 0, "fallback": None, "detail": None,
}
BODY = ("이관 일정표는 11/20까지만 주셔도 됩니다.\n보안 점검 결과는 제가 내일 오전 중에 보내 드리겠습니다.\n"
        "계정 목록은 안 보내 주셔도 됩니다.\n그런데 담당자는 누구신가요?")


def _signal_world(db):
    _base(db)
    _sent(db, 30, "c-31", sent_at=datetime(2026, 11, 10, 16, 20), subject="이관 일정")
    _mail(db, 10, conv="c-31", sent_at=datetime(2026, 11, 11, 9, 0), subject="이관 일정")
    _task(db, 12, 10, due=datetime(2026, 11, 13, 18, 0), text="이관 일정표 보내기")
    _task(db, 13, 10, text="계정 목록 보내기")
    _mail(db, 31, sender="minho.jang@example.com", conv="c-31", sent_at=datetime(2026, 11, 12, 10, 0), subject="RE: 이관 일정")
    db.commit()
    return db.get(Mail, 31)


def _ai(handler) -> AIClient:
    return AIClient("http://ai.test", transport=httpx.MockTransport(handler))


def test_signals_sample_shape_saved(client, db, monkeypatch):
    monkeypatch.setenv("REMINDER_SIGNALS", "1")
    mail = _signal_world(db)
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=SAMPLE)

    out = signals.after_classify(db, _ai(handler), mail, BODY)
    assert out == {"status": "done", "saved": {"commitments": 1, "due_changes": 1, "resolved": 1, "question": 1, "dropped": 0}}
    assert seen["mail"]["direction"] == "received" and seen["me"] == {"email": "me@cne.com", "name": "문규남"}
    assert [t["task_id"] for t in seen["open_tasks"]] == [12, 13] and len(seen["thread"]) == 2
    c = db.scalar(select(Commitment))
    assert (c.who, c.due_at, c.source) == ("them", datetime(2026, 11, 13, 12, 0), "exaone")
    kinds = {(s.kind, s.task_id) for s in db.scalars(select(ReminderSignal))}
    assert kinds == {("due_change", 12), ("resolved", 13), ("question", None)}
    move_to(datetime(2026, 11, 12, 11, 0))
    keys = set(_by_key(client))
    assert {"due_changed:task:12", "resolved:task:13"} <= keys
    assert signals.after_classify(db, _ai(handler), mail, BODY) == {"status": "done"}  # 같은 메일은 한 번


def test_signals_drop_bad_evidence_and_unknown_task(client, db, monkeypatch):
    monkeypatch.setenv("REMINDER_SIGNALS", "1")
    mail = _signal_world(db)
    bad = {**SAMPLE, "due_changes": [{**SAMPLE["due_changes"][0], "task_id": "999"}],
           "commitments": [{**SAMPLE["commitments"][0], "evidence": "본문에 없는 문장"}]}
    out = signals.after_classify(db, _ai(lambda r: httpx.Response(200, json=bad)), mail, BODY)
    assert out["saved"]["dropped"] == 2 and out["saved"]["commitments"] == 0


@pytest.mark.parametrize("response, status, attempts", [
    (httpx.Response(404, json={"detail": "Not Found"}), "skipped", 0),  # ai에 /signals가 없음 → 조용히 건너뜀
    (httpx.Response(200, json={**SAMPLE, "commitments": [], "due_changes": [], "resolved": [], "asks_me_question": False,
                               "source": "none", "fallback": "quota"}), "queued", 0),
    (httpx.Response(200, json={**SAMPLE, "commitments": [], "due_changes": [], "resolved": [], "asks_me_question": False,
                               "source": "none", "fallback": "model_failed"}), "queued", 1),
    (httpx.Response(200, json={**SAMPLE, "commitments": [], "due_changes": [], "resolved": [], "asks_me_question": False,
                               "source": "none", "fallback": "empty_body"}), "skipped", 0),
    (httpx.Response(500), "queued", 1),
])
def test_signals_failure_rules(client, db, monkeypatch, response, status, attempts):
    monkeypatch.setenv("REMINDER_SIGNALS", "1")
    mail = _signal_world(db)
    signals.after_classify(db, _ai(lambda r: response), mail, BODY)
    check = db.scalar(select(SignalCheck))
    assert (check.status, check.attempts) == (status, attempts)
    assert db.scalars(select(Commitment)).all() == []


def test_signals_model_failed_three_times_then_failed(client, db, monkeypatch):
    monkeypatch.setenv("REMINDER_SIGNALS", "1")
    mail = _signal_world(db)
    resp = {**SAMPLE, "commitments": [], "due_changes": [], "resolved": [], "source": "none", "fallback": "bad_output"}
    ai = _ai(lambda r: httpx.Response(200, json=resp))
    signals.after_classify(db, ai, mail, BODY)
    signals.run(db, ai, mail, BODY)
    signals.run(db, ai, mail, BODY)
    assert db.scalar(select(SignalCheck.status)) == "failed"


def test_signals_ai_off_keeps_rules_working(client, db, monkeypatch):
    monkeypatch.setenv("REMINDER_SIGNALS", "1")
    monkeypatch.setattr(signals, "fetch_body", lambda db, mail: BODY if mail.id == 31 else "")
    mail = _signal_world(db)

    def down(request):
        raise httpx.ConnectError("refused")

    assert signals.after_classify(db, _ai(down), mail, BODY)["error"] == "unavailable"
    assert db.scalar(select(SignalCheck.status)) == "queued"  # ai가 켜지면 스케줄러가 다시 부른다
    assert signals.run_pending(db, _ai(lambda r: httpx.Response(200, json=SAMPLE)))[0]["status"] == "done"
    monkeypatch.delenv("REMINDER_SIGNALS")
    assert signals.run_pending(db, _ai(down)) == []  # 꺼져 있으면 부르지 않는다
    assert _items(client)["counts"]["all"] >= 1


def test_signals_gate(client, db, monkeypatch):
    _base(db)
    _mail(db, 1, conv="lonely")  # 대화에 미처리 업무도 내 메일도 없음 → 부르지 않음
    _sent(db, 2, "out", sent_at=NOW - timedelta(hours=1))  # 보낸 메일 → 늘 부름
    db.commit()
    assert signals.enqueue(db, db.get(Mail, 2)) is None  # 꺼져 있으면 넣지 않는다
    monkeypatch.setenv("REMINDER_SIGNALS", "1")
    assert signals.should_call(db, db.get(Mail, 1)) is False
    assert signals.enqueue(db, db.get(Mail, 2)) is not None
    assert signals.after_classify(db, _ai(lambda r: httpx.Response(500)), db.get(Mail, 1), "x") is None


# ---------- 스케줄러 · 설정 · 예전 DB ----------

def test_scheduler_flag_and_tick(client, db, monkeypatch):
    _base(db)
    _mail(db, 1); _task(db, 1, 1, due=datetime(2026, 11, 11, 16, 0))  # 지금(14:00)은 기한 3시간 전이 지남
    db.commit()
    monkeypatch.delenv("REMINDER_SCHEDULER", raising=False)
    assert scheduler.enabled() is False
    scheduler.start()
    assert scheduler._scheduler is None
    scheduler.tick()  # 시작할 때 한 번 도는 틱: DB에서 다시 계산
    assert [n.reminder_key for n in _notes(db)] == ["due_soon:task:1"]
    monkeypatch.setenv("REMINDER_SCHEDULER", "1")
    scheduler.start()
    try:
        assert scheduler._scheduler.get_job(scheduler.JOB_ID) is not None
    finally:
        scheduler.stop()


def test_flag_values_checked_at_startup(monkeypatch):
    from app.core.config import check_settings

    monkeypatch.setenv("REMINDER_SCHEDULER", "yes")
    assert any(e.startswith("REMINDER_SCHEDULER") for e in check_settings())
    monkeypatch.setenv("REMINDER_SCHEDULER", "1")
    monkeypatch.setenv("REMINDER_SIGNALS", "")
    assert not any("REMINDER" in e for e in check_settings())


# ---------- 엣지(11-14 리뷰) ----------

def test_signals_same_mail_not_called_twice_at_once(client, db, monkeypatch):
    # 분류 작업자가 ai를 기다리는 동안(엑사원 약 30초) 스케줄러 틱이 같은 메일을 다시 부르면 약속이 두 번 저장된다
    monkeypatch.setenv("REMINDER_SIGNALS", "1")
    mail = _signal_world(db)
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            calls.append(signals.run(db, _ai(handler), mail, BODY))  # 그사이 다른 쪽이 같은 메일을 부름
        return httpx.Response(200, json=SAMPLE)

    assert signals.after_classify(db, _ai(handler), mail, BODY)["status"] == "done"
    assert calls.count(1) == 1 and calls[1] == {"status": "running"}
    assert len(db.scalars(select(Commitment)).all()) == 1


def test_signals_evidence_lines_checked_one_by_one(client, db, monkeypatch):
    # ai는 떨어진 두 문장을 줄바꿈으로 이어 근거로 준다(AI-D20). 비교는 ai와 같게 NFKC · 보이지 않는 글자 · 공백을 무시한다
    monkeypatch.setenv("REMINDER_SIGNALS", "1")
    mail = _signal_world(db)
    body = "이관 일정표는​ 11/20까지만 주셔도 됩니다.\n감사합니다.\n보안 점검 결과는 제가 내일 오전 중에 보내 드리겠습니다."
    two = "이관 일정표는 11/20까지만 주셔도 됩니다.\n보안 점검 결과는 제가 내일 오전 중에 보내 드리겠습니다."
    resp = {**SAMPLE, "resolved": [], "asks_me_question": False,
            "commitments": [{**SAMPLE["commitments"][0], "evidence": two}],
            "due_changes": [{**SAMPLE["due_changes"][0], "evidence": "이관 일정표는 １１/２０까지만 주셔도 됩니다."}]}
    out = signals.after_classify(db, _ai(lambda r: httpx.Response(200, json=resp)), mail, body)
    assert out["saved"] == {"commitments": 1, "due_changes": 1, "resolved": 0, "question": 0, "dropped": 0}
    bad = {**resp, "commitments": [{**SAMPLE["commitments"][0], "evidence": two + "\n본문에 없는 문장입니다."}],
           "due_changes": []}
    db.query(SignalCheck).delete()
    db.commit()
    assert signals.after_classify(db, _ai(lambda r: httpx.Response(200, json=bad)), mail, body)["saved"]["dropped"] == 1


def test_scheduler_first_run_uses_real_kst_not_os_time(monkeypatch):
    # 서버 OS 시간대가 KST가 아니어도 '시작하자마자 한 번'이 KST 기준 지금이어야 한다(스케줄러 시간대는 Asia/Seoul)
    from datetime import timezone

    from app.core import clock

    seen = {}

    class Fake:
        def __init__(self, **kw):
            pass

        def add_job(self, fn, trigger, **kw):
            seen.update(kw)

        def start(self):
            pass

    monkeypatch.setenv("REMINDER_SCHEDULER", "1")
    monkeypatch.setattr(scheduler, "BackgroundScheduler", Fake)
    monkeypatch.setattr(clock, "_utc_now", lambda: datetime(2026, 11, 11, 0, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(scheduler, "_scheduler", None)
    scheduler.start()
    assert seen["next_run_time"] == datetime(2026, 11, 11, 9, 0)
