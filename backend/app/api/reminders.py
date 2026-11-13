"""리마인더 · 알림 센터 · 브리핑 API (BE-12, 명세 docs/10_planning/reminders.md 7.2절).

- 조회(GET)는 어떤 행도 쓰지 않는다(PL-16 S1). 알림은 엔진(스케줄러 · 개발용 실행)만 만든다.
- 적용 · 신고의 상태 변경은 action_log 한 줄로 남고 되돌리기는 `POST /api/actions/{id}/undo` 하나다.
- 개발용 강제 실행 `POST /api/dev/reminders/run`은 APP_MODE=dev에서만 있다(운영은 404, BE-14).
"""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.clock import as_kst, now, to_kst_naive
from app.core.config import get_settings
from app.core.db import get_db
from app.core.user import Id, current_user_id
from app.models import Notification
from app.reminders import actions, briefings, engine
from app.reminders.types import GROUPS
from app.schemas.actions import TaskState
from app.schemas.reminders import (ApplyResult, Briefing, DismissRequest, DismissResult, NotificationList,
                                   NotificationPatch, NotificationView, ReadAllResult, ReminderList, RunResult,
                                   TypeNotify, TypeNotifyResult)
from app.services import task_status
from app.services.task_status import StatusError

router = APIRouter(prefix="/api")
HTTP = {"not_found": 404, "conflict": 409, "invalid": 422}
KEY = Path(max_length=100, pattern=r"^[a-z_]+:[a-z_]+:[0-9]+$")
NOTIFICATION_LIMIT = 100


def _write(db: Session, fn, *args, **kwargs):
    try:
        out = fn(db, *args, **kwargs)
    except StatusError as e:
        db.rollback()
        raise HTTPException(HTTP[e.kind], str(e)) from None
    db.commit()
    return out


def _view(i: dict) -> dict:
    out = {k: v for k, v in i.items() if not k.startswith("_")}
    out["due_at"], out["created_at"] = as_kst(i["due_at"]), as_kst(i["created_at"])
    out["notify"] = bool(i["_notify"]) and not i["_muted"] and not i["_not_mine"]
    return out


def _state(t) -> TaskState:
    return TaskState(id=t.id, status=t.status, done_at=as_kst(t.done_at), snoozed_until=as_kst(t.snoozed_until),
                     status_changed_at=as_kst(t.status_changed_at))


# ---------- 리마인더 ----------

