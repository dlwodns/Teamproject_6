"""캘린더 API (BE-15 · D50 결정 6). 달력만 보고 언제 무엇을 해야 하는지 알 수 있게 기한 · 다시 알림 · 회의 · 넣은 일정을 한 번에 준다.

- GET  /api/calendar?start=YYYY-MM-DD&end=YYYY-MM-DD  두 날 포함, 62일까지
- POST /api/calendar/events      일정 넣기(일정참석 카드 버튼 · 캘린더 화면). 메일 한 통에 하나
- DELETE /api/calendar/events/{id}  일정 빼기
넣기 · 빼기는 action_id를 주고, 되돌리기는 기존 POST /api/actions/{action_id}/undo로 한다.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.clock import as_kst, now, to_kst_naive
from app.core.db import get_db
from app.core.user import Id, current_user_id
from app.schemas.calendar import CalendarItem, CalendarRange, EventCreate, EventResult
from app.services import calendar
from app.services.task_status import StatusError

router = APIRouter(prefix="/api/calendar")
HTTP = {"not_found": 404, "conflict": 409, "invalid": 422}


def _item(i: calendar.Item) -> CalendarItem:
    return CalendarItem(kind=i.kind, title=i.title, start=as_kst(i.start), end=as_kst(i.end), time_stated=i.time_stated,
                        mail_id=i.mail_id, task_id=i.task_id, event_id=i.event_id, subject=i.subject, auto=i.auto)


def _event_item(ev) -> CalendarItem:
    return _item(calendar.Item("event", ev.title, ev.start_at, ev.end_at, True, ev.mail_id, ev.task_id, ev.id, None, ev.auto))


def _run(db: Session, fn, *args, **kwargs):
    try:
        out = fn(db, *args, **kwargs)
    except StatusError as e:
        db.rollback()
        raise HTTPException(HTTP[e.kind], str(e)) from None
    db.commit()
    return out


@router.get("", response_model=CalendarRange)
def get_range(start: date = Query(...), end: date = Query(...), user_id: int = Depends(current_user_id),
              db: Session = Depends(get_db)) -> CalendarRange:
    try:
        rows = calendar.items(db, user_id, start, end)
    except StatusError as e:
        raise HTTPException(HTTP[e.kind], str(e)) from None
    return CalendarRange(start=start, end=end, as_of=as_kst(now()), items=[_item(i) for i in rows])


@router.post("/events", response_model=EventResult, status_code=201)
def create_event(body: EventCreate, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> EventResult:
    start = to_kst_naive(body.start)
    end = to_kst_naive(body.end) if body.end else None
    ev, log = _run(db, calendar.add, user_id, title=body.title, start=start, end=end, mail_id=body.mail_id,
                   task_id=body.task_id, source="ui", via=body.via)
    return EventResult(action_id=log.id, item=_event_item(ev))


@router.delete("/events/{event_id}", response_model=EventResult)
def delete_event(event_id: Id, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> EventResult:
    ev, log = _run(db, calendar.remove, user_id, event_id, source="ui")
    return EventResult(action_id=log.id, item=_event_item(ev))
