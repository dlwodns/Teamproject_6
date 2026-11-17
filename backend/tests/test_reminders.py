"""리마인더 엔진 · 알림 정책 · API · 브리핑 · AI 신호 (BE-12, 명세 docs/10_planning/reminders.md 2 · 3 · 4 · 7 · 8절)."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.models import (Account, ActionLog, Commitment, Contact, Mail, Notification, Reminder, ReminderSignal, SuggestionHide, Task,
                        User, UserSettings)
from app.reminders import engine
from app.reminders.types import ACTIVE_TYPES
from tests.clock_util import move_to

NOW = datetime(2026, 11, 11, 14, 0)  # 수요일 오후
WED_MORNING = datetime(2026, 11, 11, 8, 30)


@pytest.fixture(autouse=True)
def fixed_clock():
    move_to(NOW)
    yield
    move_to(None)


# ---------- 처음 상태 만들기(모든 유형을 만들 수 있는 재료) ----------

def _base(db, **settings):
    db.add(User(id=1, name="문규남", department="AX팀", position="책임"))
    db.flush()
    db.add(Account(id=1, user_id=1, provider="dummy", email="me@cne.com"))
    db.add(UserSettings(user_id=1, remind_time="08:30", **settings))
    db.flush()


def _mail(db, mid, *, sender="kim@cne.com", sent_at=NOW - timedelta(hours=1), category="회신", direction="received",
          subject="견적 회신 요청", conv=None, to=("me@cne.com",), cc=(), kind=None):
    db.add(Mail(id=mid, account_id=1, source_id=f"M-{mid}", direction=direction, sender=sender, subject=subject,
                sent_at=sent_at, category=category, conversation_id=conv, recipients=list(to), cc=list(cc), kind=kind))
    db.flush()


def _sent(db, mid, conv, *, sent_at, subject="자료 요청", to=("lee@cne.com",)):
    _mail(db, mid, direction="sent", sender="me@cne.com", subject=subject, sent_at=sent_at, category=None, conv=conv, to=to)


def _task(db, tid, mid, *, due=None, status="pending", text="견적 회신", until=None, mentioned_me=False):
    db.add(Task(id=tid, mail_id=mid, text=text, due_at=due, status=status, snoozed_until=until, mentioned_me=mentioned_me,
                evidence_text="금요일까지 회신 부탁드립니다."))
    db.flush()


def _world(db):
    """이번 단계 유형 15개가 하나씩 걸리는 메일함(NOW = 11/11 수 14:00)."""
    _base(db)
    db.add(Contact(user_id=1, email="park@cne.com", name="박서연", position="상무", is_superior=True))
    _mail(db, 1); _task(db, 1, 1, due=NOW - timedelta(days=1), text="예산안 검토")  # overdue
    _mail(db, 2); _task(db, 2, 2, due=NOW + timedelta(hours=3), text="견적 회신")  # due_soon
    _mail(db, 3); _task(db, 3, 3, due=NOW + timedelta(days=5), text="계약서 검토")  # due_changed
    db.add(ReminderSignal(mail_id=3, task_id=3, kind="due_change", new_due_raw="다음 주 화요일",
                          new_due_at=NOW + timedelta(days=6), evidence_text="다음 주 화요일까지로 미뤄 주세요", status="open"))
    for i, h in ((4, 10), (5, 12), (6, 15)):  # due_cluster: 11/13에 기한 3건
        _mail(db, i); _task(db, i, i, due=datetime(2026, 11, 13, h, 0), text=f"13일 업무 {i}")
    _sent(db, 20, "c-nr", sent_at=NOW - timedelta(days=4), subject="평가표 요청")  # no_reply
    _sent(db, 21, "c-tp", sent_at=NOW - timedelta(days=5), subject="보안 점검 요청")  # their_promise
    _mail(db, 22, sender="lee@cne.com", sent_at=NOW - timedelta(days=4), conv="c-tp", subject="RE: 보안 점검 요청", category="기타")
    db.add(Commitment(id=1, mail_id=22, who="them", text="보안 점검 결과 보내기", due_raw="어제",
                      due_at=NOW - timedelta(days=1), evidence_text="결과는 제가 보내 드리겠습니다.", status="open"))
    _sent(db, 23, "c-mp", sent_at=NOW - timedelta(days=1), subject="일정표 드립니다")  # my_promise
    db.add(Commitment(id=2, mail_id=23, who="me", text="일정표 수정본 드리기", due_raw="오늘 밤",
                      due_at=NOW + timedelta(hours=10), evidence_text="오늘 밤까지 드리겠습니다.", status="open"))
    _mail(db, 7); _task(db, 7, 7, status="snoozed", until=NOW - timedelta(minutes=10), text="연기 업무")  # snooze_due
    _mail(db, 8, sender="park@cne.com", sent_at=NOW - timedelta(hours=3)); _task(db, 8, 8, text="상무님 지시")  # priority_sender
    _mail(db, 9, to=("team@cne.com",), cc=("me@cne.com",)); _task(db, 9, 9, mentioned_me=True, text="참조 부탁")  # cc_mention
    _mail(db, 10, sent_at=NOW - timedelta(days=4), category="요청"); _task(db, 10, 10, text="장기 미처리")  # stale
    _sent(db, 24, "c-st", sent_at=NOW - timedelta(days=5), subject="질문 드립니다")  # stalled_thread
    _mail(db, 11, sender="lee@cne.com", sent_at=NOW - timedelta(days=3), conv="c-st", subject="RE: 질문 드립니다")
    _task(db, 11, 11, text="질문에 답하기")
    _mail(db, 12, kind="K09", subject="주간 회의"); _task(db, 12, 12, due=NOW + timedelta(minutes=20), text="회의 참석")  # meeting_prep
    _mail(db, 13); _task(db, 13, 13, due=NOW + timedelta(days=3), text="보고서 작성")  # resolved
    db.add(ReminderSignal(mail_id=13, task_id=13, kind="resolved", reason="done_by_other",
                          evidence_text="그 건은 제가 처리했습니다", status="open"))
    _mail(db, 14, conv="c-rc", sent_at=NOW - timedelta(days=1)); _task(db, 14, 14, due=NOW + timedelta(days=3), text="답장할 일")
    _sent(db, 25, "c-rc", sent_at=NOW - timedelta(hours=1), subject="RE: 견적 회신 요청")  # reply_confirm
    db.commit()


def _items(client, **params):
    r = client.get("/api/reminders", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _by_key(client):
    return {i["key"]: i for i in _items(client)["items"]}


def _run(db, at):
    db.expire_all()
    return engine.run(db, 1, at)


def _notes(db):
    db.expire_all()
    return db.scalars(select(Notification).order_by(Notification.id)).all()


# ---------- 유형 · 우선순위 ----------

EXPECTED = {
    "overdue:task:1", "due_soon:task:2", "due_changed:task:3", "due_cluster:day:20261113", "no_reply:sent_mail:20",
    "their_promise:commitment:1", "my_promise:commitment:2", "snooze_due:task:7", "priority_sender:task:8",
    "cc_mention:task:9", "stale:task:10", "stalled_thread:task:11", "meeting_prep:task:12", "resolved:task:13",
    "reply_confirm:task:14",
}


def test_every_type_this_phase_triggers(client, db):
    _world(db)
    body = _items(client)
    assert {i["key"] for i in body["items"]} == EXPECTED
    assert {i["type"] for i in body["items"]} == set(ACTIVE_TYPES)
    assert body["counts"] == {"due": 4, "waiting": 2, "promise": 1, "revisit": 5, "prepare": 1, "cleanup": 2, "all": 15}
    assert {i["key"] for i in _items(client, group="waiting")["items"]} == {"no_reply:sent_mail:20", "their_promise:commitment:1"}
    got = _by_key(client)
    assert got["overdue:task:1"]["reason"] == "기한(11/10(화) 14:00)이 1일 경과했습니다"
    assert got["due_changed:task:3"]["evidence"] == "다음 주 화요일까지로 미뤄 주세요"
    assert got["due_cluster:day:20261113"]["task_ids"] == [4, 5, 6]
    assert got["their_promise:commitment:1"]["counterpart"]["email"] == "lee@cne.com"
    assert got["resolved:task:13"]["reason"] == "같은 대화의 새 메일에서 다른 담당자가 처리했다는 회신이 있습니다"
    assert [a["label"] for a in got["no_reply:sent_mail:20"]["actions"]] == ["회신 요청 작성", "메일 열기", "회신 대기 종료"]
    assert all(len(i["actions"]) <= 3 and sum(a["primary"] for a in i["actions"]) == 1 for i in got.values())


def test_one_item_per_task_in_priority_order(client, db):
    _base(db)
    db.add(Contact(user_id=1, email="park@cne.com", name="박서연", position="상무", is_superior=True))
    _mail(db, 1, sender="park@cne.com", sent_at=NOW - timedelta(days=2))
    _task(db, 1, 1, due=NOW - timedelta(days=1))  # 기한 경과 + 상급자
    _mail(db, 2, sender="park@cne.com", sent_at=NOW - timedelta(days=2))
    _task(db, 2, 2, due=NOW - timedelta(days=1))  # + 해결 신호 → 정리 제안이 앞선다
    db.add(ReminderSignal(mail_id=2, task_id=2, kind="resolved", reason="cancelled", evidence_text="취소", status="open"))
    _mail(db, 3, kind="K09")
    _task(db, 3, 3, due=NOW + timedelta(hours=2))  # 회의 초대: 30분 전까지는 기한 임박
    db.commit()
    assert set(_by_key(client)) == {"overdue:task:1", "resolved:task:2", "due_soon:task:3"}
    move_to(NOW + timedelta(hours=1, minutes=40))  # 회의 20분 전 → 회의 준비
    assert "meeting_prep:task:3" in _by_key(client)


def test_list_order_due_first_then_created(client, db):
    _base(db)
    _mail(db, 1, sent_at=NOW - timedelta(days=5), category="요청"); _task(db, 1, 1)  # stale(기한 없음)
    _mail(db, 2); _task(db, 2, 2, due=NOW + timedelta(hours=5))
    _mail(db, 3); _task(db, 3, 3, due=NOW + timedelta(hours=1))
    db.commit()
    assert [i["key"] for i in _items(client)["items"]] == ["due_soon:task:3", "due_soon:task:2", "stale:task:1"]


def test_suggestions_are_first_reminder_items(client, db):
    _world(db)
    keys = [i["key"] for i in _items(client)["items"]]
    cards = client.get("/api/suggestions").json()
    assert [c["key"] for c in cards["suggestions"]] == keys[:3] and cards["total"] == len(keys)
    assert all(c["via"] == f"suggestion:{c['rule']}" for c in cards["suggestions"])


# ---------- 알림 정책 ----------

def test_due_soon_three_hours_before_once(client, db):
    _base(db)
    _mail(db, 1, sent_at=NOW - timedelta(days=1))
    _task(db, 1, 1, due=datetime(2026, 11, 11, 18, 0))
    db.commit()
    assert _run(db, datetime(2026, 11, 11, 14, 59))["sent"] == []
    out = _run(db, datetime(2026, 11, 11, 15, 0))
    assert out["sent"] == ["due_soon:task:1"]
    assert _run(db, datetime(2026, 11, 11, 15, 1))["sent"] == []  # 같은 slot은 한 번
    (n,) = _notes(db)
    assert (n.kind, n.type, n.group, n.reminder_key, n.rule) == ("reminder", "due_soon", "due", "due_soon:task:1", "R-기한")
    row = db.scalar(select(Reminder))
    assert (row.slot, row.notify_count, row.state, row.notification_id) == ("2026-11-11T15:00", 1, "active", n.id)


def test_backoff_then_quiet(client, db):
    _base(db)
    _mail(db, 1, sent_at=NOW - timedelta(days=3))
    _task(db, 1, 1, due=NOW - timedelta(days=1))
    db.commit()
    sent = {}
    for day in range(11, 19):  # 11/11(수) ~ 11/18(수) 아침마다
        at = datetime(2026, 11, day, 8, 30)
        sent[day] = _run(db, at)["sent"]
    # 수 → 목(1일 뒤) → (2일 간격, 토 · 일은 근무일 아님) 월 → 3번 넘으면 조용히 둠
    assert [d for d, s in sent.items() if s] == [11, 12, 16]
    move_to(datetime(2026, 11, 18, 9, 0))
    item = _by_key(client)["overdue:task:1"]
    assert item["state"] == "quiet" and item["notify_count"] == 3
    assert db.scalars(select(Reminder.state).order_by(Reminder.id)).all()[-1] == "quiet"


def test_outside_work_hours_waits_for_next_work_start(client, db):
    _base(db)
    _mail(db, 1); _task(db, 1, 1, due=NOW + timedelta(days=5))
    db.add(ReminderSignal(mail_id=1, task_id=1, kind="due_change", new_due_at=NOW + timedelta(days=7), evidence_text="x",
                          status="open", created_at=datetime(2026, 11, 11, 20, 0)))
    db.commit()
    assert _run(db, datetime(2026, 11, 11, 20, 0))["sent"] == []
    assert _run(db, datetime(2026, 11, 12, 8, 59))["sent"] == []
    assert _run(db, datetime(2026, 11, 12, 9, 0))["sent"] == ["due_changed:task:1"]


def test_due_soon_outside_work_hours_but_not_quiet_hours(client, db):
    _base(db, quiet_start="22:00", quiet_end="07:00")
    _mail(db, 1); _task(db, 1, 1, due=datetime(2026, 11, 11, 21, 0))  # 3시간 전 = 18:00(근무 끝) → 예외로 보냄
    _mail(db, 2); _task(db, 2, 2, due=datetime(2026, 11, 12, 1, 0))  # 3시간 전 = 22:00(조용한 시간) → 보내지 않음
    db.commit()
    assert _run(db, datetime(2026, 11, 11, 18, 0))["sent"] == ["due_soon:task:1"]
    assert _run(db, datetime(2026, 11, 11, 22, 0))["sent"] == []
    assert _run(db, datetime(2026, 11, 12, 7, 0))["sent"] == []  # 그사이 기한이 지나 '기한 경과'(아침에 몰아서)
    assert sorted(_run(db, datetime(2026, 11, 12, 8, 30))["sent"]) == ["overdue:task:1", "overdue:task:2"]


def test_away_mode_then_return_briefing(client, db):
    _base(db, away_until=datetime(2026, 11, 13, 9, 0))
    _mail(db, 1, sent_at=NOW - timedelta(days=3)); _task(db, 1, 1, due=NOW - timedelta(days=1))
    db.commit()
    for at in (datetime(2026, 11, 11, 14, 0), datetime(2026, 11, 12, 8, 30), datetime(2026, 11, 13, 8, 30)):
        assert _run(db, at) == {"user_id": 1, "sent": [], "skipped": [], "notifications": []}
    out = _run(db, datetime(2026, 11, 13, 9, 0))
    assert out["sent"] == [] and out["skipped"] == [{"key": "overdue:task:1", "reason": "away"}]
    (n,) = _notes(db)
    assert (n.kind, n.type, n.title, n.reminder_keys) == ("digest", "away_return", "자리를 비운 동안 쌓인 것 1건",
                                                          ["overdue:task:1"])
    assert _run(db, datetime(2026, 11, 13, 9, 1))["notifications"] == []  # 복귀 브리핑은 한 번
    assert _run(db, datetime(2026, 11, 16, 8, 30))["sent"] == ["overdue:task:1"]  # 그다음 아침부터 다시


def test_three_at_once_become_one_digest(client, db):
    _base(db)
    for i in (1, 2, 3):
        _mail(db, i, sent_at=NOW - timedelta(days=3)); _task(db, i, i, due=NOW - timedelta(days=1), text=f"업무 {i}")
    db.commit()
    out = _run(db, datetime(2026, 11, 12, 8, 30))
    assert len(out["sent"]) == 3 and len(out["notifications"]) == 1
    (n,) = _notes(db)
    assert (n.kind, n.title, n.body, n.task_ids) == ("digest", "챙길 것 3건", "기한 경과 3", [1, 2, 3])
    assert set(db.scalars(select(Reminder.channel))) == {"digest"}


def test_two_at_once_stay_separate(client, db):
    _base(db)
    for i in (1, 2):
        _mail(db, i, sent_at=NOW - timedelta(days=3)); _task(db, i, i, due=NOW - timedelta(days=1))
    db.commit()
    assert len(_run(db, datetime(2026, 11, 12, 8, 30))["notifications"]) == 2


def test_recheck_right_before_send_skips_with_reason(client, db):
    _base(db)
    _mail(db, 1); _task(db, 1, 1, due=datetime(2026, 11, 11, 18, 0))
    db.commit()
    at = datetime(2026, 11, 11, 15, 0)
    sends = engine.plan(db, 1, at)
    assert [s.item["key"] for s in sends] == ["due_soon:task:1"]
    db.get(Task, 1).status = "done"  # 그사이 완료
    db.flush()
    out = engine.deliver(db, 1, sends, at)
    db.commit()
    assert out["sent"] == [] and out["skipped"] == [{"key": "due_soon:task:1", "reason": "done"}]
    assert _notes(db) == [] and db.scalar(select(Reminder.skipped_reason)) == "done"


def test_same_slot_written_once_even_if_planned_twice(client, db):
    _base(db)
    _mail(db, 1); _task(db, 1, 1, due=datetime(2026, 11, 11, 18, 0))
    db.commit()
    at = datetime(2026, 11, 11, 15, 0)
    first, second = engine.plan(db, 1, at), engine.plan(db, 1, at)  # 두 틱이 같은 순간에 계산
    engine.deliver(db, 1, first, at)
    assert engine.deliver(db, 1, second, at)["sent"] == []
    db.commit()
    assert len(_notes(db)) == 1 and len(db.scalars(select(Reminder)).all()) == 1


def test_type_mute_keeps_item_in_list(client, db):
    _base(db)
    _mail(db, 1, sent_at=NOW - timedelta(days=3)); _task(db, 1, 1, due=NOW - timedelta(days=1))
    db.commit()
    r = client.patch("/api/reminders/types/overdue", json={"notify": False})
    assert r.json() == {"type": "overdue", "notify": False, "muted_types": ["overdue"]}
    assert _run(db, datetime(2026, 11, 12, 8, 30))["sent"] == []
    item = _by_key(client)["overdue:task:1"]
    assert item["notify"] is False and _items(client)["muted_types"] == ["overdue"]
    client.patch("/api/reminders/types/overdue", json={"notify": True})
    assert _run(db, datetime(2026, 11, 13, 8, 30))["sent"] == ["overdue:task:1"]
    assert client.patch("/api/reminders/types/nope", json={"notify": False}).status_code == 404
    assert client.patch("/api/reminders/types/overdue", json={"notify": "no"}).status_code == 422


def test_not_mine_excludes_and_mutes_same_sender_and_type(client, db):
    _base(db)
    _mail(db, 1, sent_at=NOW - timedelta(days=4), category="요청"); _task(db, 1, 1)
    db.commit()
    r = client.post("/api/reminders/stale:task:1/dismiss", json={"reason": "not_mine"})
    assert r.status_code == 200 and r.json()["action_id"]
    log = db.get(ActionLog, r.json()["action_id"])
    assert (log.action, log.params_json["via"], db.get(Task, 1).status) == ("T10", "reminder:stale", "excluded")
    _mail(db, 2, sent_at=NOW - timedelta(days=4), category="요청"); _task(db, 2, 2)  # 같은 발신자 · 같은 유형
    _mail(db, 3, sender="lee@cne.com", sent_at=NOW - timedelta(days=4), category="요청"); _task(db, 3, 3)
    db.commit()
    items = _by_key(client)
    assert items["stale:task:2"]["notify"] is False and items["stale:task:3"]["notify"] is True
    assert _run(db, datetime(2026, 11, 12, 8, 30))["sent"] == ["stale:task:3"]


# ---------- 적용 · 되돌리기 ----------

def test_apply_due_changed_t16_and_undo(client, db):
    _base(db)
    _mail(db, 1); _task(db, 1, 1, due=NOW + timedelta(days=2))
    new = NOW + timedelta(days=6)
    db.add(ReminderSignal(id=1, mail_id=1, task_id=1, kind="due_change", new_due_raw="다음 주 화요일", new_due_at=new,
                          evidence_text="x", status="open"))
    db.commit()
    r = client.post("/api/reminders/due_changed:task:1/apply")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["due_at"] == "2026-11-17T14:00:00+09:00" and body["task"]["status"] == "pending"
    log = db.get(ActionLog, body["action_id"])
    assert (log.action, log.params_json["kind"], log.affected_ids) == ("T16", "due_change", [1])
    assert "due_changed:task:1" not in _by_key(client)
    hist = client.get("/api/actions/history").json()["items"][0]
    assert hist["text"] == "'견적 회신' 업무 기한을 11/17 14:00(으)로 변경했습니다" and hist["can_undo"]
    assert hist["via_label"] == "리마인더(기한 변경)"
    u = client.post(f"/api/actions/{log.id}/undo")
    assert u.status_code == 200, u.text
    db.expire_all()
    assert db.get(Task, 1).due_at == NOW + timedelta(days=2) and db.get(ReminderSignal, 1).status == "open"
    assert "due_changed:task:1" in _by_key(client)  # 되돌리면 항목이 다시 뜬다
    assert client.post(f"/api/actions/{u.json()['action_id']}/undo").status_code == 200  # 다시 하기
    db.expire_all()
    assert db.get(Task, 1).due_at == new


def test_apply_resolved_and_reply_confirm_complete_with_undo(client, db):
    _world(db)
    for key, tid in (("resolved:task:13", 13), ("reply_confirm:task:14", 14)):
        r = client.post(f"/api/reminders/{key}/apply")
        assert r.status_code == 200 and r.json()["task"]["status"] == "done"
        log = db.get(ActionLog, r.json()["action_id"])
        assert log.action == "T03" and log.params_json["via"] == f"reminder:{key.split(':')[0]}"
        assert client.post(f"/api/actions/{log.id}/undo").status_code == 200
        db.expire_all()
        assert db.get(Task, tid).status == "pending"


@pytest.mark.parametrize("key, cid", [("their_promise:commitment:1", 1), ("my_promise:commitment:2", 2)])
def test_apply_promise_done_and_undo(client, db, key, cid):
    _world(db)
    r = client.post(f"/api/reminders/{key}/apply")
    assert r.status_code == 200 and r.json()["commitment_id"] == cid and r.json()["task"] is None
    db.expire_all()
    assert db.get(Commitment, cid).status == "done" and key not in _by_key(client)
    row = client.get("/api/actions/history").json()["items"][0]
    assert row["text"].startswith("약속 '") and row["can_undo"] is True  # #84 리뷰: 토스트가 사라져도 기록 탭에서 되돌린다
    assert client.post(f"/api/actions/{r.json()['action_id']}/undo").status_code == 200
    db.expire_all()
    assert db.get(Commitment, cid).status == "open" and key in _by_key(client)
    row = client.get("/api/actions/history").json()["items"][0]
    assert row["state"] == "undone" and row["can_undo"] is False and row["redo_action_id"]


def test_apply_rejects_rule_types_and_unknown(client, db):
    _world(db)
    assert client.post("/api/reminders/overdue:task:1/apply").status_code == 422
    assert client.post("/api/reminders/overdue:task:999/apply").status_code == 404
    assert client.post("/api/reminders/drop table/apply").status_code in (404, 422)


# ---------- 숨김 · 신고 ----------

def test_dismiss_reasons(client, db):
    _world(db)
    r = client.post("/api/reminders/overdue:task:1/dismiss", json={"reason": "hide"})
    assert r.json()["hidden_until"] == "2026-11-12T08:30:00+09:00"
    assert client.post("/api/reminders/due_changed:task:3/dismiss", json={"reason": "keep"}).status_code == 200
    assert client.post("/api/reminders/no_reply:sent_mail:20/dismiss", json={"reason": "stop_waiting"}).status_code == 200
    assert client.post("/api/reminders/my_promise:commitment:2/dismiss", json={"reason": "wrong_signal"}).status_code == 200
    keys = set(_by_key(client))
    assert not keys & {"overdue:task:1", "due_changed:task:3", "no_reply:sent_mail:20", "my_promise:commitment:2"}
    db.expire_all()
    assert db.get(ReminderSignal, 1).status == "rejected" and db.get(Commitment, 2).status == "dismissed"
    move_to(datetime(2026, 11, 12, 9, 0))
    keys = set(_by_key(client))
    assert "overdue:task:1" in keys and "no_reply:sent_mail:20" not in keys  # 숨김만 풀린다
    assert client.post("/api/reminders/overdue:task:1/dismiss", json={"reason": "stop_waiting"}).status_code == 422
    assert client.post("/api/reminders/no_reply:sent_mail:20/dismiss", json={"reason": "hide"}).status_code == 404
    assert client.post("/api/reminders/stale:task:10/dismiss", json={"reason": "later"}).status_code == 422


def test_reply_confirm_asks_again_only_for_new_reply(client, db):
    _world(db)
    assert client.post("/api/reminders/reply_confirm:task:14/dismiss", json={"reason": "keep"}).status_code == 200
    assert "reply_confirm:task:14" not in _by_key(client)
    _sent(db, 26, "c-rc", sent_at=NOW - timedelta(minutes=5), subject="RE: 추가")
    db.commit()
    assert "reply_confirm:task:14" in _by_key(client)


# ---------- 알림 센터 API ----------

def _demo_client(monkeypatch):
    """시연 도구(DEMO_TOOLS)만 단 app. 강제 실행은 BE-14 시연 라우터에 있다(테스트 app에는 없다)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import demo

    monkeypatch.setenv("DEMO_TOOLS", "1")
    app = FastAPI()
    demo.install(app)
    return TestClient(app)


