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


def test_undo_remove_blocked_when_mail_has_other_event(client, box):
    # #74 리뷰: 메일 1로 A 넣기 → A 빼기 → 메일 1로 B 넣기 → 'A 빼기' 되돌리기 → 409(메일 한 통에 살아 있는 일정은 하나)
    a = client.post("/api/calendar/events", json={"start": "2026-11-20T10:00:00", "mail_id": 1}).json()
    rm = client.delete(f"/api/calendar/events/{a['item']['event_id']}").json()
    b = client.post("/api/calendar/events", json={"start": "2026-11-21T10:00:00", "mail_id": 1})
    assert b.status_code == 201
    row = next(i for i in history.history(box, 1) if i["action_id"] == rm["action_id"])
    assert row["can_undo"] is False  # 기록 탭에도 [되돌리기]를 보이지 않는다
    assert client.post(f"/api/actions/{rm['action_id']}/undo").status_code == 409
    assert [i["event_id"] for i in _week(client) if i["kind"] == "event"] == [b.json()["item"]["event_id"]]


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
    assert u.kind == "done" and u.title == "캘린더 일정 등록을 취소했습니다"
    box.expire_all()
    assert box.get(CalendarEvent, ev.id).deleted_at is not None


def test_t15_no_time_asks(box):
    # 시각 없음(고른 메일도 없음) → 되묻기. 고른 메일이 시각 안 적힌 회의 → 되묻기(18:00을 지어내지 않음)
    assert executor.run(box, 1, _plan(params={"start": None, "end": None, "title": "회의"})).kind == "ask"
    r = executor.run(box, 1, _plan({"mail_ids": [3]}, {"start": None, "end": None, "title": None}))
    assert r.kind == "ask" and r.title.startswith("등록할 날짜")
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


# ---------- 다시 알릴 시각이 지난 미룬 업무(BE-D24 보완, C2) ----------
# 미처리 = pending 또는 snoozed인데 snoozed_until <= 지금(rules._open_tasks와 같은 기준).
# 지난 업무는 원래 기한 날짜에 due · meeting으로, snoozed 표시는 빠진다. 기한이 없으면 snoozed 표시를 남긴다.

def _kinds(client, start="2026-11-16", end="2026-11-22", **kw):
    r = client.get("/api/calendar", params={"start": start, "end": end}, **kw)
    assert r.status_code == 200, r.text
    return [(i["kind"], i["task_id"], i["start"][:16]) for i in r.json()["items"]]


def _snooze(client, task_id, until):
    r = client.patch(f"/api/tasks/{task_id}", json={"status": "snoozed", "snoozed_until": until})
    assert r.status_code == 200, r.text
    return r.json()["action_id"]


def test_expired_snooze_shows_on_due_day_before_at_after(client, box):
    # 기한 18일 18:00 업무를 17일 09:00까지 미룸 → 직전엔 17일 snoozed, 정각 · 이후엔 18일 due, snoozed 없음
    _snooze(client, 1, "2026-11-17T09:00:00+09:00")
    move_to(datetime(2026, 11, 17, 8, 59))
    got = _kinds(client)
    assert ("snoozed", 1, "2026-11-17T09:00") in got and not any(k == "due" and t == 1 for k, t, _ in got)
    for at in (datetime(2026, 11, 17, 9, 0), datetime(2026, 11, 17, 10, 0)):
        move_to(at)
        got = _kinds(client)
        assert [x for x in got if x[1] == 1] == [("due", 1, "2026-11-18T18:00")], at


def test_expired_snooze_same_day_no_duplicate(client, box):
    # 기한과 다시 알릴 시각이 같은 날(18일 09:00 → 기한 18일 18:00): 지나면 그날 due 하나만
    _snooze(client, 1, "2026-11-18T09:00:00+09:00")
    move_to(datetime(2026, 11, 18, 9, 30))
    day = _kinds(client, "2026-11-18", "2026-11-18")
    assert [x for x in day if x[1] == 1] == [("due", 1, "2026-11-18T18:00")]


def test_expired_snooze_without_due_keeps_snoozed_mark(client, box):
    # 기한 없는 업무 4(17일 09:00까지 미룸): 지나도 snoozed 표시를 남긴다(캘린더에서 사라지지 않게)
    move_to(datetime(2026, 11, 17, 10, 0))
    assert ("snoozed", 4, "2026-11-17T09:00") in _kinds(client)


