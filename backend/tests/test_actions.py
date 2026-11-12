"""업무 상태 변경 · 일괄 변경 · 되돌리기 API (BE-4). 구조도 v3.1 12절 #7 · #8 · #10 · #15 · #18."""
from datetime import datetime, timedelta

from app.models import Account, ActionLog, ActionPreview, Mail, Task, User

T0 = datetime(2026, 11, 3, 9, 0)


def _seed(db, n=3) -> list[int]:
    db.add(User(id=1, name="테스트"))
    db.flush()
    db.add(Account(id=1, user_id=1, provider="dummy", email="me@example.com"))
    db.flush()
    db.add(Mail(id=1, account_id=1, source_id="M-0001", direction="received", sender="lead@example.com",
                subject="요청", sent_at=T0))
    db.flush()
    tasks = [Task(mail_id=1, text=f"할 일 {i}") for i in range(n)]
    db.add_all(tasks)
    db.commit()
    return [t.id for t in tasks]


def _task(db, task_id) -> Task:
    db.expire_all()
    return db.get(Task, task_id)


def test_patch_done_logs_once(client, db):
    # #7: 1건 완료는 바로 실행 · done_at · action_log 1건
    tid = _seed(db, 1)[0]
    r = client.patch(f"/api/tasks/{tid}", json={"status": "done"})
    assert r.status_code == 200
    body = r.json()
    assert body["action_id"] is not None
    assert body["tasks"][0]["status"] == "done"
    assert body["tasks"][0]["done_at"].endswith("+09:00")  # D47: 응답 시각은 KST
    assert _task(db, tid).done_at is not None
    logs = db.query(ActionLog).all()
    assert len(logs) == 1
    assert logs[0].source == "ui" and logs[0].before_json[str(tid)]["status"] == "pending"


def test_undo_restores_and_records(client, db):
    # #8: 되돌리기 → pending · done_at 비움 · undone_at 기록
    tid = _seed(db, 1)[0]
    action_id = client.patch(f"/api/tasks/{tid}", json={"status": "done"}).json()["action_id"]
    r = client.post(f"/api/actions/{action_id}/undo")
    assert r.status_code == 200
    assert r.json()["undone_action_id"] == action_id
    t = _task(db, tid)
    assert t.status == "pending" and t.done_at is None
    assert db.get(ActionLog, action_id).undone_at is not None
    assert client.post(f"/api/actions/{action_id}/undo").status_code == 409  # 두 번 되돌리지 않는다


def test_undo_of_undo_redoes(client, db):
    tid = _seed(db, 1)[0]
    action_id = client.patch(f"/api/tasks/{tid}", json={"status": "done"}).json()["action_id"]
    back_id = client.post(f"/api/actions/{action_id}/undo").json()["action_id"]
    assert client.post(f"/api/actions/{back_id}/undo").status_code == 200
    assert _task(db, tid).status == "done"


def test_undo_blocked_by_later_change(client, db):
    # 뒤에 같은 업무를 바꾼 기록이 있으면 앞 기록을 되돌려 덮어쓰지 않는다
    tid = _seed(db, 1)[0]
    first = client.patch(f"/api/tasks/{tid}", json={"status": "done"}).json()["action_id"]
    client.patch(f"/api/tasks/{tid}", json={"status": "excluded"})
    assert client.post(f"/api/actions/{first}/undo").status_code == 409
    assert _task(db, tid).status == "excluded"


def test_snooze_needs_until_and_keeps_kst(client, db):
    # #10: 나중에는 snoozed_until 필수. 시간대가 붙어 와도 KST로 저장한다(D47)
    tid = _seed(db, 1)[0]
    assert client.patch(f"/api/tasks/{tid}", json={"status": "snoozed"}).status_code == 422
    r = client.patch(f"/api/tasks/{tid}", json={"status": "snoozed", "snoozed_until": "2026-11-07T00:00:00Z"})
    assert r.status_code == 200
    assert r.json()["tasks"][0]["snoozed_until"] == "2026-11-07T09:00:00+09:00"
    assert _task(db, tid).snoozed_until == datetime(2026, 11, 7, 9, 0)


def test_leaving_states_clears_fields(client, db):
    tid = _seed(db, 1)[0]
    client.patch(f"/api/tasks/{tid}", json={"status": "snoozed", "snoozed_until": "2026-11-07T09:00:00"})
    client.patch(f"/api/tasks/{tid}", json={"status": "done"})
    t = _task(db, tid)
    assert t.snoozed_until is None and t.done_at is not None
    client.patch(f"/api/tasks/{tid}", json={"status": "pending"})
    assert _task(db, tid).done_at is None


def test_invalid_status_rejected(client, db):
    # #18: 없는 상태는 422 · 상태 변경 없음 · 기록 없음
    tid = _seed(db, 1)[0]
    assert client.patch(f"/api/tasks/{tid}", json={"status": "archived"}).status_code == 422
    assert client.patch(f"/api/tasks/{tid}", json={"status": "done", "snoozed_until": "2026-11-07T09:00:00"}).status_code == 422
    assert _task(db, tid).status == "pending"
    assert db.query(ActionLog).count() == 0


def test_missing_task_404(client, db):
    _seed(db, 1)
    assert client.patch("/api/tasks/999", json={"status": "done"}).status_code == 404


def test_same_status_no_log(client, db):
    tid = _seed(db, 1)[0]
    r = client.patch(f"/api/tasks/{tid}", json={"status": "pending"})
    assert r.status_code == 200 and r.json()["action_id"] is None
    assert db.query(ActionLog).count() == 0


