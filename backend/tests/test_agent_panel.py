"""제안 카드(D50) · 기록 탭 · 에이전트가 아는 것 · 실행 안전 규칙 (PL-16 5.1 · 5.2 · 5.4절)."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from tests.clock_util import move_to
from app.models import (Account, ActionLog, ActionPreview, Contact, Mail, MailingList, SuggestionHide, Task, Template,
                        User, UserSettings)
from app.services import task_status

NOW = datetime(2026, 11, 11, 14, 0)  # 수요일 오후(아침 요약 카드가 뜨지 않는 시각)


@pytest.fixture(autouse=True)
def fixed_clock():
    move_to(NOW)
    yield
    move_to(None)


def _base(db, user_id=1):
    db.add(User(id=user_id, name="문규남", department="AX팀", position="책임"))
    db.flush()
    db.add(Account(id=user_id, user_id=user_id, provider="dummy", email=f"me{user_id}@cne.com"))
    db.flush()


def _mail(db, mid, *, sender="kim@cne.com", sent_at=NOW - timedelta(hours=1), category="회신", direction="received",
          subject="견적 회신 요청", conv=None, account_id=1):
    db.add(Mail(id=mid, account_id=account_id, source_id=f"M-{mid}", direction=direction, sender=sender,
                subject=subject, sent_at=sent_at, category=category, conversation_id=conv))
    db.flush()


def _task(db, tid, mid, *, due=None, status="pending", text="견적 회신", until=None):
    db.add(Task(id=tid, mail_id=mid, text=text, due_at=due, status=status, snoozed_until=until))
    db.flush()


def _cards(client, **params):
    r = client.get("/api/suggestions", params={"limit": 50, **params})
    assert r.status_code == 200, r.text
    return r.json()["suggestions"]


# ---------- 제안 카드 ----------

def test_due_soon_card_with_draft_button(client, db):
    _base(db)
    db.add(Contact(user_id=1, email="kim@cne.com", name="김민준", position="팀장"))
    _mail(db, 1)
    _task(db, 1, 1, due=datetime(2026, 11, 11, 18, 0))
    db.commit()
    cards = _cards(client)
    assert [c["rule"] for c in cards] == ["due_soon"]
    c = cards[0]
    assert c["key"] == "due_soon:task:1" and c["via"] == "suggestion:due_soon"
    assert c["title"] == "김민준 팀장님 '견적 회신' 기한이 오늘 18:00이에요. 초안을 써 둘까요?"
    assert [b["label"] for b in c["buttons"]] == ["초안 보기", "나중에", "완료"]
    assert c["buttons"][0]["primary"] and c["buttons"][0]["action"] == "T07"
    assert c["created_at"].endswith("+09:00")


def test_one_card_per_task_overdue_wins_over_superior(client, db):
    # 시험 3: 기한 지남 + 상급자 → ②만
    _base(db)
    db.add(Contact(user_id=1, email="park@cne.com", name="박서연", position="상무", is_superior=True))
    _mail(db, 1, sender="park@cne.com", sent_at=NOW - timedelta(days=2))
    _task(db, 1, 1, due=NOW - timedelta(days=1), text="예산안 검토")
    db.commit()
    cards = _cards(client)
    assert [c["rule"] for c in cards] == ["overdue"]
    assert cards[0]["title"] == "박서연 상무님 '예산안 검토' 기한이 D+1 지났어요."


def test_superior_after_two_hours_only(client, db):
    _base(db)
    db.add(Contact(user_id=1, email="park@cne.com", name="박서연", position="상무", is_superior=True))
    _mail(db, 1, sender="park@cne.com", sent_at=NOW - timedelta(hours=3))
    _mail(db, 2, sender="park@cne.com", sent_at=NOW - timedelta(hours=1))
    _task(db, 1, 1)
    _task(db, 2, 2)
    db.commit()
    cards = _cards(client)
    assert [(c["rule"], c["task_ids"]) for c in cards] == [("priority_sender", [1])]
    assert "3시간" in cards[0]["title"]


def test_action_task_uses_open_mail_button(client, db):
    _base(db)
    _mail(db, 1, category="공지")  # 공지 속 나를 지목한 요청 등 답장으로 끝나지 않는 업무
    _task(db, 1, 1, due=NOW + timedelta(hours=2))
    db.commit()
    c = _cards(client)[0]
    assert c["buttons"][0]["kind"] == "navigate" and c["buttons"][0]["label"] == "메일 열기"
    assert c["title"].endswith("메일을 확인해 볼까요?")


def test_done_excluded_and_future_snoozed_have_no_card(client, db):
    _base(db)
    for i, (status, until) in enumerate([("done", None), ("excluded", None), ("snoozed", NOW + timedelta(hours=1))], 1):
        _mail(db, i)
        _task(db, i, i, due=NOW + timedelta(hours=2), status=status, until=until)
    _mail(db, 4)
    _task(db, 4, 4, due=NOW + timedelta(hours=2), status="snoozed", until=NOW - timedelta(minutes=1))  # 나중에 시각이 지남
    db.commit()
    assert [c["task_ids"] for c in _cards(client)] == [[4]]


def test_no_morning_card_morning_is_briefing(client, db):
    # BE-12(BE-D31): 제안 카드는 리마인더 목록의 앞쪽 N건이다. 아침 요약 카드는 아침 브리핑(GET /api/briefings/morning)으로 옮겼다
    _base(db)
    db.add(UserSettings(user_id=1, remind_time="08:30"))
    _mail(db, 1)
    _task(db, 1, 1, due=datetime(2026, 11, 11, 17, 0))
    _mail(db, 2)
    _task(db, 2, 2, due=datetime(2026, 11, 13, 17, 0))
    db.commit()
    move_to(datetime(2026, 11, 11, 10, 0))
    assert "morning" not in [c["rule"] for c in _cards(client)]
    b = client.get("/api/briefings/morning").json()
    assert b["summary"] == "오늘 기한 1건이 있어요." and b["sections"][0]["items"][0]["task_id"] == 1


def test_no_reply_card(client, db):
    _base(db)
    old = NOW - timedelta(days=4)
    _mail(db, 1, direction="sent", sender="me1@cne.com", subject="협력사 평가표 요청", sent_at=old, category=None, conv="c1")
    _mail(db, 2, direction="sent", sender="me1@cne.com", subject="회의록 확인 요청", sent_at=old, category=None, conv="c2")
    _mail(db, 3, sender="lee@cne.com", subject="RE: 회의록 확인 요청", sent_at=old + timedelta(days=1), conv="c2")
    _mail(db, 4, direction="sent", sender="me1@cne.com", subject="RE: 다른 건", sent_at=old, category=None, conv="c3")
    _mail(db, 5, direction="sent", sender="me1@cne.com", subject="새 요청", sent_at=NOW - timedelta(days=1), conv="c4")
    _mail(db, 6, direction="sent", sender="me1@cne.com", subject="대화 없음", sent_at=old, conv=None)
    db.commit()
    cards = _cards(client)
    assert [c["rule"] for c in cards] == ["no_reply"]
    assert cards[0]["title"] == "보낸 요청 '협력사 평가표 요청'에 4일째 답이 없어요."  # 보낸 메일 한 통에 카드 하나(BE-12)
    assert cards[0]["key"] == "no_reply:sent_mail:1" and cards[0]["buttons"][0]["action"] == "T07"
    assert cards[0]["detail"] == ["협력사 평가표 요청"] and cards[0]["mail_ids"] == [1]


def test_other_users_data_is_not_shown(client, db):
    _base(db, 1)
    _base(db, 2)
    _mail(db, 1, account_id=2)
    _task(db, 1, 1, due=NOW + timedelta(hours=1))
    db.commit()
    assert _cards(client) == []
    assert len(client.get("/api/suggestions", headers={"X-User-Id": "2"}).json()["suggestions"]) == 1


def test_limit_and_more(client, db):
    _base(db)
    for i in range(1, 6):
        _mail(db, i)
        _task(db, i, i, due=NOW + timedelta(hours=i))
    db.commit()
    body = client.get("/api/suggestions").json()
    # 5건이 모두 오늘 기한이라 '기한 몰림'(그날 마지막 기한 자리) 1건이 더 있다(BE-12)
    assert len(body["suggestions"]) == 3 and body["more"] == 3 and body["total"] == 6
    assert [c["task_ids"][0] for c in body["suggestions"]] == [1, 2, 3]  # 기한 이른 순


def test_hide_until_next_morning_and_reappear_on_next_stage(client, db):
    # 시험 4: 임박 카드를 숨긴 뒤 기한이 지나면 ②가 바로 뜸
    _base(db)
    _mail(db, 1)
    _task(db, 1, 1, due=NOW + timedelta(hours=3))
    db.commit()
    r = client.post("/api/suggestions/due_soon:task:1/hide")
    assert r.status_code == 200 and r.json()["hidden_until"] == "2026-11-12T08:30:00+09:00"
    assert _cards(client) == []
    move_to(NOW + timedelta(hours=4))
    assert [c["rule"] for c in _cards(client)] == ["overdue"]


def test_hide_rejects_bad_key(client, db):
    _base(db)
    db.commit()
    assert client.post("/api/suggestions/drop table/hide").status_code == 422
    assert client.post("/api/suggestions/unknown:task:1/hide").status_code == 422


def test_card_button_records_via(client, db):
    _base(db)
    _mail(db, 1)
    _task(db, 1, 1, due=NOW + timedelta(hours=3))
    db.commit()
    card = _cards(client)[0]
    r = client.patch("/api/tasks/1", json={"status": "done", "via": card["via"]})
    assert r.status_code == 200
    log = db.query(ActionLog).one()
    assert log.params_json["via"] == "suggestion:due_soon" and log.source == "ui"
    assert _cards(client) == []
    client.post(f"/api/actions/{log.id}/undo")
    assert [c["key"] for c in _cards(client)] == ["due_soon:task:1"]  # 시험 2: 되돌리면 카드가 다시 뜸


def test_via_format_is_checked(client, db):
    _base(db)
    _mail(db, 1)
    _task(db, 1, 1)
    db.commit()
    assert client.patch("/api/tasks/1", json={"status": "done", "via": "<script>"}).status_code == 422


# ---------- 기록 탭 ----------

def test_history_lists_waiting_first_then_done(client, db):
    _base(db)
    for i in (1, 2, 3):
        _mail(db, i)
        _task(db, i, i, text=f"업무 {i}")
    db.commit()
    client.patch("/api/tasks/1", json={"status": "done", "via": "suggestion:due_soon"})
    client.patch("/api/tasks/2", json={"status": "snoozed", "snoozed_until": "2026-11-12T09:00:00+09:00"})
    pid = client.post("/api/tasks/bulk/preview", json={"task_ids": [2, 3], "status": "done"}).json()["preview_id"]
    items = client.get("/api/actions/history").json()["items"]
    assert [i["state"] for i in items] == ["waiting", "done", "done"]
    assert items[0]["preview_id"] == pid and items[0]["text"] == "업무 2건 완료 — 확인을 기다려요"
    assert items[1]["text"] == "'업무 2' 업무를 11/12 09:00까지 미뤘어요" and items[1]["via_label"] == "화면 버튼"
    assert items[2]["text"] == "'업무 1' 업무를 완료했어요" and items[2]["via_label"] == "제안 카드(기한 임박)"
    assert all(i["can_undo"] for i in items[1:])
    assert items[2]["at"].endswith("+09:00")


def test_history_undone_and_blocked_undo(client, db):
    _base(db)
    _mail(db, 1)
    _task(db, 1, 1)
    db.commit()
    a = client.patch("/api/tasks/1", json={"status": "done"}).json()["action_id"]
    b = client.patch("/api/tasks/1", json={"status": "excluded"}).json()["action_id"]
    items = {i["action_id"]: i for i in client.get("/api/actions/history").json()["items"]}
    assert items[b]["can_undo"] and not items[a]["can_undo"]  # 뒤에 살아 있는 변경이 있으면 못 되돌림
    client.post(f"/api/actions/{b}/undo")
    items = {i["action_id"]: i for i in client.get("/api/actions/history").json()["items"]}
    assert items[b]["state"] == "undone" and not items[b]["can_undo"]
    assert items[a]["can_undo"]
    assert len(items) == 2  # 되돌리기 기록은 따로 줄을 만들지 않는다


def test_history_hides_used_and_expired_previews(client, db):
    _base(db)
    _mail(db, 1)
    _task(db, 1, 1)
    db.commit()
    pid = client.post("/api/tasks/bulk/preview", json={"task_ids": [1], "status": "done"}).json()["preview_id"]
    move_to(NOW + timedelta(minutes=6))
    assert [i["state"] for i in client.get("/api/actions/history").json()["items"]] == []
    move_to(NOW)
    client.post("/api/actions/execute", json={"preview_id": pid})
    assert [i["state"] for i in client.get("/api/actions/history").json()["items"]] == ["done"]


# ---------- 에이전트가 아는 것 ----------

def _memory_base(db):
    _base(db)
    db.add(Contact(id=5, user_id=1, email="park@cne.com", name="박서연", position="상무", is_superior=True))
    db.add(Contact(id=6, user_id=1, email="lee@cne.com", name="이도윤"))
    db.add(Template(id=4, user_id=1, kind="reply", name="확인", body="확인했습니다"))
    db.add(MailingList(user_id=1, address="ax-team@cne.com"))
    db.commit()


def test_memory_view(client, db):
    _memory_base(db)
    m = client.get("/api/agent/memory").json()
    assert m["me"]["position"] == "책임" and m["me"]["mailing_lists"] == [{"address": "ax-team@cne.com", "kind": "team"}]
    assert m["me"]["origin"] == {"at": None, "text": "처음 설정에서 넣었어요"}
    assert [p["contact_id"] for p in m["people"]] == [5]  # 표시 없는 연락처는 기억이 아니다
    assert "rules" not in m  # 자유 문장 규칙 · 답장 템플릿은 기억이 아니다(읽는 곳이 없다)
    assert m["me"]["used_by"] == ["메일 분류"] and m["people"][0]["used_by"] == ["제안 카드", "메일 분류"]


def test_memory_person_change_affects_cards_and_undo(client, db):
    # M3: 상급자 표시를 끄면 ④ 카드가 사라진다. 되돌리면 돌아온다
    _memory_base(db)
    _mail(db, 1, sender="park@cne.com", sent_at=NOW - timedelta(hours=3))
    _task(db, 1, 1)
    db.commit()
    assert [c["rule"] for c in _cards(client)] == ["priority_sender"]
    r = client.patch("/api/agent/memory/people/5", json={"is_superior": False})
    assert r.status_code == 200 and r.json()["memory"]["people"] == []
    aid = r.json()["action_id"]
    assert _cards(client) == []
    item = client.get("/api/actions/history").json()["items"][0]
    assert item["text"] == "중요한 사람 표시를 바꿨어요" and item["via_label"] == "에이전트가 아는 것" and item["can_undo"]
    u = client.post(f"/api/actions/{aid}/undo")
    assert u.status_code == 200 and u.json()["tasks"] == []
    assert [c["rule"] for c in _cards(client)] == ["priority_sender"]
    origin = client.get("/api/agent/memory").json()["people"][0]["origin"]["text"]
    assert origin == "11/11 화면에서 되돌렸어요"


def test_memory_same_value_is_noop(client, db):
    _memory_base(db)
    r = client.patch("/api/agent/memory/people/5", json={"is_superior": True})
    assert r.json()["action_id"] is None and db.query(ActionLog).count() == 0


def test_memory_other_users_contact_404(client, db):
    _memory_base(db)
    _base(db, 2)
    db.add(Contact(id=9, user_id=2, email="x@cne.com"))
    db.commit()
    assert client.patch("/api/agent/memory/people/9", json={"is_favorite": True}).status_code == 404
    assert client.patch("/api/agent/memory/people/5", json={"is_favorite": None}).status_code == 422


def test_memory_me_and_mailing_lists(client, db):
    _memory_base(db)
    r = client.patch("/api/agent/memory/me", json={"position": "팀장", "mailing_lists": ["Leaders@CNE.com", "ax-team@cne.com"]})
    assert r.status_code == 200
    me = r.json()["memory"]["me"]
    assert me["position"] == "팀장" and me["mailing_lists"] == [{"address": "ax-team@cne.com", "kind": "team"}, {"address": "leaders@cne.com", "kind": "role"}]
    assert me["department"] == "AX팀"  # 보내지 않은 칸은 그대로
    client.post(f"/api/actions/{r.json()['action_id']}/undo")
    me = client.get("/api/agent/memory").json()["me"]
    assert me["position"] == "책임" and me["mailing_lists"] == [{"address": "ax-team@cne.com", "kind": "team"}]
    assert client.patch("/api/agent/memory/me", json={"mailing_lists": ["not-an-address"]}).status_code == 422
    assert client.patch("/api/agent/memory/me", json={"name": "x"}).status_code == 422


def test_memory_blocked_undo_when_later_change(client, db):
    _memory_base(db)
    a = client.patch("/api/agent/memory/people/5", json={"is_favorite": True}).json()["action_id"]
    client.patch("/api/agent/memory/people/5", json={"is_superior": False})
    assert client.post(f"/api/actions/{a}/undo").status_code == 409


def test_memory_body_text_never_creates_memory(client, db):
    # M4: 메일 본문의 개인 사실은 기억이 되지 않는다(본문을 받는 경로 자체가 없다)
    _memory_base(db)
    _mail(db, 1, subject="제 딸 생일이 다음 주예요")
    _task(db, 1, 1)
    db.commit()
    before = client.get("/api/agent/memory").json()
    client.get("/api/suggestions")
    client.get("/api/actions/history")
    assert client.get("/api/agent/memory").json() == before


# ---------- 실행 안전 규칙 (5.4절) ----------

def _counts(db):
    db.expire_all()
    return (db.query(ActionLog).count(), db.query(ActionPreview).count(), db.query(SuggestionHide).count(),
            [(t.id, t.status) for t in db.query(Task).order_by(Task.id)])


def test_s1_reads_never_write(client, db):
    _memory_base(db)
    _mail(db, 1, sent_at=NOW - timedelta(days=3))
    _task(db, 1, 1, due=NOW - timedelta(hours=1))
    _mail(db, 2, sender="park@cne.com", sent_at=NOW - timedelta(hours=5))
    _task(db, 2, 2)
    db.commit()
    before = _counts(db)
    for _ in range(3):
        assert client.get("/api/suggestions").status_code == 200
        assert client.get("/api/actions/history").status_code == 200
        assert client.get("/api/agent/memory").status_code == 200
    assert _counts(db) == before


def test_s4_execute_can_only_narrow_preview_targets(client, db):
    # 확인한 뒤 대상을 바꿔 끼울 수 없다(S4). task_ids는 미리보기 대상 안에서 줄이기만 한다(UX-D8 확인 카드 일부 실행, #31)
    _base(db)
    for i in (1, 2, 3):
        _mail(db, i)
        _task(db, i, i)
    db.commit()
    pid = client.post("/api/tasks/bulk/preview", json={"task_ids": [1, 3], "status": "done"}).json()["preview_id"]
    for bad in ([1, 2], []):
        r = client.post("/api/actions/execute", json={"preview_id": pid, "task_ids": bad})
        assert r.status_code == 422
    assert client.post("/api/actions/execute", json={"preview_id": pid, "status": "excluded"}).status_code == 422
    assert _counts(db)[3] == [(1, "pending"), (2, "pending"), (3, "pending")]
    assert client.post("/api/actions/execute", json={"preview_id": pid, "task_ids": [3]}).status_code == 200
    assert _counts(db)[3] == [(1, "pending"), (2, "pending"), (3, "done")]
    pid = client.post("/api/tasks/bulk/preview", json={"task_ids": [1], "status": "done"}).json()["preview_id"]
    assert client.post("/api/actions/execute", json={"preview_id": pid}).status_code == 200  # 없으면 전부
    assert _counts(db)[3] == [(1, "done"), (2, "pending"), (3, "done")]


def test_s5_no_state_change_without_log(db):
    _base(db)
    _mail(db, 1)
    _task(db, 1, 1)
    db.commit()
    with pytest.raises(IntegrityError):
        task_status.change_status(db, [1], "done", source="not-a-source")  # 기록이 제약에 걸려 실패
    db.rollback()
    assert _counts(db)[0] == 0 and _counts(db)[3] == [(1, "pending")]


def test_requires_user_header_in_prod(client, db, monkeypatch):
    _base(db)
    db.commit()
    monkeypatch.setenv("APP_MODE", "prod")
    assert client.get("/api/suggestions").status_code == 401
    assert client.get("/api/suggestions", headers={"X-User-Id": "1"}).status_code == 200
    assert client.get("/api/dev/scenario/state").status_code == 404  # 운영에서는 시나리오 API가 없다


def test_scenario_api_only_on_scenario_db(monkeypatch):
    from app.api import dev_scenario

    monkeypatch.setenv("APP_MODE", "dev")
    for url, on in [("sqlite://", True), ("sqlite:///./scenario.db", True), ("sqlite:///./ax.db", False),
                    ("sqlite:///./demo.db", False), ("sqlite:////tmp/scenario/ax.db", False),
                    ("sqlite:///./ax.db?scenario=1", False), ("sqlite:///./scenario.db?timeout=5", False),
                    ("sqlite:///C:\\data\\scenario\\ax.db", False), ("sqlite:///./scenario_x.sqlite", False)]:
        monkeypatch.setenv("DATABASE_URL", url)
        assert dev_scenario.enabled() is on, url


# ---------- 리뷰에서 찾은 경계 (11/11) ----------

def test_card_created_at_is_when_condition_first_held(client, db):
    # 늦게 온 메일 · 나중에가 풀린 업무는 그 시각이 created_at (✦ 배지 '새 카드')
    _base(db)
    _mail(db, 1, sent_at=NOW - timedelta(minutes=30))
    _task(db, 1, 1, due=datetime(2026, 11, 11, 18, 0))
    _mail(db, 2, sent_at=NOW - timedelta(days=1))
    _task(db, 2, 2, due=datetime(2026, 11, 11, 20, 0), status="snoozed", until=NOW - timedelta(minutes=1))
    db.commit()
    got = {c["task_ids"][0]: c["created_at"] for c in _cards(client)}
    assert got[1] == "2026-11-11T13:30:00+09:00" and got[2] == "2026-11-11T13:59:00+09:00"


def _sent(db, mid, conv, subject="요청", account_id=1, sent_at=NOW - timedelta(days=4)):
    _mail(db, mid, direction="sent", sender=f"me{account_id}@cne.com", subject=subject, sent_at=sent_at,
          category=None, conv=conv, account_id=account_id)


def test_no_reply_hide_is_per_sent_mail(client, db):
    # 답 없음은 보낸 메일마다 항목 하나라 숨김도 그 메일 하나만 숨긴다(BE-12). 답이 오면 그 항목은 사라진다
    _base(db)
    _sent(db, 1, "c1")
    _sent(db, 2, "c2")
    db.commit()
    assert client.post("/api/suggestions/no_reply:sent_mail:1/hide").status_code == 200
    assert [c["mail_ids"] for c in _cards(client)] == [[2]]
    _mail(db, 3, sender="lee@cne.com", sent_at=NOW - timedelta(days=1), conv="c2")  # 2번에 답이 옴
    db.commit()
    assert _cards(client) == []
    _sent(db, 4, "c4")  # 새로 기다리는 메일
    db.commit()
    assert [c["mail_ids"] for c in _cards(client)] == [[4]]


def test_no_reply_matches_reply_in_same_account_and_not_my_copy(client, db):
    _base(db)
    db.add(Account(id=2, user_id=1, provider="dummy", email="me-other@cne.com"))
    db.flush()
    _sent(db, 1, "T-0001")
    _mail(db, 2, sender="x@cne.com", sent_at=NOW - timedelta(days=1), conv="T-0001", account_id=2)  # 다른 메일함의 같은 id
    _sent(db, 3, "T-0002")
    _mail(db, 4, sender="ME1@cne.com", sent_at=NOW - timedelta(days=4) + timedelta(seconds=5), conv="T-0002")  # 내 사본
    db.commit()
    assert [c["mail_ids"] for c in _cards(client)] == [[1], [3]]


def test_hide_right_before_morning_lasts_until_next_day(client, db):
    _base(db)
    _mail(db, 1)
    _task(db, 1, 1, due=datetime(2026, 11, 12, 18, 0))
    db.commit()
    move_to(datetime(2026, 11, 12, 8, 29))
    r = client.post("/api/suggestions/due_soon:task:1/hide")
    assert r.json()["hidden_until"] == "2026-11-13T08:30:00+09:00"


def test_preview_shown_until_exact_expiry(client, db):
    _base(db)
    _mail(db, 1)
    _task(db, 1, 1)
    db.commit()
    client.post("/api/tasks/bulk/preview", json={"task_ids": [1], "status": "done", "via": "history"})
    move_to(NOW + timedelta(minutes=5))
    item = client.get("/api/actions/history").json()["items"][0]
    assert item["state"] == "waiting" and item["via_label"] == "기록 탭"


def test_other_user_cannot_touch_my_tasks_or_undo(client, db, monkeypatch):
    _memory_base(db)
    _base(db, 2)
    _mail(db, 1)
    _task(db, 1, 1)
    db.commit()
    aid = client.patch("/api/agent/memory/people/5", json={"is_favorite": True}).json()["action_id"]
    other = {"X-User-Id": "2"}
    assert client.post(f"/api/actions/{aid}/undo", headers=other).status_code == 404
    assert client.patch("/api/tasks/1", json={"status": "done"}, headers=other).status_code == 404
    assert client.post("/api/tasks/bulk/preview", json={"task_ids": [1], "status": "done"}, headers=other).status_code == 404
    pid = client.post("/api/tasks/bulk/preview", json={"task_ids": [1], "status": "done"}).json()["preview_id"]
    assert client.post("/api/actions/execute", json={"preview_id": pid}, headers=other).status_code == 404
    monkeypatch.setenv("APP_MODE", "prod")
    assert client.patch("/api/tasks/1", json={"status": "done"}).status_code == 401
    assert _counts(db)[3] == [(1, "pending")]


def test_bad_inputs_are_4xx_not_500(client, db):
    _memory_base(db)
    _mail(db, 1)
    _task(db, 1, 1)
    db.commit()
    huge = "99999999999999999999"
    assert client.get("/api/suggestions", headers={"X-User-Id": huge}).status_code == 422
    assert client.post("/api/suggestions/due_soon:task:1/hide", headers={"X-User-Id": "999"}).status_code == 401
    assert client.patch(f"/api/agent/memory/people/{huge}", json={"is_favorite": True}).status_code == 422
    assert client.post(f"/api/actions/{huge}/undo").status_code == 422
    assert client.patch(f"/api/tasks/{huge}", json={"status": "done"}).status_code == 422
    assert client.post("/api/suggestions/morning:abc%0A/hide").status_code == 422
    for bad in (["a\t@b"], ["@@@"], ["x@y,z@w"]):
        assert client.patch("/api/agent/memory/me", json={"mailing_lists": bad}).status_code == 422, bad
    assert client.patch("/api/agent/memory/people/5", json={"is_superior": "no"}).status_code == 422
    assert client.patch("/api/tasks/1", json={"status": "done", "vai": "x"}).status_code == 422
    for until in (1763000000, "2026-11-20"):
        assert client.patch("/api/tasks/1", json={"status": "snoozed", "snoozed_until": until}).status_code == 422
    r = client.patch("/api/agent/memory/me", json={"department": "  "})
    assert r.json()["memory"]["me"]["department"] is None


def test_t11_sets_importance_and_undo_redo(client, db):
    # T11 중요_발신자_지정 "이도윤 대리 메일은 항상 중요로" → 연락처 즐겨찾기 표시(자유 문장 규칙을 만들지 않는다)
    from app.services import memory

    _memory_base(db)
    log = memory.apply_t11(db, 1, "LEE@cne.com", "favorite")
    db.commit()
    assert db.get(Contact, 6).is_favorite and db.query(Template).count() == 1  # 답장 템플릿 하나뿐, T11은 템플릿을 만들지 않는다
    assert memory.apply_t11(db, 1, "lee@cne.com", "favorite") is None  # 이미 그렇다
    new = memory.apply_t11(db, 1, "new@cne.com", "superior", name="새사람")
    db.commit()
    assert db.query(Contact).filter(Contact.email == "new@cne.com").one().is_superior
    with pytest.raises(task_status.StatusError):
        memory.apply_t11(db, 1, "x@cne.com", "vip")
    item = {i["action_id"]: i for i in client.get("/api/actions/history").json()["items"]}[log.id]
    assert item["text"] == "에이전트에게 말해 중요한 사람으로 정했어요" and item["via_label"] == "말로 시킴"
    back = client.post(f"/api/actions/{new.id}/undo").json()["action_id"]
    assert not db.get(Contact, db.query(Contact).filter(Contact.email == "new@cne.com").one().id).is_superior
    hist = {i["action_id"]: i for i in client.get("/api/actions/history").json()["items"]}
    assert hist[new.id]["state"] == "undone" and hist[new.id]["redo_action_id"] == back
    client.post(f"/api/actions/{back}/undo")  # 다시 하기
    db.expire_all()
    person = [p for p in client.get("/api/agent/memory").json()["people"] if p["email"] == "new@cne.com"][0]
    assert person["is_superior"] and person["origin"]["text"] == "11/11 화면에서 다시 했어요"


def test_undo_refuses_when_changed_outside_log(client, db):
    _memory_base(db)
    aid = client.patch("/api/agent/memory/people/6", json={"is_favorite": True}).json()["action_id"]
    db.get(Contact, 6).is_superior = True  # 기록 없이 바뀜(시드 등)
    db.commit()
    assert client.post(f"/api/actions/{aid}/undo").status_code == 409
    assert db.get(Contact, 6).is_favorite


def test_classify_context_reads_memory(client, db):
    # 기억이 메일 분류에 들어가는 유일한 입구. ai 스키마 OwnerProfile · SenderFlags와 칸 이름이 같아야 한다
    from app.services import memory

    _memory_base(db)
    _mail(db, 1, sender="PARK@cne.com")
    db.commit()
    ctx = memory.classify_context(db, db.get(Mail, 1))
    assert set(ctx["owner"]) == {"email", "name", "position", "team", "member_of", "role_lists", "team_lists"}
    assert set(ctx["sender"]) == {"is_superior", "is_favorite"}
    assert ctx["owner"]["member_of"] == ["ax-team@cne.com"] and ctx["owner"]["position"] == "책임"
    assert ctx["owner"]["team_lists"] == ["ax-team@cne.com"] and ctx["owner"]["role_lists"] == []
    assert ctx["sender"] == {"is_superior": True, "is_favorite": False}
    client.patch("/api/agent/memory/people/5", json={"is_superior": False})
    db.expire_all()
    assert memory.classify_context(db, db.get(Mail, 1))["sender"]["is_superior"] is False


def test_mailing_list_kind_guess_and_override(client, db):
    from app.services.memory import list_kind

    assert [list_kind(a) for a in ("cloud-leaders@x.com", "all@x.com", "cloud1@x.com", "team.leads@x.com",
                                   "all-staff@x.com", "ax_part@x.com")] == ["role", "all", "team", "role", "all", "team"]
    _memory_base(db)
    r = client.patch("/api/agent/memory/me", json={"mailing_lists": [{"address": "Cloud1@cne.com", "kind": "role"},
                                                                    "all@cne.com"]})
    assert r.json()["memory"]["me"]["mailing_lists"] == [{"address": "all@cne.com", "kind": "all"},
                                                         {"address": "cloud1@cne.com", "kind": "role"}]
    assert client.patch("/api/agent/memory/me", json={"mailing_lists": [{"address": "a@cne.com", "kind": "vip"}]}
                        ).status_code == 422
