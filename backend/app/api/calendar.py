"""캘린더 API (BE-15 · D50 결정 6). 달력만 보고 언제 무엇을 해야 하는지 알 수 있게 기한 · 다시 알림 · 회의 · 넣은 일정을 한 번에 준다.

- GET  /api/calendar?start=YYYY-MM-DD&end=YYYY-MM-DD  두 날 포함, 62일까지
- POST /api/calendar/events      일정 넣기(일정참석 카드 버튼 · 캘린더 화면). 메일 한 통에 하나
- DELETE /api/calendar/events/{id}  일정 빼기
넣기 · 빼기는 action_id를 주고, 되돌리기는 기존 POST /api/actions/{action_id}/undo로 한다.
- BE-7: 연결된 Outlook 계정의 일정도 같은 기간으로 읽어 kind=event · outlook_id로 함께 준다(Graph calendarView, 읽기만).
  Outlook이 실패하면 그 일정만 빠지고 나머지는 그대로 보인다. 넣기 · 빼기를 Outlook에 쓰는 것은 다음 단계(되돌리기와 함께).
"""
import logging
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import as_kst, now, to_kst_naive
from app.core.db import get_db
from app.core.user import Id, current_user_id
from app.models import Account
from app.schemas.calendar import CalendarItem, CalendarRange, EventCreate, EventResult
from app.services import calendar
from app.services.task_status import StatusError

log = logging.getLogger("app.graph")
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


def _graph_time(v: dict, all_day: bool = False) -> datetime:
    """Graph dateTimeTimeZone(기본 UTC, 소수 7자리) → naive KST. 종일 일정은 시간대와 상관없는 자정이라 날짜를 그대로 쓴다
    (UTC로 보고 바꾸면 09:00 시작 · 다음 날 09:00 끝이 된다)."""
    raw = v["dateTime"][:26]  # 파이썬은 소수 6자리까지 읽는다
    if all_day:
        return datetime.fromisoformat(raw)
    tz = "+00:00" if v.get("timeZone", "UTC") == "UTC" else ""
    return to_kst_naive(datetime.fromisoformat(raw + tz))


def _outlook_items(db: Session, user_id: int, start: date, end: date) -> list[CalendarItem]:
    accounts = db.scalars(select(Account).where(Account.user_id == user_id, Account.provider == "outlook_graph",
                                                Account.refresh_token_enc.is_not(None))).all()
    if not accounts:
        return []
    from app.mail import graph

    lo = datetime.combine(start, time.min).isoformat() + "+09:00"
    hi = datetime.combine(end + timedelta(days=1), time.min).isoformat() + "+09:00"
    out = []
    for account in accounts:
        url, params = "/me/calendarView", {"startDateTime": lo, "endDateTime": hi, "$top": "100",
                                           "$select": "id,subject,start,end,isAllDay,isCancelled,webLink"}
        try:
            while url:
                data = graph.call(db, account, "GET", url, params=params).json()
                for ev in data.get("value", []):
                    if ev.get("isCancelled"):
                        continue
                    out.append(CalendarItem(kind="event", title=ev.get("subject") or "(제목 없음)", start=as_kst(_graph_time(ev["start"], ev.get("isAllDay", False))),
                                            end=as_kst(_graph_time(ev["end"], ev.get("isAllDay", False))), time_stated=not ev.get("isAllDay"), mail_id=None,
                                            task_id=None, event_id=None, subject=None, outlook_id=ev["id"], web_link=ev.get("webLink")))
                url, params = data.get("@odata.nextLink"), None
        except graph.GraphError as e:
            db.rollback()
            log.warning("Outlook 일정 읽기 실패 account=%s status=%s", account.id, e.status)
    return out


@router.get("", response_model=CalendarRange)
def get_range(start: date = Query(...), end: date = Query(...), user_id: int = Depends(current_user_id),
              db: Session = Depends(get_db)) -> CalendarRange:
    try:
        rows = calendar.items(db, user_id, start, end)
    except StatusError as e:
        raise HTTPException(HTTP[e.kind], str(e)) from None
    items = sorted([_item(i) for i in rows] + _outlook_items(db, user_id, start, end), key=lambda i: i.start)
    return CalendarRange(start=start, end=end, as_of=as_kst(now()), items=items)


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
