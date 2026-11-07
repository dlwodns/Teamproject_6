"""업무 상태 변경 · action_log 기록 · 되돌리기 · 일괄 변경 미리보기 · 실행 (BE-4, 구조도 v3.1 5 · 6절).

REST 버튼 · 에이전트(BE-11) · MCP(BE-17)가 같은 함수를 쓴다. 모든 변경은 action_log 한 줄로 남기고,
되돌리기는 그 줄의 before_json으로 한다. 확인이 필요한지는 부르는 쪽이 정한다(1건 = 바로, 여러 건 = 미리보기 → 실행).
"""
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.models import Account, ActionLog, ActionPreview, Mail, Task

PREVIEW_TTL = timedelta(minutes=5)  # [제안] docs/30_backend/detail.md 8절 #1
FIELDS = ("status", "done_at", "snoozed_until", "status_changed_at")


class StatusError(Exception):
    """API가 HTTP 상태로 바꾼다: not_found → 404, conflict → 409, invalid → 422."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def _snapshot(t: Task) -> dict:
    return {f: (v.isoformat() if isinstance(v := getattr(t, f), datetime) else v) for f in FIELDS}


def _restore(t: Task, snap: dict) -> None:
    for f in FIELDS:
        v = snap.get(f)
        setattr(t, f, datetime.fromisoformat(v) if f != "status" and v else v)


def _check(status: str, until: datetime | None) -> None:
    if status == "snoozed" and until is None:
        raise StatusError("invalid", "나중에(snoozed)는 snoozed_until이 필요합니다")
    if status != "snoozed" and until is not None:
        raise StatusError("invalid", "snoozed_until은 status가 snoozed일 때만 씁니다")


def _load(db: Session, task_ids: list[int]) -> tuple[list[Task], int]:
    """업무와 그 주인(user_id)을 읽는다. 없는 업무가 있거나 주인이 여럿이면 거절한다."""
    ids = list(dict.fromkeys(task_ids))
    rows = db.execute(
        select(Task, Account.user_id).join(Mail, Task.mail_id == Mail.id).join(Account, Mail.account_id == Account.id)
        .where(Task.id.in_(ids))
    ).all()
    found = {t.id: (t, uid) for t, uid in rows}
    if missing := [i for i in ids if i not in found]:
        raise StatusError("not_found", f"없는 업무: {missing}")
    users = {uid for _, uid in found.values()}
    if len(users) != 1:
        raise StatusError("invalid", "한 번에 한 사용자의 업무만 바꿀 수 있습니다")
    return [found[i][0] for i in ids], users.pop()


def _apply(t: Task, status: str, until: datetime | None, at: datetime) -> None:
    t.status = status
    t.snoozed_until = until if status == "snoozed" else None
    t.done_at = at if status == "done" else None
    t.status_changed_at = at


def change_status(db: Session, task_ids: list[int], status: str, until: datetime | None = None, *,
                  action: str = "set_status", source: str = "ui", preview_id: str | None = None,
                  confirmed: bool = False) -> tuple[ActionLog | None, list[Task]]:
    """상태를 바꾸고 action_log 한 줄을 남긴다. 이미 그 상태인 업무는 건드리지 않고, 바뀐 업무가 없으면 기록도 없다.
    커밋은 부르는 쪽이 한다."""
    _check(status, until)
    tasks, user_id = _load(db, task_ids)
    changed = [t for t in tasks if (t.status, t.snoozed_until) != (status, until)]
    if not changed:
        return None, tasks
    at = now()
    before = {str(t.id): _snapshot(t) for t in changed}
    for t in changed:
        _apply(t, status, until, at)
    log = ActionLog(user_id=user_id, action=action, source=source, preview_id=preview_id, confirmed=confirmed,
                    params_json={"status": status, "snoozed_until": until.isoformat() if until else None},
                    affected_ids=[t.id for t in changed], before_json=before, created_at=at)
    db.add(log)
    db.flush()
    return log, tasks


def undo(db: Session, action_id: int) -> tuple[ActionLog, ActionLog, list[Task]]:
    """action_log 한 줄을 되돌린다. 그 뒤에 같은 업무를 바꾼 기록이 있으면 덮어쓰지 않고 거절한다.
    되돌리기도 action_log 한 줄로 남겨 다시 되돌릴 수 있다. (원래 기록, 되돌리기 기록, 업무) 순으로 돌려준다."""
    log = db.get(ActionLog, action_id)
    if log is None or not log.before_json:
        raise StatusError("not_found", f"되돌릴 수 있는 기록이 없습니다: {action_id}")
    if log.undone_at is not None:
        raise StatusError("conflict", "이미 되돌린 기록입니다")
    ids = [int(i) for i in log.before_json]
    later = db.scalars(select(ActionLog).where(ActionLog.id > log.id, ActionLog.undone_at.is_(None))).all()
    if any(set(x.affected_ids or []) & set(ids) for x in later):
        raise StatusError("conflict", "이 기록 뒤에 같은 업무를 바꾼 기록이 있어 되돌릴 수 없습니다")
    tasks, user_id = _load(db, ids)
    at = now()
    before = {str(t.id): _snapshot(t) for t in tasks}
    for t in tasks:
        _restore(t, log.before_json[str(t.id)])
    log.undone_at = at
    back = ActionLog(user_id=user_id, action="undo", source="ui", params_json={"action_id": log.id},
                     affected_ids=ids, before_json=before, created_at=at)
    db.add(back)
    db.flush()
    return log, back, tasks


def preview(db: Session, task_ids: list[int], status: str, until: datetime | None = None) -> tuple[ActionPreview, list[Task]]:
    """여러 건 변경 전 확인창용 미리보기. 상태는 바꾸지 않는다."""
    _check(status, until)
    tasks, user_id = _load(db, task_ids)
    at = now()
    p = ActionPreview(preview_id=str(uuid.uuid4()), user_id=user_id, action="bulk_status", target_ids=[t.id for t in tasks],
                      params_json={"status": status, "snoozed_until": until.isoformat() if until else None},
                      created_at=at, expires_at=at + PREVIEW_TTL)
    db.add(p)
    db.flush()
    return p, tasks


def execute(db: Session, preview_id: str, *, source: str = "ui") -> tuple[ActionLog | None, list[Task]]:
    """확인된 미리보기를 실행한다. 미리보기는 한 번만, 만료 전에만 쓸 수 있다."""
    p = db.get(ActionPreview, preview_id)
    if p is None:
        raise StatusError("not_found", "없는 미리보기입니다")
    if p.used_at is not None:
        raise StatusError("conflict", "이미 실행한 미리보기입니다")
    if p.expires_at < now():
        raise StatusError("conflict", "만료된 미리보기입니다. 다시 미리보기를 받아 주세요")
    p.used_at = now()
    until = p.params_json.get("snoozed_until")
    return change_status(db, p.target_ids, p.params_json["status"], datetime.fromisoformat(until) if until else None,
                         action=p.action, source=source, preview_id=p.preview_id, confirmed=True)