def test_notifications_api_shape_read_and_answer(client, db, monkeypatch):
    _world(db)
    r = _demo_client(monkeypatch).post("/api/dev/reminders/run", params={"at": "2026-11-11T14:00:00+09:00"})
    assert r.status_code == 200 and r.json()["at"] == "2026-11-11T14:00:00+09:00"
    body = client.get("/api/notifications").json()
    assert body["unread"] == len(body["items"]) >= 1
    n = body["items"][0]
    assert set(n) == {"id", "kind", "type", "group", "reminder_key", "reminder_keys", "title", "body", "task_ids", "rule",
                      "scheduled_at", "read_at", "answered_at", "created_at"}
    assert n["created_at"] == "2026-11-11T14:00:00+09:00"
    p = client.patch(f"/api/notifications/{n['id']}", json={"read": True})
    assert p.status_code == 200 and p.json()["read_at"] is not None
    assert client.patch(f"/api/notifications/{n['id']}", json={}).status_code == 422
    assert client.patch("/api/notifications/9999", json={"read": True}).status_code == 404
    assert client.post("/api/notifications/read-all").json()["updated"] == body["unread"] - 1
    assert client.get("/api/notifications").json()["unread"] == 0


def test_reply_confirm_notification_answer_yes_completes(client, db):
    _base(db)
    _mail(db, 1, conv="c1", sent_at=NOW - timedelta(days=1)); _task(db, 1, 1)
    _sent(db, 2, "c1", sent_at=NOW - timedelta(minutes=30), subject="RE: 견적")
    db.commit()
    _run(db, NOW)
    (n,) = _notes(db)
    assert (n.kind, n.type, n.task_ids) == ("reply_confirm", "reply_confirm", [1])
    r = client.patch(f"/api/notifications/{n.id}", json={"answer": "yes"})
    assert r.status_code == 200 and r.json()["answered_at"] is not None
    db.expire_all()
    assert db.get(Task, 1).status == "done"
    assert client.patch(f"/api/notifications/{n.id}", json={"answer": "no"}).status_code == 409


