"""캘린더 (BE-15 · D50 결정 6): 기간 조회 · 일정 넣기 · 빼기 · 되돌리기 · T15. 입력 → 기대 결과."""
from datetime import datetime

import pytest

from app.agent import executor
from app.core.db import Base, _add_missing_columns, make_engine
from app.models import Account, ActionLog, CalendarEvent, Mail, Task, User
from app.services import history
from tests.clock_util import move_to

NOW = datetime(2026, 11, 16, 9, 0)  # 월요일


@pytest.fixture
def box(db):
    """나(1)와 남(2). 내 메일 4통: 기한 업무 · 회의(시각 적힘, 끝 시각 있음) · 회의(시각 안 적힘) · 미룬 업무."""
    move_to(NOW)
    db.add_all([User(id=1, name="나"), User(id=2, name="남")])
    db.flush()
    db.add_all([Account(id=1, user_id=1, provider="dummy", email="me@example.com"),
                Account(id=2, user_id=2, provider="dummy", email="other@example.com")])
    db.flush()
    mails = [(1, 1, "견적서 보내 주세요"), (2, 1, "주간 회의 안내"), (3, 1, "워크숍 참석 요청"), (4, 1, "보고서 검토"),
             (5, 2, "남의 메일")]
    for mid, acc, subject in mails:
        db.add(Mail(id=mid, account_id=acc, source_id=f"M-{mid}", direction="received", sender="a@example.com",
                    subject=subject, sent_at=datetime(2026, 11, 13, 9)))
    db.flush()
    db.add_all([
        Task(id=1, mail_id=1, text="견적서 보내기", type="자료제출요청", due_at=datetime(2026, 11, 18, 18), due_time_stated=False),
        Task(id=2, mail_id=2, text="주간 회의 참석", type="일정참석", due_at=datetime(2026, 11, 19, 14),
             due_time_stated=True, end_at=datetime(2026, 11, 19, 15, 30)),
        Task(id=3, mail_id=3, text="워크숍 참석", type="일정참석", due_at=datetime(2026, 11, 20, 18), due_time_stated=False),
        Task(id=4, mail_id=4, text="보고서 검토", status="snoozed", snoozed_until=datetime(2026, 11, 17, 9)),
        Task(id=5, mail_id=5, text="남의 업무", due_at=datetime(2026, 11, 18, 10)),
        Task(id=6, mail_id=1, text="끝난 업무", status="done", due_at=datetime(2026, 11, 18, 10)),
    ])
    db.commit()
    yield db
    move_to(None)


def _week(client, start="2026-11-16", end="2026-11-22"):
    r = client.get("/api/calendar", params={"start": start, "end": end})
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_range_shows_due_meeting_snoozed(client, box):
    # 이번 주 → 미룬 업무(17일 09시) · 기한(18일, 시각 없음) · 회의(19일 14:00~15:30) · 회의(20일, 시각 없음)
    # 남의 업무 · 끝난 업무는 없다
    items = _week(client)
    got = [(i["kind"], i["task_id"], i["start"], i["end"], i["time_stated"]) for i in items]
    assert got == [
        ("snoozed", 4, "2026-11-17T09:00:00+09:00", None, True),
        ("due", 1, "2026-11-18T18:00:00+09:00", None, False),
        ("meeting", 2, "2026-11-19T14:00:00+09:00", "2026-11-19T15:30:00+09:00", True),
        ("meeting", 3, "2026-11-20T18:00:00+09:00", None, False),
    ]
    assert items[1]["subject"] == "견적서 보내 주세요"


def test_range_limits(client, box):
    # 기간 밖 · 거꾸로 · 62일 넘김 → 비어 있음 · 422 · 422
    assert _week(client, "2026-11-23", "2026-11-29") == []
    assert client.get("/api/calendar", params={"start": "2026-11-22", "end": "2026-11-16"}).status_code == 422
    assert client.get("/api/calendar", params={"start": "2026-11-01", "end": "2027-01-15"}).status_code == 422


