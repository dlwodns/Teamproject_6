"""앱 캘린더 (BE-15 · D50 결정 6): 기간 조회 · 일정 넣기 · 빼기 · 되돌리기.

달력 한 칸에 보이는 것은 네 가지다.
- due: 미처리 업무의 기한(일정참석은 빼고 아래 meeting으로)
- snoozed: '나중에'로 미룬 업무가 다시 알려 줄 시각
- meeting: 일정참석 업무의 회의 시각. 같은 업무로 넣은 일정이 있으면 그 일정(event)만 보인다(겹쳐 두 번 보이지 않게)
- event: 앱 캘린더에 넣은 일정(카드 버튼 · 말로 지시 T15)
조회는 읽기만 한다. 넣기 · 빼기는 action_log 한 줄로 남기고 되돌리기(POST /api/actions/{id}/undo · T04)로 돌린다.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.models import Account, ActionLog, CalendarEvent, Mail, Task
from app.services.task_status import UNDO, StatusError

DEFAULT_LENGTH = timedelta(hours=1)  # 끝 시각이 없으면 시작 + 1시간(D50 확정 11-10)
MAX_DAYS = 62  # 한 번에 조회하는 기간(달력 월 보기 6주 + 여유)
MEETING = "일정참석"  # AI-D15 업무 유형
TARGET = "calendar"  # action_log.params_json.kind — 업무 · 기억 변경과 구분한다


@dataclass
class Item:
    kind: str  # due | snoozed | meeting | event
    title: str
    start: datetime
    end: datetime | None
    time_stated: bool  # False면 날짜만 보여 준다(메일에 시각이 없어 기본 시각으로 채운 기한)
    mail_id: int | None
    task_id: int | None
    event_id: int | None
    subject: str | None
    auto: bool = False


def _owned_tasks(user_id: int):
    return (select(Task, Mail.subject).join(Mail, Task.mail_id == Mail.id).join(Account, Mail.account_id == Account.id)
            .where(Account.user_id == user_id, Mail.direction == "received"))


def _active_events(user_id: int):
    return select(CalendarEvent).where(CalendarEvent.user_id == user_id, CalendarEvent.deleted_at.is_(None))


def items(db: Session, user_id: int, start_day: date, end_day: date) -> list[Item]:
    """[start_day, end_day] 두 날을 포함한 기간의 항목, 시각 순."""
    if end_day < start_day:
        raise StatusError("invalid", "끝 날짜가 시작 날짜보다 앞입니다")
    if (end_day - start_day).days + 1 > MAX_DAYS:
        raise StatusError("invalid", f"한 번에 {MAX_DAYS}일까지 볼 수 있습니다")
    lo, hi = datetime.combine(start_day, time.min), datetime.combine(end_day + timedelta(days=1), time.min)
    out: list[Item] = []

    events = db.scalars(_active_events(user_id).where(CalendarEvent.start_at < hi, CalendarEvent.end_at > lo)).all()
    evented_tasks = set(db.scalars(select(CalendarEvent.task_id).where(
        CalendarEvent.user_id == user_id, CalendarEvent.deleted_at.is_(None), CalendarEvent.task_id.is_not(None))))
    subjects = dict(db.execute(select(Mail.id, Mail.subject).where(
        Mail.id.in_({e.mail_id for e in events if e.mail_id}))).all()) if events else {}
    for e in events:
        out.append(Item("event", e.title, e.start_at, e.end_at, True, e.mail_id, e.task_id, e.id,
                        subjects.get(e.mail_id), e.auto))

    for t, subject in db.execute(_owned_tasks(user_id).where(Task.status == "pending", Task.due_at >= lo,
                                                             Task.due_at < hi)).all():
        if t.type == MEETING:
            if t.id in evented_tasks:
                continue
            end = (t.end_at or t.due_at + DEFAULT_LENGTH) if t.due_time_stated else None
            out.append(Item("meeting", t.text, t.due_at, end, t.due_time_stated is not False, t.mail_id, t.id, None, subject))
        else:
            out.append(Item("due", t.text, t.due_at, None, t.due_time_stated is not False, t.mail_id, t.id, None, subject))

    for t, subject in db.execute(_owned_tasks(user_id).where(Task.status == "snoozed", Task.snoozed_until >= lo,
                                                             Task.snoozed_until < hi)).all():
        out.append(Item("snoozed", t.text, t.snoozed_until, None, True, t.mail_id, t.id, None, subject))

    order = {"event": 0, "meeting": 1, "due": 2, "snoozed": 3}
    out.sort(key=lambda i: (i.start, order[i.kind], i.task_id or 0, i.event_id or 0))
    return out


def _iso(v: datetime | None) -> str | None:
    return v.isoformat() if v else None


def _log(db: Session, user_id: int, action: str, ev: CalendarEvent, before: datetime | None, *, source: str,
         via: str | None = None) -> ActionLog:
    """일정 한 건의 deleted_at 전후를 남긴다. 되돌리기는 before로 돌린다(업무 칸은 건드리지 않는다)."""
    params = {"kind": TARGET, "event_id": ev.id, "title": ev.title, "start": _iso(ev.start_at), "after": _iso(ev.deleted_at)}
    if via:
        params["via"] = via
    log = ActionLog(user_id=user_id, action=action, source=source, params_json=params, affected_ids=[],
                    before_json={"deleted_at": _iso(before)}, created_at=now())
    db.add(log)
    db.flush()
    return log


def add(db: Session, user_id: int, *, title: str | None, start: datetime, end: datetime | None = None,
        mail_id: int | None = None, task_id: int | None = None, action: str = "T15", source: str = "ui",
        via: str | None = None) -> tuple[CalendarEvent, ActionLog]:
    """일정을 넣는다. 메일 한 통에 살아 있는 일정은 하나다(이미 있으면 409). 커밋은 부르는 쪽이 한다."""
    if task_id is not None:
        row = db.execute(_owned_tasks(user_id).where(Task.id == task_id)).first()
        if row is None:
            raise StatusError("not_found", f"없는 업무: {task_id}")
        mail_id = mail_id or row[0].mail_id
        if row[0].mail_id != mail_id:
            raise StatusError("invalid", "업무와 메일이 맞지 않습니다")
    subject = None
    if mail_id is not None:
        mail = db.scalar(select(Mail).join(Account, Mail.account_id == Account.id)
                         .where(Mail.id == mail_id, Account.user_id == user_id))
        if mail is None:
            raise StatusError("not_found", f"없는 메일: {mail_id}")
        subject = mail.subject
        if db.scalar(_active_events(user_id).where(CalendarEvent.mail_id == mail_id)) is not None:
            raise StatusError("conflict", "이 메일의 일정이 이미 캘린더에 있습니다")
    end = end or start + DEFAULT_LENGTH
    if end <= start:
        raise StatusError("invalid", "끝 시각이 시작 시각보다 앞입니다")
    title = (title or "").strip() or (subject or "").strip() or "일정"
    ev = CalendarEvent(user_id=user_id, mail_id=mail_id, task_id=task_id, title=title[:200], start_at=start, end_at=end)
    db.add(ev)
    db.flush()
    log = _log(db, user_id, action, ev, before=ev.created_at, source=source, via=via)  # 넣기 전 = 없던 것(지운 것과 같게)
    ev.action_id = log.id
    return ev, log


def remove(db: Session, user_id: int, event_id: int, *, source: str = "ui", via: str | None = None) -> tuple[CalendarEvent, ActionLog]:
    ev = db.get(CalendarEvent, event_id)
    if ev is None or ev.user_id != user_id or ev.deleted_at is not None:
        raise StatusError("not_found", f"없는 일정: {event_id}")
    ev.deleted_at = now()
    return ev, _log(db, user_id, "calendar_remove", ev, before=None, source=source, via=via)


def is_calendar(log: ActionLog) -> bool:
    return (log.params_json or {}).get("kind") == TARGET


def _mail_taken(db: Session, ev: CalendarEvent) -> bool:
    """ev를 되살리면 같은 메일에 살아 있는 일정이 둘이 되는지(메일 한 통에 하나 규칙)."""
    if ev.mail_id is None:
        return False
    return db.scalar(_active_events(ev.user_id).where(CalendarEvent.mail_id == ev.mail_id,
                                                      CalendarEvent.id != ev.id)) is not None


def can_undo(db: Session, log: ActionLog) -> bool:
    """기록 탭 [되돌리기]를 보일지: 일정이 이 기록 직후 상태 그대로이고, 되살릴 때는 같은 메일에 다른 일정이 없을 때만."""
    p = log.params_json or {}
    ev = db.get(CalendarEvent, p.get("event_id"))
    if ev is None or (ev.deleted_at is None) != (p.get("after") is None):
        return False
    revive = not (log.before_json or {}).get("deleted_at")
    return not (revive and _mail_taken(db, ev))


def undo(db: Session, log: ActionLog, *, source: str = "ui") -> ActionLog:
    """일정 넣기 · 빼기(또는 그 되돌리기) 한 줄을 되돌린다. 기록 뒤에 일정이 다른 길로 바뀌었으면(이미 뺐는데 넣기를 되돌림 등) 409."""
    p = log.params_json or {}
    ev = db.get(CalendarEvent, p["event_id"])
    if ev is None:
        raise StatusError("not_found", "일정이 없습니다")
    if not can_undo(db, log):
        if ev.deleted_at is not None and _mail_taken(db, ev):
            raise StatusError("conflict", "이 메일의 다른 일정이 이미 캘린더에 있어 되살릴 수 없습니다")
        raise StatusError("conflict", "이 기록 뒤에 일정이 바뀌어 되돌릴 수 없습니다")
    before = log.before_json.get("deleted_at")
    current = ev.deleted_at
    ev.deleted_at = datetime.fromisoformat(before) if before else None
    at = now()
    log.undone_at = at
    if log.action == UNDO and (redone := db.get(ActionLog, p["action_id"])) is not None:
        redone.undone_at = None  # 다시 하기
    back = ActionLog(user_id=log.user_id, action=UNDO, source=source,
                     params_json={"action_id": log.id, "kind": TARGET, "event_id": ev.id, "title": ev.title,
                                  "start": _iso(ev.start_at), "after": _iso(ev.deleted_at)},
                     affected_ids=[], before_json={"deleted_at": _iso(current)}, created_at=at)
    db.add(back)
    db.flush()
    return back


def describe(log: ActionLog) -> str:
    """기록 탭 문장."""
    p = log.params_json or {}
    start = datetime.fromisoformat(p["start"]) if p.get("start") else None
    when = f"{start.month}/{start.day} {start:%H:%M} " if start else ""
    title = p.get("title") or "일정"
    if log.action == "calendar_remove":
        return f"캘린더에서 {when}'{title}'을(를) 뺐어요"
    return f"캘린더에 {when}'{title}'을(를) 넣었어요"


def mail_meeting(db: Session, user_id: int, mail_id: int) -> Task | None:
    """고른 메일의 일정참석 업무 중 시각이 메일에 적힌 첫 업무(T15 '이 회의 캘린더에 넣어줘'). 없으면 None — 지어내지 않는다."""
    return db.scalars(_owned_tasks(user_id).where(Task.mail_id == mail_id, Task.type == MEETING,
                                                  Task.due_at.is_not(None), Task.due_time_stated.is_(True))
                      .order_by(Task.due_at, Task.id).limit(1)).first()