@router.get("/reminders", response_model=ReminderList)
def list_reminders(group: str = Query("all", pattern=r"^(all|due|waiting|promise|revisit|prepare|cleanup)$"),
                   user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> ReminderList:
    at = now()
    its = engine.items(db, user_id, at)
    counts = {g: sum(1 for i in its if i["group"] == g) for g in GROUPS}
    counts["all"] = len(its)
    shown = its if group == "all" else [i for i in its if i["group"] == group]
    return ReminderList(as_of=as_kst(at), counts=counts, muted_types=actions.muted(db, user_id),
                        items=[_view(i) for i in shown])


@router.post("/reminders/{key}/dismiss", response_model=DismissResult)
def dismiss(body: DismissRequest, key: str = KEY, user_id: int = Depends(current_user_id),
            db: Session = Depends(get_db)) -> DismissResult:
    out = _write(db, actions.dismiss, user_id, key, body.reason)
    return DismissResult(**{**out, "hidden_until": as_kst(out["hidden_until"])})


@router.post("/reminders/{key}/apply", response_model=ApplyResult)
def apply(key: str = KEY, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> ApplyResult:
    out = _write(db, actions.apply, user_id, key)
    task = out["task"]
    return ApplyResult(key=key, action_id=out["action_id"], task=_state(task) if task else None,
                       due_at=as_kst(task.due_at) if task else None, commitment_id=out["commitment_id"])


@router.patch("/reminders/types/{type_}", response_model=TypeNotifyResult)
def set_type_notify(body: TypeNotify, type_: str = Path(max_length=20), user_id: int = Depends(current_user_id),
                    db: Session = Depends(get_db)) -> TypeNotifyResult:
    muted = _write(db, actions.set_notify, user_id, type_, body.notify)
    return TypeNotifyResult(type=type_, notify=type_ not in muted, muted_types=muted)


# ---------- 알림 센터 ----------

def _notification(n: Notification) -> NotificationView:
    return NotificationView(id=n.id, kind=n.kind, type=n.type, group=n.group, reminder_key=n.reminder_key,
                            reminder_keys=n.reminder_keys or [], title=n.title, body=n.body, task_ids=n.task_ids or [],
                            rule=n.rule, scheduled_at=as_kst(n.scheduled_at), read_at=as_kst(n.read_at),
                            answered_at=as_kst(n.answered_at), created_at=as_kst(n.created_at))


@router.get("/notifications", response_model=NotificationList)
def list_notifications(unread_only: bool = False, user_id: int = Depends(current_user_id),
                       db: Session = Depends(get_db)) -> NotificationList:
    q = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        q = q.where(Notification.read_at.is_(None))
    rows = db.scalars(q.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(NOTIFICATION_LIMIT)).all()
    unread = len(db.scalars(select(Notification.id).where(Notification.user_id == user_id,
                                                          Notification.read_at.is_(None))).all())
    return NotificationList(items=[_notification(n) for n in rows], unread=unread)


def _answer(db: Session, user_id: int, n: Notification, answer: str) -> None:
    """reply_confirm 답: 예 = 완료(T03, 되돌리기 가능), 아니오 = 아직 남았어요(이 답장으로는 다시 묻지 않음)."""
    if n.kind != "reply_confirm":
        raise StatusError("invalid", "answer는 reply_confirm 알림에만 씁니다")
    if n.answered_at is not None:
        raise StatusError("conflict", "이미 답한 알림입니다")
    if answer == "yes":
        task_status.change_status(db, n.task_ids, "done", action="T03", via="reminder:reply_confirm", owner=user_id)
    elif n.reminder_key:
        try:
            actions.dismiss(db, user_id, n.reminder_key, "keep")
        except StatusError as e:
            if e.kind != "not_found":  # 항목이 이미 없으면(완료 등) 답만 남긴다
                raise
    n.read_at = n.read_at or now()
    n.answered_at = now()


@router.patch("/notifications/{notification_id}", response_model=NotificationView)
def patch_notification(notification_id: Id, body: NotificationPatch, user_id: int = Depends(current_user_id),
                       db: Session = Depends(get_db)) -> NotificationView:
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != user_id:
        raise HTTPException(404, "없는 알림입니다")
    if body.read is None and body.answer is None:
        raise HTTPException(422, "read 또는 answer가 필요합니다")
    if body.answer is not None:
        _write(db, lambda d: _answer(d, user_id, n, body.answer))
    if body.read and n.read_at is None:
        n.read_at = now()
        db.commit()
    return _notification(n)


@router.post("/notifications/read-all", response_model=ReadAllResult)
def read_all(user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> ReadAllResult:
    n = db.execute(update(Notification).where(Notification.user_id == user_id, Notification.read_at.is_(None))
                   .values(read_at=now()).execution_options(synchronize_session=False)).rowcount
    db.commit()
    return ReadAllResult(updated=n)


# ---------- 브리핑 · 회고 ----------

@router.get("/briefings/{kind}", response_model=Briefing)
def get_briefing(kind: str = Path(pattern=r"^(morning|evening|weekly)$"), date_: date | None = Query(None, alias="date"),
                 user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> Briefing:
    b = briefings.build(db, user_id, kind, date_)
    b["as_of"] = as_kst(b["as_of"])
    for s in b["sections"]:
        for line in s["items"]:
            line["due_at"] = as_kst(line["due_at"])
    return Briefing(**b)


# ---------- 개발용 강제 실행(BE-14) ----------

def dev_only() -> None:
    if get_settings().app_mode != "dev":
        raise HTTPException(404, "Not Found")


@router.post("/dev/reminders/run", response_model=RunResult, dependencies=[Depends(dev_only)])
def dev_run(at: datetime | None = None, db: Session = Depends(get_db)) -> RunResult:
    """그 시각(없으면 지금)으로 엔진을 한 번 돌린다. 서비스 시각은 옮기지 않는다(옮기려면 시나리오 /clock)."""
    when = to_kst_naive(at) if at else now()
    return RunResult(at=as_kst(when.replace(second=0, microsecond=0)), results=engine.run_all(db, when))