def test_reminder_item_shape(client, db):
    _world(db)
    body = _items(client)
    assert set(body) == {"as_of", "counts", "muted_types", "items"}
    i = _by_key(client)["due_soon:task:2"]
    assert set(i) == {"key", "type", "type_label", "group", "title", "reason", "evidence", "task_id", "task_ids", "task_type", "mail_id",
                      "commitment_id", "due_at", "counterpart", "created_at", "state", "notify_count", "last_notified_at", "notify",
                      "actions"}
    assert i["due_at"] == "2026-11-11T17:00:00+09:00" and i["type_label"] == "기한 임박"
    assert i["actions"][0] == {"id": "draft", "label": "회신 작성", "action": "T07", "primary": True,
                               "params": {"mail_id": 2, "tone": "polite"}}
    assert client.get("/api/reminders", params={"group": "nope"}).status_code == 422


def test_due_cluster_open_day_matches_calendar_day(client, db):
    """기한 몰림 [당일 업무 보기](T13)의 start · end로 캘린더(GET /api/calendar, 두 날 포함)를 열면 그날 업무만 나온다.
    날짜는 둘 다 KST: 11/13 00:00 · 23:59:59는 그날, 11/12 23:59:59 · 11/14 00:00은 아니다. 끝난 업무는 어디에도 없다."""
    _base(db)
    for tid, due, status in ((1, datetime(2026, 11, 13, 0, 0), "pending"), (2, datetime(2026, 11, 13, 12, 0), "pending"),
                             (3, datetime(2026, 11, 13, 23, 59, 59), "pending"), (4, datetime(2026, 11, 12, 23, 59, 59), "pending"),
                             (5, datetime(2026, 11, 14, 0, 0), "pending"), (6, datetime(2026, 11, 13, 10, 0), "done")):
        _mail(db, tid); _task(db, tid, tid, due=due, status=status, text=f"업무 {tid}")
    db.commit()
    got = _by_key(client)
    assert "due_cluster:day:20261112" not in got and "due_cluster:day:20261114" not in got
    cluster = got["due_cluster:day:20261113"]
    assert cluster["task_ids"] == [1, 2, 3]
    open_day = next(a for a in cluster["actions"] if a["id"] == "open_day")
    assert open_day["action"] == "T13" and open_day["primary"] is True
    assert open_day["params"] == {"start": "2026-11-13", "end": "2026-11-13"}
    r = client.get("/api/calendar", params=open_day["params"])
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [(i["kind"], i["task_id"]) for i in items] == [("due", 1), ("due", 2), ("due", 3)]
    assert all(i["start"].startswith("2026-11-13T") and i["start"].endswith("+09:00") for i in items)


