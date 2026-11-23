"""리마인더 항목 버튼 — 숨기기 · 신고 · 적용, T16 기한 바꾸기 · 약속 끝내기와 그 되돌리기 (명세 reminders.md 7.2절, BE-D29).

- 자동으로 적용하지 않는다. 기한을 바꾸거나 완료하는 것은 사용자가 버튼을 누를 때만 한다(D36 · D48).
- 업무 완료(T03) · 제외(T10)는 `services/task_status.change_status`를 그대로 쓴다(REST 버튼 · 에이전트와 같은 길, 같은 되돌리기).
- T16 기한 바꾸기 · 약속 끝내기는 업무 상태가 아니라서 여기서 action_log를 쓰고, 되돌리기는 `task_status.undo`가 이 모듈의
  undo()로 넘긴다(params_json.kind = due_change | commitment). 기록 줄 하나 = 되돌리기 하나라는 규칙은 같다.
- 커밋은 부르는 쪽이 한다.
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.models import ActionLog, Commitment, ReminderFeedback, ReminderSignal, Task, UserSettings
from app.reminders import engine, rules
from app.reminders.types import ACTIVE_TYPES
from app.services import suggestions, task_status
from app.services.task_status import UNDO, StatusError

REASONS = ("hide", "not_mine", "wrong_signal", "keep", "stop_waiting")
DUE_FIELDS = ("due_at", "due_raw", "due_source")
SIGNAL_TYPES = ("due_changed", "resolved")
COMMITMENT_TYPES = ("their_promise", "my_promise")


def _find(db: Session, user_id: int, key: str, at: datetime) -> dict:
    if rules.parse_key(key) is None:
        raise StatusError("invalid", f"리마인더 키 형식이 아닙니다: {key}")
    for i in engine.items(db, user_id, at, include_hidden=True):
        if i["key"] == key:
            return i
    raise StatusError("not_found", f"지금 없는 리마인더입니다: {key}")


def _feedback(db: Session, user_id: int, item: dict, reason: str, at: datetime) -> None:
    db.add(ReminderFeedback(user_id=user_id, key=item["key"], type=item["type"], reason=reason, sender=item["_sender"],
                            ref_id=item["_ref"] or item["mail_id"], created_at=at))


def _signal(db: Session, item: dict) -> ReminderSignal | None:
    kind = "resolved" if item["type"] == "resolved" else "due_change"
    return db.scalar(select(ReminderSignal).where(ReminderSignal.task_id == item["task_id"], ReminderSignal.kind == kind,
                                                  ReminderSignal.status == "open").order_by(ReminderSignal.id.desc()))


def _close_older(db: Session, sig: ReminderSignal) -> None:
    """같은 업무 · 같은 종류의 더 옛 신호도 닫는다. 남겨 두면 최신 신호에 답한 뒤 옛 신호(예전 새 기한)가 항목으로 다시 뜬다."""
    for old in db.scalars(select(ReminderSignal).where(ReminderSignal.task_id == sig.task_id, ReminderSignal.kind == sig.kind,
                                                       ReminderSignal.status == "open", ReminderSignal.id < sig.id)):
        old.status = "rejected"


def dismiss(db: Session, user_id: int, key: str, reason: str, at: datetime | None = None) -> dict:
    """항목 숨김 · 신고(명세 4.2절 5 · 6번).
    hide: 다음 R-아침까지 숨김(제안 카드 숨김과 같은 표 · 같은 규칙, BE-D16) · not_mine: 업무를 제외(T10)하고 같은 발신자 · 유형은
    알림 대신 목록에만 · wrong_signal: AI 신호(약속 · 기한 변경 · 해결 · 답장 감지)가 틀림 · keep: 신호는 맞지만 그대로 둠
    (그대로 두기 · 아직 남았어요) · stop_waiting: 그만 기다리기(답 없음 · 상대 약속)."""
    at = at or now()
    if reason not in REASONS:
        raise StatusError("invalid", f"reason은 {' | '.join(REASONS)} 중 하나입니다")
    item = _find(db, user_id, key, at)
    t = item["type"]
    out = {"key": key, "reason": reason, "hidden_until": None, "action_id": None}
    if reason == "hide":
        row = suggestions.hide(db, user_id, key, at)
        out["hidden_until"] = row.until
        return out
    if reason == "not_mine":
        if item["task_id"] is None:
            raise StatusError("invalid", "업무 항목만 '내 일 아님'으로 신고할 수 있습니다")
        log, _ = task_status.change_status(db, [item["task_id"]], "excluded", action="T10", via=f"reminder:{t}",
                                           owner=user_id)
        out["action_id"] = log.id if log else None
    elif reason in ("wrong_signal", "keep"):
        if t in SIGNAL_TYPES:
            sig = _signal(db, item)
            if sig is not None:
                sig.status = "rejected"
                _close_older(db, sig)
        elif t in COMMITMENT_TYPES:
            db.get(Commitment, item["commitment_id"]).status = "dismissed"
        elif t not in ("reply_confirm", "stalled_thread"):
            raise StatusError("invalid", f"'{t}'은(는) AI 신호 항목이 아니라 {reason}을(를) 쓸 수 없습니다")
    elif reason == "stop_waiting":
        if t == "their_promise":
            db.get(Commitment, item["commitment_id"]).status = "dismissed"
        elif t != "no_reply":
            raise StatusError("invalid", "'그만 기다리기'는 답 없음 · 상대 약속에만 씁니다")
    _feedback(db, user_id, item, reason, at)
    db.flush()
    return out


def apply(db: Session, user_id: int, key: str, at: datetime | None = None) -> dict:
    """[새 기한으로 바꾸기] · [완료로 하기] · [받았어요] · [했어요]. action_log 한 줄 + 되돌리기(명세 7.2절)."""
    at = at or now()
    item = _find(db, user_id, key, at)
    t = item["type"]
    via = f"reminder:{t}"
    if t == "due_changed":
        sig = _signal(db, item)
        if sig is None:
            raise StatusError("conflict", "적용할 기한 변경 신호가 없습니다")
        log = change_due(db, user_id, item["task_id"], sig.new_due_at, due_raw=sig.new_due_raw, via=via, signal_id=sig.id)
        sig.status = "applied"
        _close_older(db, sig)
    elif t in ("resolved", "reply_confirm"):
        log, _ = task_status.change_status(db, [item["task_id"]], "done", action="T03", via=via, owner=user_id)
        if t == "resolved" and (sig := _signal(db, item)) is not None:
            sig.status = "applied"
            _close_older(db, sig)
    elif t in COMMITMENT_TYPES:
        log = finish_commitment(db, user_id, item["commitment_id"], via=via)
    else:
        raise StatusError("invalid", f"'{t}'에는 적용할 것이 없습니다(버튼의 행동을 부릅니다)")
    db.flush()
    task = db.get(Task, item["task_id"]) if item["task_id"] else None
    return {"key": key, "action_id": log.id if log else None, "task": task, "commitment_id": item["commitment_id"]}


# ---------- T16 기한 바꾸기 ----------

def _due_snapshot(t: Task) -> dict:
    return {"due_at": t.due_at.isoformat() if t.due_at else None, "due_raw": t.due_raw, "due_source": t.due_source,
            "due_time_stated": t.due_time_stated}


def _due_restore(t: Task, snap: dict) -> None:
    t.due_at = datetime.fromisoformat(snap["due_at"]) if snap.get("due_at") else None
    t.due_raw, t.due_source = snap.get("due_raw"), snap.get("due_source") or "none"
    t.due_time_stated = snap.get("due_time_stated")


def change_due(db: Session, user_id: int, task_id: int, due_at: datetime | None, *, due_raw: str | None = None,
               via: str | None = None, signal_id: int | None = None, source: str = "ui") -> ActionLog:
    """T16 기한_변경(state_change, params task_id · due_at). 1건이고 되돌릴 수 있어 바로 실행한다(D37)."""
    tasks, _ = task_status._load(db, [task_id], user_id)
    t = tasks[0]
    before = {str(t.id): _due_snapshot(t)}
    t.due_at, t.due_raw = due_at, due_raw if due_raw is not None else t.due_raw
    t.due_source = "model" if due_at is not None else "none"
    t.due_time_stated = None  # 바뀐 기한은 메일 글자에서 온 게 아니다: 모름으로 두면 화면이 시각까지 보인다
    params = {"kind": "due_change", "task_id": t.id, "due_at": due_at.isoformat() if due_at else None}
    if via:
        params["via"] = via
    if signal_id:
        params["signal_id"] = signal_id
    log = ActionLog(user_id=user_id, action="T16", source=source, params_json=params, affected_ids=[t.id],
                    before_json=before, created_at=now())
    db.add(log)
    db.flush()
    return log


def finish_commitment(db: Session, user_id: int, commitment_id: int, *, via: str | None = None,
                      source: str = "ui") -> ActionLog:
    c = db.get(Commitment, commitment_id)
    if c is None:
        raise StatusError("not_found", f"없는 약속: {commitment_id}")
    before = {"status": c.status}
    c.status = "done"
    params = {"kind": "commitment", "commitment_id": c.id, "status": "done", "text": rules.short(c.text, 40)}
    if via:
        params["via"] = via
    log = ActionLog(user_id=user_id, action="commitment_done", source=source, params_json=params, affected_ids=[],
                    before_json=before, created_at=now())
    db.add(log)
    db.flush()
    return log


def _commitment_top(db: Session, user_id: int, commitment_id: int) -> int | None:
    """그 약속을 바꾼 기록 중 지금 되돌릴 수 있는 것(되돌리기 · 다시 하기를 반영한 가장 최근)."""
    stack: list[int] = []
    by_id: dict[int, ActionLog] = {}
    for x in db.scalars(select(ActionLog).where(ActionLog.user_id == user_id).order_by(ActionLog.id)):
        by_id[x.id] = x
        p = x.params_json or {}
        if p.get("kind") != "commitment" or p.get("commitment_id") != commitment_id:
            continue
        if x.action != UNDO:
            stack.append(x.id)
            continue
        target = by_id.get(p.get("action_id"))
        if target is not None and target.action == UNDO:
            stack.append(target.params_json["action_id"])
        elif stack and target is not None and stack[-1] == target.id:
            stack.pop()
    return stack[-1] if stack else None


def undo(db: Session, log: ActionLog, *, source: str = "ui") -> tuple[ActionLog, ActionLog, list[Task]]:
    """T16 · 약속 끝내기 기록을 되돌린다(task_status.undo가 부른다). 뒤에 같은 대상을 바꾼 살아 있는 기록이 있으면 409."""
    p = log.params_json or {}
    at = now()
    if p.get("kind") == "commitment":
        cid = p["commitment_id"]
        if log.action == UNDO:
            later = db.scalars(select(ActionLog).where(ActionLog.user_id == log.user_id, ActionLog.id > log.id)).all()
            blocked = any((x.params_json or {}).get("commitment_id") == cid and (x.params_json or {}).get("kind") == "commitment"
                          for x in later)
        else:
            blocked = _commitment_top(db, log.user_id, cid) != log.id
        if blocked:
            raise StatusError("conflict", "이 기록 뒤에 같은 약속을 바꾼 기록이 있어 되돌릴 수 없습니다")
        c = db.get(Commitment, cid)
        current = {"status": c.status}
        c.status = log.before_json["status"]
        tasks: list[Task] = []
        back_params = {"action_id": log.id, "kind": "commitment", "commitment_id": cid, "text": p.get("text")}
        affected: list[int] = []
    else:  # due_change
        ids = [int(i) for i in log.before_json]
        tasks, user_id = task_status._load(db, ids)
        if log.action == UNDO:
            later = db.scalars(select(ActionLog).where(ActionLog.user_id == user_id, ActionLog.id > log.id)).all()
            blocked = any(set(x.affected_ids or []) & set(ids) for x in later)
        else:
            blocked = any(top != log.id for top in task_status._top_actions(db, user_id, ids).values())
        if blocked:
            raise StatusError("conflict", "이 기록 뒤에 같은 업무를 바꾼 기록이 있어 되돌릴 수 없습니다")
        current = {str(t.id): _due_snapshot(t) for t in tasks}
        for t in tasks:
            _due_restore(t, log.before_json[str(t.id)])
        if (sid := p.get("signal_id")) and (sig := db.get(ReminderSignal, sid)) is not None:
            sig.status = "open" if log.action != UNDO else "applied"  # 되돌리면 '기한 바뀜' 항목이 다시 뜬다
        back_params = {"action_id": log.id, "kind": "due_change", "task_id": p.get("task_id"), "signal_id": p.get("signal_id")}
        affected = ids
    log.undone_at = at
    if log.action == UNDO and (redone := db.get(ActionLog, p["action_id"])) is not None:
        redone.undone_at = None
    back = ActionLog(user_id=log.user_id, action=UNDO, source=source, params_json=back_params, affected_ids=affected,
                     before_json=current, created_at=at)
    db.add(back)
    db.flush()
    return log, back, tasks


def describe(log: ActionLog, tasks: dict[int, Task]) -> str | None:
    """기록 탭 문장. 리마인더 기록이 아니면 None."""
    p = log.params_json or {}
    if p.get("kind") == "commitment":
        return f"약속 '{p.get('text') or ''}'을(를) 이행 완료로 처리했습니다"
    if p.get("kind") == "due_change":
        t = tasks.get(p.get("task_id"))
        what = f"'{rules.short(t.text, 24)}' 업무" if t else "업무"
        due = datetime.fromisoformat(p["due_at"]) if p.get("due_at") else None
        return f"{what} 기한을 {due.month}/{due.day} {due:%H:%M}(으)로 변경했습니다" if due else f"{what} 기한을 삭제했습니다"
    return None


# ---------- 유형 알림 끄기 ----------

def set_notify(db: Session, user_id: int, type_: str, notify: bool) -> list[str]:
    """유형 알림 끄기 · 켜기(명세 4.2절 5번). 목록에서는 사라지지 않는다. 꺼진 유형 목록을 돌려준다."""
    if type_ not in ACTIVE_TYPES:
        raise StatusError("not_found", f"없는 리마인더 유형: {type_}")
    s = rules.ensure_settings(db, user_id)
    mute = dict(s.reminder_mute or {})
    if notify:
        mute.pop(type_, None)
    else:
        mute[type_] = True
    s.reminder_mute = mute  # JSON 칸은 새 dict를 넣어야 바뀐 것으로 본다
    db.flush()
    return sorted(mute)


def muted(db: Session, user_id: int) -> list[str]:
    s = db.get(UserSettings, user_id)
    return sorted(k for k, v in ((s.reminder_mute if s else None) or {}).items() if v)
