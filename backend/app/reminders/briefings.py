"""브리핑 · 회고 내용 (명세 reminders.md 4.3절, BE-D30).

브리핑은 **무엇이 있는지만** 알린다. "~부터 챙기세요"처럼 할 일을 권하지 않는다(AI-D18 · 11-13 사용자 결정).
숫자와 목록은 코드가 세고 문장은 정해진 문장이다(모델을 부르지 않는다). 읽기만 한다.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.models import Account, ActionLog, Mail, Task
from app.reminders import policy as pol
from app.reminders import rules

KINDS = ("morning", "evening", "weekly")
TITLE = {"morning": "일일 업무 요약", "evening": "일일 업무 회고", "weekly": "주간 업무 회고"}


def _line(task: Task | None = None, *, title: str, reason: str | None = None, due_at=None, mail_id=None, key=None,
          commitment_id=None, action_id=None, actions=None) -> dict:
    return {"task_id": task.id if task else None, "mail_id": mail_id if mail_id is not None else (task.mail_id if task else None),
            "commitment_id": commitment_id, "reminder_key": key, "title": title, "reason": reason, "due_at": due_at,
            "action_id": action_id, "actions": actions or []}


def _section(id_: str, label: str, lines: list[dict]) -> dict:
    return {"id": id_, "label": label, "count": len(lines), "items": lines}


def _item_line(i: dict) -> dict:
    return _line(title=i["title"], reason=i["reason"], due_at=i["due_at"], mail_id=i["mail_id"], key=i["key"],
                 commitment_id=i["commitment_id"])


def _summary(sections: list[dict], empty: str) -> str:
    parts = [f"{s['label']} {s['count']}건" for s in sections if s["count"]]
    return (" · ".join(parts) + "이 있습니다.") if parts else empty


def _day_word(day: date, today: date) -> str:
    """묶음 이름의 날짜 말: 오늘 '금일', 내일 '익일', 그 밖은 M/D. 내일 요약에 '금일'이 붙지 않게 한다(#190 리뷰 3)."""
    if day == today:
        return "금일"
    if day == today + timedelta(days=1):
        return "익일"
    return f"{day.month}/{day.day}"


def _user_tasks(db: Session, user_id: int):
    return (select(Task, Mail).join(Mail, Task.mail_id == Mail.id).join(Account, Mail.account_id == Account.id)
            .where(Account.user_id == user_id, Mail.direction == "received"))


def scheduled_at(kind: str, day: date, p: pol.Policy) -> datetime:
    """그 날짜의 브리핑을 만드는 시각(명세 4.3절): 아침 = R-아침(remind_time), 퇴근 = 회고 시각(evening_time), 주간 = 그 주 금요일 회고 시각."""
    if kind == "morning":
        return datetime.combine(day, p.remind)
    if kind == "weekly":
        day = day - timedelta(days=day.weekday()) + timedelta(days=pol.WEEKLY_DAY - 1)
    return p.evening(day)


def _as_of(day: date, scheduled: datetime, at: datetime) -> datetime:
    """오늘이면 지금, 다른 날이면 만드는 시각과 지금 중 이른 쪽으로 센다. 지난날은 그 시각 기준(지금 상태로 다시 센 근사값),
    앞날은 지금 기준이라 as_of < scheduled_at이면 화면이 '아직 만들 시각이 아니에요'라고 쓴다."""
    return at if day == at.date() else min(at, scheduled)


def build(db: Session, user_id: int, kind: str, day: date | None = None, at: datetime | None = None) -> dict:
    at = at or now()
    day = day or at.date()
    p = pol.load(db, user_id)
    scheduled = scheduled_at(kind, day, p)
    as_of = _as_of(day, scheduled, at)
    ctx = rules.Context(db, user_id, as_of)
    open_tasks = rules._open_tasks(ctx)
    items = rules.compute(db, user_id, as_of, include_hidden=True)
    by_type: dict[str, list[dict]] = {}
    for i in items:
        by_type.setdefault(i["type"], []).append(i)
    d0, d1 = _day_word(day, at.date()), _day_word(day + timedelta(days=1), at.date())

    if kind == "morning":
        start = datetime.combine(day, datetime.min.time())
        due_today = [_line(t, title=t.text, due_at=t.due_at, reason=f"기한 {t.due_at:%H:%M}")
                     for t, _ in sorted(open_tasks, key=lambda r: (r[0].due_at or datetime.max, r[0].id))
                     if t.due_at is not None and t.due_at.date() == day and t.due_at >= as_of]
        # 그날 0시 전 기한은 그날 아침엔 지나 있다. 앞날 미리 보기(as_of = 지금)에서 아직 안 지난 것은 이유에 따로 적는다
        # (빼면 오늘 남은 마감이 어느 칸에도 없다, #198 리뷰)
        overdue = [_line(t, title=t.text, due_at=t.due_at,
                         reason=f"기한 {rules.when(t.due_at, as_of)}" + ("(아직 안 지남)" if t.due_at >= as_of else ""))
                   for t, _ in sorted(open_tasks, key=lambda r: (r[0].due_at or datetime.max, r[0].id))
                   if t.due_at is not None and t.due_at < max(as_of, start)]
        prev = p.latest_morning(as_of - timedelta(minutes=1)) or (as_of - timedelta(days=1))
        auto = db.scalars(select(ActionLog).where(ActionLog.user_id == user_id, ActionLog.source == "reply_auto",
                                                  ActionLog.undone_at.is_(None), ActionLog.created_at >= prev,
                                                  ActionLog.created_at < as_of).order_by(ActionLog.id)).all()
        tasks = {t.id: t for t in db.scalars(select(Task).where(Task.id.in_({i for x in auto for i in x.affected_ids or []})))}
        auto_lines = [_line(tasks.get(tid), title=tasks[tid].text if tid in tasks else f"업무 {tid}", action_id=x.id,
                            reason="회신으로 완료 처리됨",
                            actions=[{"id": "undo", "label": "되돌리기", "action": "T04", "primary": False,
                                      "params": {"action_id": x.id}}])
                      for x in auto for tid in (x.affected_ids or [])]
        sections = [_section("due_today", f"{d0} 마감 업무", due_today), _section("overdue", "기한 경과 업무", overdue),
                    _section("no_reply", "회신 미수신 메일", [_item_line(i) for i in by_type.get("no_reply", [])]),
                    _section("my_promise", "이행 약속", [_item_line(i) for i in by_type.get("my_promise", [])]),
                    _section("auto_done", "회신 완료 처리", auto_lines)]
        summary = _summary(sections, f"{d0} 확인할 업무가 없습니다.")
    elif kind == "evening":
        lo, hi = datetime.combine(day, datetime.min.time()), datetime.combine(day + timedelta(days=1), datetime.min.time())
        done = [_line(t, title=t.text, reason="완료")
                for t, _ in db.execute(_user_tasks(db, user_id).where(Task.status == "done", Task.done_at >= lo,
                                                                      Task.done_at < hi).order_by(Task.done_at)).all()]
        tomorrow_morning = p.next_morning(hi) or hi + timedelta(hours=8, minutes=30)
        remaining = [_line(t, title=t.text, due_at=t.due_at,
                           reason=f"기한 {rules.when(t.due_at, as_of)}" if t.due_at else "기한 없음",
                           actions=[{"id": "snooze_morning", "label": "익일 오전으로 연기", "action": "T05",
                                     "primary": False, "params": {"until": tomorrow_morning.isoformat()}}])
                     for t, _ in sorted(open_tasks, key=lambda r: (r[0].due_at or datetime.max, r[0].id))]
        due_tomorrow = [_line(t, title=t.text, due_at=t.due_at, reason=f"기한 {t.due_at:%H:%M}")
                        for t, _ in open_tasks if t.due_at is not None and t.due_at.date() == day + timedelta(days=1)]
        sections = [_section("done_today", f"{d0} 완료 업무", done), _section("remaining", "미처리 업무", remaining),
                    _section("due_tomorrow", f"{d1} 마감 업무", due_tomorrow)]
        summary = _summary(sections, f"{d0} 정리할 업무가 없습니다.")
    elif kind == "weekly":
        monday = day - timedelta(days=day.weekday())
        lo, hi = datetime.combine(monday, datetime.min.time()), datetime.combine(monday + timedelta(days=7), datetime.min.time())
        rows = db.execute(_user_tasks(db, user_id).where(Task.status == "done", Task.done_at >= lo, Task.done_at < hi)
                          .order_by(Task.done_at)).all()
        done = [_line(t, title=t.text, reason="완료") for t, _ in rows]
        near = [_line(t, title=t.text, due_at=t.due_at, reason=f"기한 {t.due_at:%m/%d %H:%M} 경과 후 {t.done_at:%m/%d %H:%M}에 완료")
                for t, _ in rows if t.due_at is not None and t.done_at > t.due_at]
        waiting = [_item_line(i) for t in ("no_reply", "their_promise") for i in by_type.get(t, [])]
        sections = [_section("done_week", "금주 완료 업무", done), _section("near_miss", "기한 경과 후 완료", near),
                    _section("waiting", "회신 대기", waiting)]
        summary = _summary(sections, "금주 정리할 업무가 없습니다.")
    else:
        raise ValueError(kind)
    total = sum(s["count"] for s in sections)
    return {"kind": kind, "date": day, "as_of": as_of, "scheduled_at": scheduled, "title": f"{TITLE[kind]} · {day.month}/{day.day}({rules.WEEKDAYS[day.weekday()]})",
            "summary": summary, "total": total, "sections": sections}