def test_reads_never_write(client, db):
    _world(db)
    before = db.execute(text("SELECT (SELECT COUNT(*) FROM reminders) + (SELECT COUNT(*) FROM notifications)"
                             " + (SELECT COUNT(*) FROM action_log)")).scalar()
    for path in ("/api/reminders", "/api/notifications", "/api/briefings/morning", "/api/briefings/evening",
                 "/api/briefings/weekly", "/api/suggestions"):
        assert client.get(path).status_code == 200
    after = db.execute(text("SELECT (SELECT COUNT(*) FROM reminders) + (SELECT COUNT(*) FROM notifications)"
                            " + (SELECT COUNT(*) FROM action_log)")).scalar()
    assert before == after == 0


def test_dev_run_only_with_demo_tools(client, db, monkeypatch):
    """강제 실행은 DEMO_TOOLS=true일 때만 있다. APP_MODE=dev여도 없으면 404, prod여도 켜면 있다(BE-14 · BE-D23)."""
    _base(db)
    db.commit()
    assert client.post("/api/dev/reminders/run", headers={"X-User-Id": "1"}).status_code == 404  # 테스트 app: dev, 도구 없음
    monkeypatch.setenv("APP_MODE", "prod")
    r = _demo_client(monkeypatch).post("/api/dev/reminders/run", params={"at": "2026-11-11T14:00:00+09:00"})
    assert r.status_code == 200 and r.json()["at"] == "2026-11-11T14:00:00+09:00"


