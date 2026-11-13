"""업무 상태 변경 · action_log 기록 · 되돌리기 · 일괄 변경 미리보기 · 실행 (BE-4, 구조도 v3.1 5 · 6절).

REST 버튼 · 에이전트(BE-11) · MCP(BE-17)가 같은 함수를 쓴다. 모든 변경은 action_log 한 줄로 남기고,
되돌리기는 그 줄의 before_json으로 한다. 확인이 필요한지는 부르는 쪽이 정한다(1건 = 바로, 여러 건 = 미리보기 → 실행).
"""
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, update
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


def _load(db: Session, task_ids: list[int], owner: int | None = None) -> tuple[list[Task], int]:
    """업무와 그 주인(user_id)을 읽는다. 없는 업무가 있거나 주인이 여럿이면 거절한다.
    owner를 주면 그 사용자의 업무가 아닐 때 없는 업무로 본다(다른 사람 업무가 있는지도 알려 주지 않는다)."""
    ids = list(dict.fromkeys(task_ids))
    rows = db.execute(
        select(Task, Account.user_id).join(Mail, Task.mail_id == Mail.id).join(Account, Mail.account_id == Account.id)
        .where(Task.id.in_(ids))
    ).all()
    found = {t.id: (t, uid) for t, uid in rows}
    if missing := [i for i in ids if i not in found]:
        raise StatusError("not_found", f"없는 업무: {missing}")
    users = {uid for _, uid in found.values()}
    if owner is not None and users != {owner}:
        raise StatusError("not_found", f"없는 업무: {[i for i in ids if found[i][1] != owner]}")
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
                  confirmed: bool = False, via: str | None = None,
                  owner: int | None = None) -> tuple[ActionLog | None, list[Task]]:
    """상태를 바꾸고 action_log 한 줄을 남긴다. 이미 그 상태인 업무는 건드리지 않고, 바뀐 업무가 없으면 기록도 없다.
    via는 어느 화면에서 눌렀는지(예: suggestion:due_soon, D50)이고 params_json에 남는다. 커밋은 부르는 쪽이 한다.
    상태 변경과 기록은 같은 트랜잭션이다. 기록이 실패하면 부르는 쪽이 되돌려 상태도 바뀌지 않는다(PL-16 S5)."""
    _check(status, until)
    tasks, user_id = _load(db, task_ids, owner)
    changed = [t for t in tasks if (t.status, t.snoozed_until) != (status, until)]
    if not changed:
        return None, tasks
    at = now()
    before = {str(t.id): _snapshot(t) for t in changed}
    for t in changed:
        _apply(t, status, until, at)
    params = {"status": status, "snoozed_until": until.isoformat() if until else None}
    if via:
        params["via"] = via
    log = ActionLog(user_id=user_id, action=action, source=source, preview_id=preview_id, confirmed=confirmed,
                    params_json=params, affected_ids=[t.id for t in changed], before_json=before, created_at=at)
    db.add(log)
    db.flush()
    return log, tasks


UNDO = "undo"


def _top_actions(db: Session, user_id: int, ids: list[int]) -> dict[int, int | None]:
    """업무마다 지금 되돌릴 수 있는 행동(되돌리기 · 다시 하기를 반영한 가장 최근 행동)의 id.
    기록을 순서대로 다시 훑는다: 보통 행동은 쌓고, 되돌리기는 그 행동을 빼고, 되돌리기를 되돌리면(다시 하기) 뺀 행동을 다시 쌓는다."""
    stacks: dict[int, list[int]] = {i: [] for i in ids}
    by_id: dict[int, ActionLog] = {}
    for x in db.scalars(select(ActionLog).where(ActionLog.user_id == user_id).order_by(ActionLog.id)):
        by_id[x.id] = x
        hit = [i for i in (x.affected_ids or []) if i in stacks]
        if not hit:
            continue
        if x.action != UNDO:
            for i in hit:
                stacks[i].append(x.id)
            continue
        target = by_id.get((x.params_json or {}).get("action_id"))
        if target is None:
            continue
        if target.action == UNDO:  # 다시 하기: 그 되돌리기가 뺀 행동을 다시 올린다
            for i in hit:
                stacks[i].append(target.params_json["action_id"])
        else:
            for i in hit:
                if stacks[i] and stacks[i][-1] == target.id:
                    stacks[i].pop()
    return {i: (s[-1] if s else None) for i, s in stacks.items()}