def test_bulk_preview_then_execute(client, db):
    # #15(버튼 경로): 여러 건은 미리보기 → 상태 변경 없음 → 실행 후 3건 완료 · 기록 1줄 · 한 번만 실행
    ids = _seed(db, 3)
    r = client.post("/api/tasks/bulk/preview", json={"task_ids": ids, "status": "done"})
    assert r.status_code == 200
    p = r.json()
    assert [t["id"] for t in p["targets"]] == ids and p["expires_at"].endswith("+09:00")
    assert all(_task(db, i).status == "pending" for i in ids)

    r = client.post("/api/actions/execute", json={"preview_id": p["preview_id"]})
    assert r.status_code == 200
    assert all(_task(db, i).status == "done" for i in ids)
    log = db.get(ActionLog, r.json()["action_id"])
    assert log.confirmed and log.preview_id == p["preview_id"] and sorted(log.affected_ids) == sorted(ids)
    assert client.post("/api/actions/execute", json={"preview_id": p["preview_id"]}).status_code == 409

    assert client.post(f"/api/actions/{log.id}/undo").status_code == 200  # 일괄 변경도 한 번에 되돌린다
    assert all(_task(db, i).status == "pending" for i in ids)


def test_expired_preview_rejected(client, db):
    ids = _seed(db, 2)
    pid = client.post("/api/tasks/bulk/preview", json={"task_ids": ids, "status": "excluded"}).json()["preview_id"]
    db.expire_all()
    db.get(ActionPreview, pid).expires_at = datetime(2000, 1, 1)
    db.commit()
    assert client.post("/api/actions/execute", json={"preview_id": pid}).status_code == 409
    assert all(_task(db, i).status == "pending" for i in ids)


def test_bulk_unknown_task_rejected(client, db):
    ids = _seed(db, 1)
    assert client.post("/api/tasks/bulk/preview", json={"task_ids": [*ids, 999], "status": "done"}).status_code == 404
    assert db.query(ActionPreview).count() == 0


def test_preview_expires_in_five_minutes(client, db):
    ids = _seed(db, 1)
    p = client.post("/api/tasks/bulk/preview", json={"task_ids": ids, "status": "done"}).json()
    db.expire_all()
    row = db.get(ActionPreview, p["preview_id"])
    assert row.expires_at - row.created_at == timedelta(minutes=5)


def test_undo_chain_after_later_action_undone(client, db):
    # 동하님 제보(#26 후속 1번): 완료(C) → 제외(A) → A 되돌리기 → C 되돌리기가 409였다. A가 이미 되돌려졌으니 C도 되돌려져야 한다
    tid = _seed(db, 1)[0]
    c = client.patch(f"/api/tasks/{tid}", json={"status": "done"}).json()["action_id"]
    a = client.patch(f"/api/tasks/{tid}", json={"status": "excluded"}).json()["action_id"]
    assert client.post(f"/api/actions/{a}/undo").status_code == 200
    assert _task(db, tid).status == "done"
    r = client.post(f"/api/actions/{c}/undo")
    assert r.status_code == 200, r.text
    assert _task(db, tid).status == "pending" and _task(db, tid).done_at is None


def test_undo_blocked_again_after_redo(client, db):
    # 완료(C) → 제외(A) → A 되돌리기(U) → U 되돌리기(= A 다시 하기). A가 다시 살아 있으니 C는 되돌리면 안 된다
    tid = _seed(db, 1)[0]
    c = client.patch(f"/api/tasks/{tid}", json={"status": "done"}).json()["action_id"]
    a = client.patch(f"/api/tasks/{tid}", json={"status": "excluded"}).json()["action_id"]
    u = client.post(f"/api/actions/{a}/undo").json()["action_id"]
    assert client.post(f"/api/actions/{u}/undo").status_code == 200
    assert _task(db, tid).status == "excluded"
    assert client.post(f"/api/actions/{c}/undo").status_code == 409
    assert client.post(f"/api/actions/{a}/undo").status_code == 200  # 다시 살아난 A는 다시 되돌릴 수 있다
    assert _task(db, tid).status == "done"


def test_undo_records_caller_source(db):
    # #26 후속 2번: 에이전트(T04) · MCP가 되돌리면 기록 source도 그 값이어야 한다
    from app.services import task_status

    tid = _seed(db, 1)[0]
    log, _ = task_status.change_status(db, [tid], "done")
    _, back, _ = task_status.undo(db, log.id, source="agent_rule")
    db.commit()
    assert back.source == "agent_rule"


def test_preview_executes_once_even_if_raced(client, db):
    # #26 후속 4번: 다른 요청이 먼저 실행해도, 아직 used_at이 비어 보이던 쪽은 실행되지 않는다
    from app.core.db import SessionLocal
    from app.services import task_status
    from app.services.task_status import StatusError

    ids = _seed(db, 2)
    pid = client.post("/api/tasks/bulk/preview", json={"task_ids": ids, "status": "done"}).json()["preview_id"]
    slow = SessionLocal()
    seen = slow.get(ActionPreview, pid)  # 이 세션은 used_at이 비어 있는 것을 먼저 읽어 들고 있다(변수에 잡아 두어야 세션이 버리지 않는다)
    assert seen.used_at is None
    assert client.post("/api/actions/execute", json={"preview_id": pid}).status_code == 200
    try:
        task_status.execute(slow, pid)
        raise AssertionError("두 번째 실행이 통과했다")
    except StatusError as e:
        assert e.kind == "conflict"
    finally:
        slow.rollback()
        slow.close()
    assert db.query(ActionLog).filter(ActionLog.preview_id == pid).count() == 1