def test_expired_snooze_resnooze_undo_done(client, box):
    _snooze(client, 1, "2026-11-17T09:00:00+09:00")
    move_to(datetime(2026, 11, 17, 10, 0))
    # 다시 미루기(19일 09:00): 18일 due가 빠지고 19일 snoozed
    act = _snooze(client, 1, "2026-11-19T09:00:00+09:00")
    assert [x for x in _kinds(client) if x[1] == 1] == [("snoozed", 1, "2026-11-19T09:00")]
    # 되돌리기: 17일 09:00(이미 지남)로 돌아가 다시 18일 due
    assert client.post(f"/api/actions/{act}/undo").status_code == 200
    assert [x for x in _kinds(client) if x[1] == 1] == [("due", 1, "2026-11-18T18:00")]
    # 완료: 어디에도 없다
    assert client.patch("/api/tasks/1", json={"status": "done"}).status_code == 200
    assert [x for x in _kinds(client) if x[1] == 1] == []


def test_expired_snooze_meeting_stays_meeting_and_event_wins(client, box):
    # 일정참석 업무 2(19일 14:00 회의)를 미뤘다가 지나면 due가 아니라 meeting으로. 일정을 넣었으면 event 하나만
    _snooze(client, 2, "2026-11-17T09:00:00+09:00")
    move_to(datetime(2026, 11, 17, 10, 0))
    assert [x for x in _kinds(client) if x[1] == 2] == [("meeting", 2, "2026-11-19T14:00")]
    r = client.post("/api/calendar/events", json={"start": "2026-11-19T14:00:00+09:00", "task_id": 2})
    assert r.status_code == 201, r.text
    assert [x[:2] for x in _kinds(client) if x[1] == 2] == [("event", 2)]


def test_expired_snooze_kst_day_boundary_and_other_user(client, box):
    # 기한이 18일 00:00(KST)인 지난 미룬 업무는 18일 칸에만. 남(2)의 지난 미룬 업무는 나에게 안 보이고 남에게만
    box.add_all([
        Task(id=7, mail_id=1, text="자정 기한", status="snoozed", snoozed_until=datetime(2026, 11, 16, 9),
             due_at=datetime(2026, 11, 18, 0, 0)),
        Task(id=8, mail_id=5, text="남의 미룬 업무", status="snoozed", snoozed_until=datetime(2026, 11, 16, 9),
             due_at=datetime(2026, 11, 18, 10)),
    ])
    box.commit()
    move_to(datetime(2026, 11, 16, 10, 0))
    assert [x for x in _kinds(client, "2026-11-17", "2026-11-17") if x[1] == 7] == []
    assert [x for x in _kinds(client, "2026-11-18", "2026-11-18") if x[1] == 7] == [("due", 7, "2026-11-18T00:00")]
    assert not any(x[1] == 8 for x in _kinds(client))
    assert ("due", 8, "2026-11-18T10:00") in _kinds(client, headers={"X-User-Id": "2"})


def test_due_cluster_and_calendar_same_tasks_after_snooze_expires(client, box):
    # 기한 몰림(리마인더)과 그날 캘린더가 같은 업무 집합을 보인다 — 지난 미룬 업무 포함, 중복 없음
    for tid in (9, 10):
        box.add(Task(id=tid, mail_id=1, text=f"18일 업무 {tid}", type="회신요청", due_at=datetime(2026, 11, 18, 12)))
    box.commit()
    _snooze(client, 1, "2026-11-17T09:00:00+09:00")
    move_to(datetime(2026, 11, 17, 8, 0))
    def cluster():
        items = client.get("/api/reminders").json()["items"]
        return next((set(i["task_ids"]) for i in items if i["key"] == "due_cluster:day:20261118"), set())
    def cal():
        ids = [x[1] for x in _kinds(client, "2026-11-18", "2026-11-18") if x[0] in ("due", "meeting", "event")]
        assert len(ids) == len(set(ids)), ids  # 중복 없음
        return set(ids)
    assert cluster() == set() and cal() == {9, 10}  # 미룬 동안은 둘뿐(몰림 3건 미만)
    move_to(datetime(2026, 11, 17, 9, 0))
    assert cluster() == cal() == {1, 9, 10}