def undo(db: Session, action_id: int, *, source: str = "ui",
         owner: int | None = None) -> tuple[ActionLog, ActionLog, list[Task]]:
    """action_log 한 줄을 되돌린다. (원래 기록, 되돌리기 기록, 업무) 순으로 돌려준다.
    - 보통 행동: 그 업무의 '지금 되돌릴 수 있는 행동'일 때만. 뒤에 살아 있는 변경이 있으면 덮어쓰지 않고 409.
      뒤 변경이 이미 되돌려졌으면 통과한다(#26 후속: 완료 → 제외 → 제외 되돌리기 → 완료 되돌리기).
    - 되돌리기 기록(다시 하기): 그 뒤에 같은 업무를 바꾼 기록이 없을 때만.
    되돌리기도 action_log 한 줄로 남겨 다시 되돌릴 수 있다. source는 부른 곳(ui · agent_rule · agent_model · mcp)."""
    log = db.get(ActionLog, action_id)
    if log is None or not log.before_json or (owner is not None and log.user_id != owner):
        raise StatusError("not_found", f"되돌릴 수 있는 기록이 없습니다: {action_id}")
    if log.undone_at is not None:
        raise StatusError("conflict", "이미 되돌린 기록입니다")
    if (log.params_json or {}).get("target"):  # '에이전트가 아는 것' 변경(PL-16 5.2)은 업무가 아니라 기억 항목을 되돌린다
        from app.services import memory

        back = memory.undo(db, log, source=source)
        return log, back, []
    if (log.params_json or {}).get("kind") in ("due_change", "commitment"):  # 리마인더 적용(BE-12): T16 기한 · 약속을 되돌린다
        from app.reminders import actions as reminder_actions

        return reminder_actions.undo(db, log, source=source)
    ids = [int(i) for i in log.before_json]
    tasks, user_id = _load(db, ids)
    if log.action == UNDO:
        later = db.scalars(select(ActionLog).where(ActionLog.user_id == user_id, ActionLog.id > log.id)).all()
        blocked = any(set(x.affected_ids or []) & set(ids) for x in later)
    else:
        blocked = any(top != log.id for top in _top_actions(db, user_id, ids).values())
    if blocked:
        raise StatusError("conflict", "이 기록 뒤에 같은 업무를 바꾼 기록이 있어 되돌릴 수 없습니다")
    at = now()
    before = {str(t.id): _snapshot(t) for t in tasks}
    for t in tasks:
        _restore(t, log.before_json[str(t.id)])
    log.undone_at = at
    if log.action == UNDO and (redone := db.get(ActionLog, log.params_json["action_id"])) is not None:
        redone.undone_at = None  # 다시 하기: 그 행동이 다시 살아 있으므로 다시 되돌릴 수 있다
    back = ActionLog(user_id=user_id, action=UNDO, source=source, params_json={"action_id": log.id},
                     affected_ids=ids, before_json=before, created_at=at)
    db.add(back)
    db.flush()
    return log, back, tasks


def preview(db: Session, task_ids: list[int], status: str, until: datetime | None = None, *,
            action: str = "bulk_status", source: str | None = None, via: str | None = None,
            owner: int | None = None) -> tuple[ActionPreview, list[Task]]:
    """여러 건 변경 전 확인창용 미리보기. 상태는 바꾸지 않는다.
    에이전트가 만든 미리보기는 action(T03 등)과 source(agent_rule · agent_model)를 남겨, 사용자가 확인해 실행해도 그 값으로
    기록한다(#31 BE-11과 같은 인자)."""
    _check(status, until)
    tasks, user_id = _load(db, task_ids, owner)
    at = now()
    params = {"status": status, "snoozed_until": until.isoformat() if until else None, "source": source}
    if via:
        params["via"] = via
    p = ActionPreview(preview_id=str(uuid.uuid4()), user_id=user_id, action=action, target_ids=[t.id for t in tasks],
                      params_json=params, created_at=at, expires_at=at + PREVIEW_TTL)
    db.add(p)
    db.flush()
    return p, tasks


def execute(db: Session, preview_id: str, *, source: str = "ui", task_ids: list[int] | None = None,
            owner: int | None = None) -> tuple[ActionLog | None, list[Task]]:
    """확인된 미리보기를 실행한다. 미리보기는 한 번만, 만료 전에만 쓸 수 있다.
    task_ids: 확인 카드에서 체크를 풀고 남긴 업무(UX-D8). 미리보기 대상 안에서 줄이기만 할 수 있고(대상 바꿔치기 금지,
    PL-16 S4), 없으면 전부."""
    p = db.get(ActionPreview, preview_id)
    if p is None or (owner is not None and p.user_id != owner):
        raise StatusError("not_found", "없는 미리보기입니다")
    if p.used_at is not None:
        raise StatusError("conflict", "이미 실행한 미리보기입니다")
    if task_ids is not None:
        picked = list(dict.fromkeys(task_ids))
        if not picked or not set(picked) <= set(p.target_ids):
            raise StatusError("invalid", "미리보기 대상 안에서 1건 이상 골라 주세요")
    else:
        picked = p.target_ids
    at = now()
    if p.expires_at < at:
        raise StatusError("conflict", "만료된 미리보기입니다. 다시 미리보기를 받아 주세요")
    # 확인과 표시를 한 문장으로 한다. 같은 미리보기가 거의 동시에 두 번 와도 한 번만 실행된다(#26 후속 4번)
    claimed = db.execute(
        update(ActionPreview)
        .where(ActionPreview.preview_id == preview_id, ActionPreview.used_at.is_(None))
        .values(used_at=at)
        .execution_options(synchronize_session=False)
    ).rowcount
    if claimed != 1:
        raise StatusError("conflict", "이미 실행한 미리보기입니다")
    until = p.params_json.get("snoozed_until")
    return change_status(db, picked, p.params_json["status"], datetime.fromisoformat(until) if until else None,
                         action=p.action, source=p.params_json.get("source") or source, preview_id=p.preview_id,
                         confirmed=True, via=p.params_json.get("via"), owner=owner)