# ---------- 브리핑 · 회고 ----------

def test_briefings_only_state_what_exists(client, db):
    _world(db)
    m = client.get("/api/briefings/morning").json()
    assert m["kind"] == "morning" and m["title"] == "일일 업무 요약 · 11/11(수)"
    counts = {s["id"]: s["count"] for s in m["sections"]}
    assert counts == {"due_today": 2, "overdue": 1, "no_reply": 1, "my_promise": 1, "auto_done": 0}
    assert m["summary"] == "금일 마감 업무 2건 · 기한 경과 업무 1건 · 회신 미수신 메일 1건 · 이행 약속 1건이 있습니다."
    db.get(Task, 2).status, db.get(Task, 2).done_at = "done", NOW - timedelta(hours=1)
    db.commit()
    e = client.get("/api/briefings/evening").json()
    ev = {s["id"]: s for s in e["sections"]}
    assert ev["done_today"]["count"] == 1 and ev["remaining"]["items"][0]["actions"][0]["label"] == "익일 오전으로 연기"
    assert ev["remaining"]["items"][0]["actions"][0]["params"]["until"] == "2026-11-12T08:30:00"
    w = client.get("/api/briefings/weekly", params={"date": "2026-11-13"}).json()
    assert {s["id"] for s in w["sections"]} == {"done_week", "near_miss", "waiting"}
    for b in (m, e, w):
        assert "챙기세요" not in b["summary"] and "부터" not in b["summary"]
    assert client.get("/api/briefings/monthly").status_code == 422