def test_add_event_from_meeting_replaces_meeting_item(client, box):
    # 회의 업무로 일정 넣기 → 그 회의는 일정(event) 하나로만 보인다. 업무 상태는 그대로(D50: 일정과 업무는 따로)
    r = client.post("/api/calendar/events", json={"start": "2026-11-19T14:00:00+09:00", "end": "2026-11-19T15:30:00+09:00",
                                                  "task_id": 2, "via": "suggestion:meeting"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["item"]["title"] == "주간 회의 안내" and body["item"]["mail_id"] == 2  # 제목이 없으면 메일 제목
    kinds = [(i["kind"], i["task_id"]) for i in _week(client)]
    assert ("event", 2) in kinds and ("meeting", 2) not in kinds
    box.expire_all()
    assert box.get(Task, 2).status == "pending"
    log = box.get(ActionLog, body["action_id"])
    assert log.action == "T15" and log.source == "ui" and log.params_json["via"] == "suggestion:meeting"


def test_add_event_default_one_hour_and_one_per_mail(client, box):
    # 끝 시각 없음 → 시작 + 1시간. 같은 메일로 또 넣기 → 409. 말로 준 일정(메일 없음)은 '일정' 제목도 된다
    r = client.post("/api/calendar/events", json={"start": "2026-11-20T10:00:00", "mail_id": 3})
    assert r.json()["item"]["end"] == "2026-11-20T11:00:00+09:00"
    assert client.post("/api/calendar/events", json={"start": "2026-11-21T10:00:00", "mail_id": 3}).status_code == 409
    r = client.post("/api/calendar/events", json={"start": "2026-11-21T10:00:00"})
    assert r.status_code == 201 and r.json()["item"]["title"] == "일정"


def test_add_event_rejects_others_and_bad_range(client, box):
    # 남의 메일 · 남의 업무 → 404, 끝이 시작보다 앞 → 422
    assert client.post("/api/calendar/events", json={"start": "2026-11-20T10:00:00", "mail_id": 5}).status_code == 404
    assert client.post("/api/calendar/events", json={"start": "2026-11-20T10:00:00", "task_id": 5}).status_code == 404
    assert client.post("/api/calendar/events", json={"start": "2026-11-20T10:00:00",
                                                     "end": "2026-11-20T09:00:00"}).status_code == 422


def test_undo_add_and_remove(client, box):
    # 넣기 → 되돌리기 → 사라짐 → 다시 하기 → 다시 보임. 빼기 → 되돌리기 → 돌아옴
    r = client.post("/api/calendar/events", json={"start": "2026-11-20T10:00:00", "title": "예산 회의"}).json()
    ev_id, add_id = r["item"]["event_id"], r["action_id"]
    back = client.post(f"/api/actions/{add_id}/undo")
    assert back.status_code == 200 and back.json()["tasks"] == []
    assert not [i for i in _week(client) if i["kind"] == "event"]
    assert client.post(f"/api/actions/{back.json()['action_id']}/undo").status_code == 200
    assert [i["event_id"] for i in _week(client) if i["kind"] == "event"] == [ev_id]

    rm = client.delete(f"/api/calendar/events/{ev_id}")
    assert rm.status_code == 200
    assert not [i for i in _week(client) if i["kind"] == "event"]
    assert client.delete(f"/api/calendar/events/{ev_id}").status_code == 404  # 이미 뺀 일정
    assert client.post(f"/api/actions/{rm.json()['action_id']}/undo").status_code == 200
    assert [i["event_id"] for i in _week(client) if i["kind"] == "event"] == [ev_id]


def test_undo_blocked_when_event_changed_after(client, box):
    # 넣기 → 빼기 → '넣기' 되돌리기 → 이미 빠져 있어 409(기록 밖 상태를 덮어쓰지 않는다)
    r = client.post("/api/calendar/events", json={"start": "2026-11-20T10:00:00"}).json()
    client.delete(f"/api/calendar/events/{r['item']['event_id']}")
    assert client.post(f"/api/actions/{r['action_id']}/undo").status_code == 409


def test_history_describes_calendar(client, box):
    r = client.post("/api/calendar/events", json={"start": "2026-11-20T10:00:00", "title": "예산 회의"}).json()
    item = next(i for i in history.history(box, 1) if i["action_id"] == r["action_id"])
    assert item["text"] == "캘린더에 11/20 10:00 '예산 회의'을(를) 넣었어요" and item["can_undo"] is True


# ---- T15 (에이전트) ----

def _plan(target=None, params=None):
    return {"action": "T15", "action_name": None, "target": target or {}, "params": params or {}, "source": "rule"}


def test_t15_spoken_time_done_and_undo(client, box):
    # "다음 주 목요일 오후 4시 거래처 미팅 잡아줘" → 바로 넣음 · 결과 카드에 되돌리기 · T04로 되돌림
    r = executor.run(box, 1, _plan(params={"start": "2026-11-19T16:00:00", "end": None, "title": "거래처 미팅"}))
    box.commit()
    assert r.kind == "done" and r.action_id is not None and "거래처 미팅" in r.title
    ev = box.query(CalendarEvent).one()
    assert (ev.start_at, ev.end_at, ev.mail_id) == (datetime(2026, 11, 19, 16), datetime(2026, 11, 19, 17), None)
    u = executor.run(box, 1, {"action": "T04", "target": {}, "params": {}, "source": "rule"})
    box.commit()
    assert u.kind == "done" and u.title == "캘린더 일정을 되돌렸어요"
    box.expire_all()
    assert box.get(CalendarEvent, ev.id).deleted_at is not None


def test_t15_no_time_asks(box):
    # 시각 없음(고른 메일도 없음) → 되묻기. 고른 메일이 시각 안 적힌 회의 → 되묻기(18:00을 지어내지 않음)
    assert executor.run(box, 1, _plan(params={"start": None, "end": None, "title": "회의"})).kind == "ask"
    r = executor.run(box, 1, _plan({"mail_ids": [3]}, {"start": None, "end": None, "title": None}))
    assert r.kind == "ask" and r.title.startswith("몇 시로")
    assert box.query(CalendarEvent).count() == 0


def test_t15_selected_meeting_mail_uses_mail_time(box):
    # "이 회의 캘린더에 넣어줘"(시각 적힌 회의 메일) → 메일의 14:00~15:30, 제목은 메일 제목
    r = executor.run(box, 1, _plan({"mail_ids": [2]}, {"start": None, "end": None, "title": None}))
    assert r.kind == "done"
    ev = box.query(CalendarEvent).one()
    assert (ev.start_at, ev.end_at, ev.task_id, ev.title) == (datetime(2026, 11, 19, 14), datetime(2026, 11, 19, 15, 30), 2,
                                                              "주간 회의 안내")


def test_t15_past_time_and_bad_value_ask(box):
    # 지난 시각 · 읽을 수 없는 값 → 되묻기
    assert executor.run(box, 1, _plan(params={"start": "2026-11-15T10:00:00"})).kind == "ask"
    assert executor.run(box, 1, _plan(params={"start": "금요일"})).kind == "ask"
    assert box.query(CalendarEvent).count() == 0


def test_old_db_gets_new_columns(tmp_path):
    # 칸이 없던 옛 tasks 표 → 시작할 때 새 칸이 더해져 읽힌다. NULL 칸(type 등)과 고정 기본값 칸(urgent = 0) 모두
    eng = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as c:
        c.exec_driver_sql("CREATE TABLE tasks (id INTEGER PRIMARY KEY, mail_id INTEGER, text TEXT)")
        c.exec_driver_sql("INSERT INTO tasks (id, mail_id, text) VALUES (1, 1, '옛 업무')")
    Base.metadata.create_all(eng)
    _add_missing_columns(eng)
    with eng.connect() as c:
        cols = {r[1] for r in c.exec_driver_sql("PRAGMA table_info(tasks)")}
        row = c.exec_driver_sql("SELECT type, urgent, status FROM tasks WHERE id = 1").one()
    assert {"type", "due_time_stated", "end_at", "evidence_text", "urgent"} <= cols
    assert tuple(row) == (None, 0, "pending")