def test_morning_briefing_lists_reply_auto_with_undo(client, db):
    _base(db)
    _mail(db, 1); _task(db, 1, 1, status="done")
    db.add(ActionLog(user_id=1, action="reply_done", source="reply_auto", params_json={"status": "done"},
                     affected_ids=[1], before_json={"1": {"status": "pending"}}, created_at=datetime(2026, 11, 11, 17, 0)))
    db.commit()
    move_to(datetime(2026, 11, 12, 8, 30))
    b = client.get("/api/briefings/morning").json()
    auto = next(s for s in b["sections"] if s["id"] == "auto_done")
    assert auto["count"] == 1 and auto["items"][0]["actions"][0]["action"] == "T04"


def test_evening_and_weekly_notifications(client, db):
    _base(db)
    _mail(db, 1); _task(db, 1, 1, due=datetime(2026, 11, 14, 18, 0))
    _mail(db, 2); _task(db, 2, 2, status="done")
    db.get(Task, 2).done_at = datetime(2026, 11, 12, 10, 0)  # 이번 주 끝낸 일(주간 회고에 들어감)
    db.commit()
    out = _run(db, datetime(2026, 11, 13, 17, 30))  # 금요일 근무 끝 30분 전 → 퇴근 + 주간
    kinds = sorted(n.type for n in _notes(db))
    assert kinds == ["evening", "weekly"] and len(out["notifications"]) == 2
    assert _run(db, datetime(2026, 11, 13, 17, 31))["notifications"] == []


# ---------- 엣지(11-14 리뷰) ----------

def test_older_due_change_signal_does_not_come_back_after_apply_or_keep(client, db):
    # 같은 업무에 기한 변경 신호가 두 번(먼저 금요일, 나중에 월요일) 왔다. 최신 것을 적용하거나 그대로 두면 옛 신호가 다시 뜨면 안 된다
    _base(db)
    _mail(db, 1); _task(db, 1, 1, due=NOW + timedelta(days=1))
    for sid, days in ((1, 2), (2, 5)):
        db.add(ReminderSignal(id=sid, mail_id=1, task_id=1, kind="due_change", new_due_at=NOW + timedelta(days=days),
                              evidence_text="x", status="open"))
    _mail(db, 2); _task(db, 2, 2, due=NOW + timedelta(days=1))
    for sid, days in ((3, 2), (4, 5)):
        db.add(ReminderSignal(id=sid, mail_id=2, task_id=2, kind="due_change", new_due_at=NOW + timedelta(days=days),
                              evidence_text="x", status="open"))
    db.commit()
    assert client.post("/api/reminders/due_changed:task:1/apply").status_code == 200
    assert client.post("/api/reminders/due_changed:task:2/dismiss", json={"reason": "keep"}).status_code == 200
    keys = set(_by_key(client))
    assert "due_changed:task:1" not in keys and "due_changed:task:2" not in keys
    db.expire_all()
    assert db.get(Task, 1).due_at == NOW + timedelta(days=5)


def test_not_mine_mute_lifts_when_exclusion_is_undone(client, db):
    # '담당 아님'을 잘못 눌러 되돌렸으면 같은 발신자 · 유형의 알림도 다시 켜져야 한다
    _base(db)
    _mail(db, 1, sent_at=NOW - timedelta(days=4), category="요청"); _task(db, 1, 1)
    _mail(db, 2, sent_at=NOW - timedelta(days=4), category="요청"); _task(db, 2, 2)
    db.commit()
    r = client.post("/api/reminders/stale:task:1/dismiss", json={"reason": "not_mine"})
    assert _by_key(client)["stale:task:2"]["notify"] is False
    assert client.post(f"/api/actions/{r.json()['action_id']}/undo").status_code == 200
    items = _by_key(client)
    assert items["stale:task:1"]["notify"] is True and items["stale:task:2"]["notify"] is True


def test_briefing_date_out_of_range_is_422_not_500(client, db):
    _base(db)
    db.commit()
    for kind, d in (("evening", "9999-12-31"), ("weekly", "9999-12-31"), ("morning", "0001-01-01")):
        assert client.get(f"/api/briefings/{kind}", params={"date": d}).status_code == 422


def test_snoozed_item_is_never_quiet(client, db):
    # 미룬 시각은 사용자가 직접 고른 때라 몇 번째로 미뤘든 그 시각에 알린다(3번 상한은 재촉에만)
    _base(db)
    _mail(db, 1, sent_at=NOW - timedelta(days=1)); _task(db, 1, 1)
    db.commit()
    sent = []
    for k in range(4):
        until = datetime(2026, 11, 11, 15, 0) + timedelta(minutes=30 * k)
        t = db.get(Task, 1)
        t.status, t.snoozed_until = "snoozed", until
        db.commit()
        sent += _run(db, until)["sent"]
    assert sent == ["snooze_due:task:1"] * 4
    move_to(datetime(2026, 11, 11, 16, 31))
    assert _by_key(client)["snooze_due:task:1"]["state"] == "active"


# ---------- 미룬 시각 알림 · 브리핑 기한 경과 (11-15 임동하 결함 보고) ----------
# 기한이 24시간 안인 업무를 미루면 다시 열릴 때 카드는 기한 임박이다. 카드는 하나로 두고 미룬 시각에 알림을 따로 보낸다.

TOMORROW_10 = datetime(2026, 11, 12, 10, 0)  # 목요일 10:00 → R-기한은 3시간 전 07:00


def _snoozed_task(db, *, due=TOMORROW_10, until=datetime(2026, 11, 11, 17, 0)):
    _base(db)
    _mail(db, 1, sent_at=NOW - timedelta(days=1)); _task(db, 1, 1, due=due, status="snoozed", until=until)
    db.commit()


def _task_notes(db):
    return [(n.type, n.scheduled_at) for n in _notes(db) if n.task_ids == [1]]


def test_snoozed_due_soon_task_alerts_exactly_at_snooze_time_once(client, db):
    _snoozed_task(db)
    assert _run(db, datetime(2026, 11, 11, 16, 59))["sent"] == []
    assert _run(db, datetime(2026, 11, 11, 17, 0))["sent"] == ["snooze_due:task:1"]  # 정각에 1회
    assert _run(db, datetime(2026, 11, 11, 17, 1))["sent"] == []  # 다음 틱에 다시 나가지 않음
    move_to(datetime(2026, 11, 11, 17, 2))
    keys = [i["key"] for i in client.get("/api/reminders").json()["items"] if i["task_id"] == 1]
    assert keys == ["due_soon:task:1"]  # 카드는 하나(기한 임박)
    n = _notes(db)[-1]
    assert n.type == "snooze_due" and n.body.startswith("연기 업무 · 연기한 시각(") and n.title == "견적 회신"


def test_due_alert_still_follows_after_snooze_alert(db):
    _snoozed_task(db)
    _run(db, datetime(2026, 11, 11, 17, 0))
    assert _run(db, datetime(2026, 11, 12, 7, 0))["sent"] == ["due_soon:task:1"]  # 기한 3시간 전 알림은 그대로
    assert [t for t, _ in _task_notes(db)] == ["snooze_due", "due_soon"]


def test_resnooze_moves_the_alert_and_done_skips_it(db):
    _snoozed_task(db)
    t = db.get(Task, 1)
    t.snoozed_until = datetime(2026, 11, 11, 17, 30)  # 17시 전에 다시 미룸
    db.commit()
    assert _run(db, datetime(2026, 11, 11, 17, 0))["sent"] == []
    assert _run(db, datetime(2026, 11, 11, 17, 30))["sent"] == ["snooze_due:task:1"]
    # 다시 미룬 시각에 한 번 알린 뒤 또 미루면 새 시각에 다시 알린다(미룬 일은 3번 상한 없음)
    t = db.get(Task, 1)
    t.snoozed_until = datetime(2026, 11, 11, 17, 40)
    db.commit()
    assert _run(db, datetime(2026, 11, 11, 17, 40))["sent"] == ["snooze_due:task:1"]
    # 계획을 세운 뒤 보내기 직전에 완료하면 건너뛴다(발송 직전 재확인)
    t = db.get(Task, 1)
    t.snoozed_until = datetime(2026, 11, 11, 17, 50)
    db.commit()
    at = datetime(2026, 11, 11, 17, 50)
    sends = engine.plan(db, 1, at)
    db.get(Task, 1).status = "done"
    db.flush()
    out = engine.deliver(db, 1, sends, at)
    assert out["sent"] == [] and out["skipped"] == [{"key": "snooze_due:task:1", "reason": "done"}]


def test_snooze_and_due_alert_at_same_time_send_once_and_both_are_recorded(db):
    # 기한 20:00 → R-기한 17:00 = 미룬 시각 17:00
    _snoozed_task(db, due=datetime(2026, 11, 11, 20, 0))
    out = _run(db, datetime(2026, 11, 11, 17, 0))
    assert len(out["notifications"]) == 1 and out["sent"] == ["due_soon:task:1"]
    rows = db.scalars(select(Reminder).where(Reminder.task_id == 1).order_by(Reminder.id)).all()
    assert sorted((r.type, r.rule) for r in rows) == [("due_soon", "R-기한"), ("snooze_due", "R-나중에")]
    assert all(r.sent_at is not None and r.notification_id == out["notifications"][0] for r in rows)
    assert _run(db, datetime(2026, 11, 11, 17, 1))["sent"] == []  # 두 조건 모두 처리됨 → 다음 틱에 다시 나가지 않음
    assert len(_task_notes(db)) == 1


def test_snooze_alert_follows_snooze_mute_not_card_mute(db):
    _base(db)
    _mail(db, 1, sent_at=NOW - timedelta(days=1))
    _task(db, 1, 1, due=TOMORROW_10, status="snoozed", until=datetime(2026, 11, 11, 17, 0))
    s = db.get(UserSettings, 1)
    s.reminder_mute = {"due_soon": True}  # 기한 임박 알림만 끔
    db.commit()
    assert _run(db, datetime(2026, 11, 11, 17, 0))["sent"] == ["snooze_due:task:1"]  # 직접 고른 시각 알림은 간다
    t = db.get(Task, 1)
    t.snoozed_until = datetime(2026, 11, 11, 17, 30)
    db.get(UserSettings, 1).reminder_mute = {"snooze_due": True}  # 연기 업무 알림을 끄면 가지 않는다
    db.commit()
    assert _run(db, datetime(2026, 11, 11, 17, 30))["sent"] == []


def test_tomorrow_morning_briefing_marks_not_yet_overdue(client, db):
    from app.reminders import briefings

    _base(db)
    _mail(db, 1, sent_at=NOW - timedelta(days=1)); _task(db, 1, 1, due=datetime(2026, 11, 11, 18, 0), text="오늘 저녁 마감")
    _mail(db, 2, sent_at=NOW - timedelta(days=1)); _task(db, 2, 2, due=datetime(2026, 11, 11, 10, 0), text="이미 지남")
    db.commit()
    b = briefings.build(db, 1, "morning", datetime(2026, 11, 12).date(), at=NOW)  # 수 14:00에 목요일 아침 요약 미리 보기
    overdue = next(s for s in b["sections"] if s["id"] == "overdue")
    # 18:00 마감은 목요일 아침엔 지나 있으니 빠지면 안 된다. 다만 지금은 아직 안 지났다고 이유에 적는다(#198 리뷰)
    assert [(x["title"], x["reason"].endswith("(아직 안 지남)")) for x in overdue["items"]] == [("이미 지남", False), ("오늘 저녁 마감", True)]


def test_old_snooze_time_after_deploy_is_merged_or_skipped_not_sent_late(db):
    # 배포 전 결함 케이스: 기한 11-10 10:00 업무를 11-08 17:00로 미뤄 둠 → snooze_due 기록이 한 줄도 없다(#198 리뷰 재현)
    _snoozed_task(db, due=datetime(2026, 11, 10, 10, 0), until=datetime(2026, 11, 8, 17, 0))
    out = _run(db, NOW)
    assert out["sent"] == ["overdue:task:1"] and len(out["notifications"]) == 1  # 같은 틱이면 한 번만
    assert _run(db, NOW + timedelta(minutes=1))["sent"] == []


def test_stale_snooze_alert_alone_is_skipped(db):
    # 카드(기한 임박 R-기한 = 내일 07:00)는 아직이고, 미룬 시각만 이틀 전 → 늦은 알림 없이 기록만
    _snoozed_task(db, until=datetime(2026, 11, 9, 17, 0))
    out = _run(db, NOW)
    assert out["sent"] == [] and out["skipped"] == [{"key": "snooze_due:task:1", "reason": "stale"}]
    assert _run(db, NOW + timedelta(minutes=1))["skipped"] == []


def test_hiding_card_also_hides_snooze_alert(db):
    # 계획을 세운 뒤 보내기 직전에 카드를 숨기면 미룬 시각 알림도 건너뛴다(발송 직전 재확인)
    _snoozed_task(db)
    at = datetime(2026, 11, 11, 17, 0)
    sends = engine.plan(db, 1, at)
    db.add(SuggestionHide(user_id=1, key="due_soon:task:1", until=datetime(2026, 11, 12, 8, 30)))
    db.flush()
    out = engine.deliver(db, 1, sends, at)
    assert out["sent"] == [] and out["skipped"] == [{"key": "snooze_due:task:1", "reason": "hidden"}]


def test_weekend_snooze_is_not_stale_even_if_card_is_quiet(db):
    """금 19시로 미룬 업무는 월 09시(근무 시작)에 알린다. '오래됨'은 미룬 시각이 아니라 보낼 예정 시각으로 본다 —
    카드(기한 경과)가 이미 3번 알려 조용히 둠이어도 사용자가 고른 시각 알림은 간다(#198 후속)."""
    _base(db)
    _mail(db, 1, sent_at=datetime(2026, 11, 9, 9, 0))
    _task(db, 1, 1, due=datetime(2026, 11, 10, 18, 0), status="snoozed", until=datetime(2026, 11, 13, 19, 0))  # 금 19:00
    for i, d in enumerate((11, 12, 13)):  # 기한 경과 아침 알림 3번 → 카드는 조용히 둠
        db.add(Reminder(user_id=1, task_id=1, type="overdue", subject_kind="task", subject_id=1, rule="R-아침",
                        slot=f"2026-11-{d}T08:30", scheduled_at=datetime(2026, 11, d, 8, 30),
                        sent_at=datetime(2026, 11, d, 8, 30), notify_count=i + 1))
    db.commit()
    got, t = [], datetime(2026, 11, 13, 19, 0)
    while t <= datetime(2026, 11, 16, 12, 0):  # 금 19:00 ~ 월 12:00, 30분마다
        out = _run(db, t)
        got += [(t, k) for k in out["sent"]] + [(t, s["reason"]) for s in out["skipped"]]
        t += timedelta(minutes=30)
    assert got == [(datetime(2026, 11, 16, 9, 0), "snooze_due:task:1")]  # 월 09:00에 한 번, 'stale'로 건너뛰지 않음


def test_item_last_notified_at(client, db):
    _base(db)
    _mail(db, 1, sent_at=NOW - timedelta(days=1)); _task(db, 1, 1, due=datetime(2026, 11, 11, 18, 0))
    _mail(db, 2, sent_at=NOW - timedelta(days=1)); _task(db, 2, 2, due=datetime(2026, 11, 11, 20, 0))
    db.commit()
    _run(db, datetime(2026, 11, 11, 15, 0))
    items = _by_key(client)
    assert items["due_soon:task:1"]["last_notified_at"] == "2026-11-11T15:00:00+09:00"
    assert items["due_soon:task:2"]["last_notified_at"] is None


def test_briefing_scheduled_at(client, db):
    _base(db, evening_time="18:30")  # 회고 시각은 근무 끝과 따로 정한다(11-14)
    db.commit()
    m = client.get("/api/briefings/morning").json()
    assert m["scheduled_at"] == "2026-11-11T08:30:00+09:00" and m["as_of"] == "2026-11-11T14:00:00+09:00"
    e = client.get("/api/briefings/evening").json()
    assert e["scheduled_at"] == "2026-11-11T18:30:00+09:00" and e["as_of"] < e["scheduled_at"]  # 아직 만들 시각이 아님
    w = client.get("/api/briefings/weekly").json()  # 수요일에 본 주간 회고 = 이번 주 금요일
    assert w["scheduled_at"] == "2026-11-13T18:30:00+09:00" and w["as_of"] == "2026-11-11T14:00:00+09:00"
    past = client.get("/api/briefings/weekly", params={"date": "2026-11-04"}).json()  # 지난주 수요일 → 지난주 금요일 기준
    assert past["scheduled_at"] == past["as_of"] == "2026-11-06T18:30:00+09:00"
    future = client.get("/api/briefings/morning", params={"date": "2026-11-12"}).json()  # 내일 아침은 아직
    assert future["scheduled_at"] == "2026-11-12T08:30:00+09:00" and future["as_of"] == "2026-11-11T14:00:00+09:00"


def test_settings_briefing_times(client, db):
    """하루 요약 · 회고 시각은 설정에서 바꾸고(11-14), 브리핑 만드는 시각에 바로 반영된다."""
    _base(db)
    db.commit()
    s = client.get("/api/settings").json()
    assert (s["remind_time"], s["evening_time"]) == ("08:30", "17:30")
    r = client.patch("/api/settings", json={"remind_time": "09:00", "evening_time": "18:00"})
    assert r.status_code == 200 and (r.json()["remind_time"], r.json()["evening_time"]) == ("09:00", "18:00")
    assert client.get("/api/briefings/morning").json()["scheduled_at"] == "2026-11-11T09:00:00+09:00"
    assert client.get("/api/briefings/evening").json()["scheduled_at"] == "2026-11-11T18:00:00+09:00"
    assert client.patch("/api/settings", json={"evening_time": "25:00"}).status_code == 422
    assert client.patch("/api/settings", json={"nope": 1}).status_code == 422


def test_settings_reply_confirm_skip_saved(client, db):
    """'오늘 다시 보지 않음'(D48): 조회한 칸을 저장할 수 있고, 다시 조회해도 남는다. null이면 해제(#190 리뷰 1 — 전에는 422)."""
    _base(db)
    db.commit()
    assert client.get("/api/settings").json()["reply_confirm_skip_until"] is None
    r = client.patch("/api/settings", json={"reply_confirm_skip_until": "2026-11-11T23:59:59+09:00"})
    assert r.status_code == 200 and r.json()["reply_confirm_skip_until"] == "2026-11-11T23:59:59+09:00"
    assert client.get("/api/settings").json()["reply_confirm_skip_until"] == "2026-11-11T23:59:59+09:00"
    r = client.patch("/api/settings", json={"reply_confirm_skip_until": "2026-11-11T14:59:59Z"})  # 다른 시간대도 KST로 저장
    assert r.json()["reply_confirm_skip_until"] == "2026-11-11T23:59:59+09:00"
    assert client.patch("/api/settings", json={"reply_confirm_skip_until": None}).json()["reply_confirm_skip_until"] is None
