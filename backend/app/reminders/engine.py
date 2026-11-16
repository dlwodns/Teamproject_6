"""리마인더 엔진 — 1분마다 ① 항목 계산 ② 보낼 알림 정하기 ③ 보내기 직전 재확인 ④ 쓰기 (명세 reminders.md 4 · 7.3절, BE-D28).

- 항목은 저장하지 않고 매번 DB 값으로 다시 계산한다(rules.py). 그래서 서버를 다시 켜도 따로 복구할 예약이 없다. 첫 틱이 DB에서 다시 만든다.
- 알림은 `reminders`에 발송 한 줄씩 남긴다. 같은 항목 · 규칙 · 시각(slot)은 유일 제약으로 한 번만 쓴다(중복 0).
- 같은 분에 3건 이상이면 "챙길 것 N건" 하나(digest)로 묶는다. 부재 중 복귀 · 퇴근 회고 · 주간 회고도 digest 한 건이다.
- 시각은 `app.core.clock.now()` 또는 부르는 쪽이 준 at만 쓴다(시연 시각 BE-D17 · 개발용 강제 실행 BE-14).
"""
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select, true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import now
from app.models import Commitment, Notification, Reminder, ReminderFeedback, SuggestionHide, Task, User
from app.reminders import briefings, rules
from app.reminders import policy as pol
from app.reminders.types import DUE, IMMEDIATE, MEETING, MORNING, RULE_NAME, SNOOZE, TYPES, label

log = logging.getLogger("app.reminders")


# ---------- 알림 기록 ----------

def history(db: Session, user_id: int) -> dict[tuple, dict]:
    """(subject_kind, subject_id, type) → {count: 보낸 수, last_slot: 마지막으로 다룬 slot 시각, slots: 다룬 slot들}."""
    out: dict[tuple, dict] = {}
    for r in db.scalars(select(Reminder).where(Reminder.user_id == user_id).order_by(Reminder.id)):
        h = out.setdefault((r.subject_kind, r.subject_id, r.type), {"count": 0, "last_sent_slot": None, "slots": set(),
                                                                     "last_slot": None, "last_sent_at": None})
        h["slots"].add((r.rule, r.slot))
        at = pol.parse_slot(r.slot)
        h["last_slot"] = max(h["last_slot"], at) if h["last_slot"] else at
        if r.sent_at is not None:
            h["count"] += 1
            h["last_sent_at"] = max(h["last_sent_at"], r.sent_at) if h["last_sent_at"] else r.sent_at
            h["last_sent_slot"] = max(h["last_sent_slot"], at) if h["last_sent_slot"] else at
    return out


def items(db: Session, user_id: int, at: datetime | None = None, *, include_hidden: bool = False) -> list[dict]:
    """화면에 보일 항목: 알림 횟수(notify_count)와 상태(3번 넘게 알렸으면 quiet)를 붙이고 정렬한다."""
    at = at or now()
    out = rules.compute(db, user_id, at, include_hidden=include_hidden)
    hist = history(db, user_id)
    for i in out:
        h = hist.get((*i["_subject"], i["type"]))
        i["notify_count"] = h["count"] if h else 0
        i["last_notified_at"] = h["last_sent_at"] if h else None
        i["state"] = "quiet" if _quiet(i, i["notify_count"]) else "active"
    out.sort(key=rules.sort_key)
    return out


def _quiet(item: dict, count: int) -> bool:
    """3번 알렸으면 조용히 둔다. 미룬 일은 사용자가 직접 고른 시각이라 몇 번째로 미뤘든 그때 알린다(상한은 재촉에만, BE-D28)."""
    return count >= pol.MAX_NOTIFY and item["_notify"] != SNOOZE


# ---------- ② 보낼 알림 정하기 ----------

@dataclass
class Send:
    item: dict
    rule: str
    slot: datetime  # 규칙이 정한 시각(중복 판정 단위)
    scheduled_at: datetime  # 근무 시간 · 조용한 시간을 반영한 실제 발송 시각
    skip: str | None = None  # 보내지 않고 남길 이유(부재 중)
    also: list["Send"] = field(default_factory=list)  # 같은 업무 · 같은 시각이라 이 알림 한 번으로 함께 처리한 것(기록만 남김)


def _base_slot(item: dict, p: pol.Policy, at: datetime, h: dict | None) -> tuple[str, datetime] | None:
    """규칙이 정한 이번 알림 시각. 아직 때가 아니거나 더 보낼 것이 없으면 None."""
    notify = item["_notify"]
    created = item["created_at"]
    if notify == MORNING:
        slot = p.latest_morning(at)
        gate = created
        if h and h["last_sent_slot"] is not None and h["count"]:
            gate = max(gate, h["last_sent_slot"] + pol.BACKOFF[min(h["count"], len(pol.BACKOFF)) - 1])
        if h and h["last_slot"] is not None:
            gate = max(gate, h["last_slot"] + timedelta(minutes=1))  # 건너뛴 아침(부재 중 등)은 다시 보내지 않는다
        if slot is None or slot < gate:
            return None
        return RULE_NAME[MORNING], slot
    if notify == DUE:
        due = item["due_at"]
        return RULE_NAME[DUE], max(due - pol.DUE_BEFORE, created)
    if notify == SNOOZE:
        return RULE_NAME[SNOOZE], created
    if notify == MEETING:
        return RULE_NAME[MEETING], created
    if notify == IMMEDIATE:
        return RULE_NAME[IMMEDIATE], created
    return None


def _adjust(item: dict, notify: str, slot: datetime, p: pol.Policy) -> datetime | None:
    """근무 시간에만 보낸다(명세 4.2절 2번). 기한 임박만 근무 시간 밖에도 기한 전에 보내되 조용한 시간은 피한다.
    R-아침은 사용자가 고른 시각이라 근무 시작 전이어도 그대로 보낸다(근무일만, BE-D28)."""
    if notify == DUE and item["type"] == "due_soon":
        return p.outside_quiet(slot)
    if notify == MORNING:
        return p.outside_quiet(slot)
    return p.next_work(slot)


def _snooze_alert(item: dict, at: datetime, p: pol.Policy) -> dict | None:
    """미룬 시각이 지나 다시 열린 업무인데 카드가 다른 유형(기한 임박 · 기한 경과 등)이면, 미룬 시각에 보낼 '연기 업무' 알림 항목.
    카드는 하나로 두고 알림만 따로 만든다. 사용자가 고른 시각이라 3번 상한을 받지 않는다(_quiet).
    알림 끄기는 카드 유형이 아니라 '연기 업무' 설정을 따른다(기한 임박을 꺼도 직접 고른 시각 알림은 간다)."""
    until = item.get("_snoozed_until")
    if until is None or item["type"] == "snooze_due" or item["_subject"][0] != "task":
        return None
    t = TYPES["snooze_due"]
    return {**item, "key": rules.make_key("snooze_due", *item["_subject"]), "type": "snooze_due", "type_label": t.label,
            "group": t.group, "reason": f"연기한 시각({rules.when(until, at)})이 되었습니다", "created_at": until,
            "_notify": SNOOZE, "state": "active", "_muted": "snooze_due" in p.mute}


def plan(db: Session, user_id: int, at: datetime, its: list[dict] | None = None) -> list[Send]:
    """지금(at) 보낼 알림. 쓰지 않는다."""
    p = pol.load(db, user_id)
    if p.away(at):
        return []  # 부재 중에는 아무 알림도 보내지 않는다(명세 4.2절 3번). 목록은 그대로
    its = items(db, user_id, at) if its is None else its
    hist = history(db, user_id)
    out = []
    for i in its:
        if i["_not_mine"]:
            continue
        sends = [s for c in (i, _snooze_alert(i, at, p)) if c is not None and (s := _send(c, p, at, hist))]
        # 같은 업무의 두 알림(카드 유형 · 미룬 시각)이 같은 시각이면 한 번만 보내고 둘 다 처리한 것으로 기록한다
        if len(sends) == 2 and sends[0].scheduled_at == sends[1].scheduled_at:
            sends[0].also.append(sends.pop())
        out += sends
    return out


def _send(i: dict, p: pol.Policy, at: datetime, hist: dict) -> Send | None:
    """항목 하나를 지금 보낼지. 보낼 것이면 Send, 아니면 None."""
    if i["_notify"] is None or i["_muted"] or i["state"] == "quiet":
        return None
    h = hist.get((*i["_subject"], i["type"]))
    base = _base_slot(i, p, at, h)
    if base is None:
        return None
    rule, slot = base
    if h and (rule, pol.slot_str(slot)) in h["slots"]:
        return None  # 이 시각은 이미 다뤘다(보냈거나 건너뜀)
    when = _adjust(i, i["_notify"], slot, p)
    if when is None or when > at:
        return None
    skip = "away" if p.away_until is not None and when < p.away_until else None
    return Send(i, rule, slot, when, skip)


# ---------- ③ 보내기 직전 재확인 ----------

def recheck(db: Session, user_id: int, send: Send, at: datetime) -> str | None:
    """보내기 직전에 DB를 다시 읽는다(detail 4.2절). 그사이 완료 · 제외 · 미룸 · 숨김이 됐으면 이유를 돌려준다."""
    i = send.item
    if db.scalar(select(SuggestionHide.id).where(SuggestionHide.user_id == user_id, SuggestionHide.key == i["key"],
                                                 SuggestionHide.until > at)) is not None:
        return "hidden"
    kind, sid = i["_subject"]
    if kind == "task":
        row = db.execute(select(Task.status, Task.snoozed_until).where(Task.id == sid)).first()
        if row is None:
            return "deleted"
        if row.status in ("done", "excluded"):
            return row.status
        if row.status == "snoozed" and row.snoozed_until is not None and row.snoozed_until > at:
            return "snoozed"
    elif kind == "commitment":
        status = db.scalar(select(Commitment.status).where(Commitment.id == sid))
        if status != "open":
            return f"commitment_{status or 'deleted'}"
    if db.scalar(select(ReminderFeedback.id).where(ReminderFeedback.user_id == user_id, ReminderFeedback.key == i["key"],
                                                   ReminderFeedback.reason.in_(("stop_waiting", "keep", "wrong_signal")),
                                                   (ReminderFeedback.ref_id == i["_ref"]) if i["_ref"] else true())) is not None:
        return "dismissed"
    return None


# ---------- ④ 쓰기 ----------

def _row(user_id: int, send: Send, at: datetime, **kw) -> Reminder:
    i = send.item
    kind, sid = i["_subject"]
    return Reminder(user_id=user_id, task_id=sid if kind == "task" else None, type=i["type"], subject_kind=kind,
                    subject_id=sid, rule=send.rule, slot=pol.slot_str(send.slot), scheduled_at=send.scheduled_at, **kw)


def _insert(db: Session, row: Reminder) -> bool:
    """유일 제약으로 중복을 막는다. 같은 줄이 이미 있으면(다른 틱 · 다른 프로세스가 먼저 씀) False."""
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
        return True
    except IntegrityError:
        return False


def _sent_row(user_id: int, s: Send, at: datetime, hist: dict) -> Reminder:
    h = hist.get((*s.item["_subject"], s.item["type"]))
    count = (h["count"] if h else 0) + 1
    return _row(user_id, s, at, sent_at=at, notify_count=count, last_notified_at=at,
                state="quiet" if _quiet(s.item, count) else "active")


def _notification(user_id: int, at: datetime, **kw) -> Notification:
    return Notification(user_id=user_id, created_at=at, scheduled_at=at, **kw)


def deliver(db: Session, user_id: int, sends: list[Send], at: datetime) -> dict:
    """재확인 → 기록 → 알림. 같은 분에 DIGEST_MIN건 이상이면 묶음 한 건. 커밋은 부르는 쪽이 한다."""
    hist = history(db, user_id)
    out = {"sent": [], "skipped": [], "notifications": []}
    ready: list[tuple[Send, list[Reminder]]] = []  # (보낼 것, 이 알림으로 기록할 줄들 — 함께 처리한 것 포함)
    for s in sends:
        reason = s.skip or recheck(db, user_id, s, at)
        if reason:
            for x in (s, *s.also):
                if _insert(db, _row(user_id, x, at, skipped_reason=reason)):
                    out["skipped"].append({"key": x.item["key"], "reason": reason})
            continue
        rows = [row for x in (s, *s.also) if _insert(db, row := _sent_row(user_id, x, at, hist))]
        if rows and rows[0].type == s.item["type"] and rows[0].rule == s.rule:
            ready.append((s, rows))  # 대표 줄을 이 틱이 새로 썼을 때만 보낸다(다른 틱 · 프로세스가 먼저 썼으면 그쪽이 보냈다)
    if not ready:
        return out
    if len(ready) >= pol.DIGEST_MIN:
        n = _digest(db, user_id, at, [s.item for s, _ in ready], type_="digest", rule=ready[0][0].rule,
                    title=f"챙길 것 {len(ready)}건")
        for _, rows in ready:
            for row in rows:
                row.channel, row.notification_id = "digest", n.id
        out["notifications"].append(n.id)
    else:
        for s, rows in ready:
            row = rows[0]
            i = s.item
            n = _notification(user_id, at, kind="reply_confirm" if i["type"] == "reply_confirm" else "reminder",
                              type=i["type"], group=i["group"], reminder_key=i["key"], reminder_keys=[i["key"]],
                              reminder_id=row.id, rule=s.rule, task_ids=i["task_ids"], title=i["title"][:255],
                              body=f"{label(i['type'])} · {i['reason']}")
            db.add(n)
            db.flush()
            for x in rows:  # 함께 처리한 줄도 같은 알림에 묶는다
                x.channel, x.notification_id = "center", n.id
            out["notifications"].append(n.id)
    out["sent"] = [s.item["key"] for s, _ in ready]
    db.flush()
    return out


def _digest(db: Session, user_id: int, at: datetime, its: list[dict], *, type_: str, rule: str | None, title: str,
            body: str | None = None) -> Notification:
    counts = Counter(i["type"] for i in its)
    body = body or " · ".join(f"{label(t)} {n}" for t, n in counts.most_common())
    task_ids = sorted({t for i in its for t in i["task_ids"]})
    n = _notification(user_id, at, kind="digest", type=type_, rule=rule, reminder_keys=[i["key"] for i in its],
                      task_ids=task_ids, title=title, body=body)
    db.add(n)
    db.flush()
    return n


# ---------- 부재 중 복귀 · 퇴근 · 주간 회고 ----------

def _day_row(user_id: int, rule: str, at_slot: datetime, at: datetime, **kw) -> Reminder:
    return Reminder(user_id=user_id, task_id=None, type="briefing", subject_kind="day",
                    subject_id=int(at_slot.strftime("%Y%m%d")), rule=rule, slot=pol.slot_str(at_slot),
                    scheduled_at=at_slot, **kw)


def _briefing_sends(db: Session, user_id: int, at: datetime, its: list[dict]) -> list[int]:
    """부재 중 복귀 브리핑(명세 4.2절 3번) · 퇴근 회고 · 주간 회고(4.3절). 시각마다 한 번(reminders 유일 제약)."""
    p = pol.load(db, user_id)
    if p.away(at):
        return []
    out = []
    if p.away_until is not None:
        back = p.next_work(p.away_until)
        if back is not None and back <= at:
            active = [i for i in its if i["state"] != "quiet"]
            row = _day_row(user_id, "R-복귀", p.away_until, at, sent_at=at if active else None,
                           skipped_reason=None if active else "empty")
            if _insert(db, row) and active:
                n = _digest(db, user_id, at, active, type_="away_return", rule="R-복귀",
                            title=f"자리를 비운 동안 쌓인 것 {len(active)}건")
                row.notification_id, row.channel = n.id, "digest"
                out.append(n.id)
    today = at.date()
    if p.is_work_day(today):
        for kind, rule, slot in (("evening", "R-퇴근", p.evening(today)),
                                 ("weekly", "R-주간", p.evening(today) if today.isoweekday() == pol.WEEKLY_DAY else None)):
            if slot is None or not (slot <= at < slot + timedelta(hours=1)) or p.in_quiet(slot):
                continue  # 그 시각에서 1시간 안에만(늦게 켜진 서버가 밤에 회고를 보내지 않게)
            b = briefings.build(db, user_id, kind, today, at)
            row = _day_row(user_id, rule, slot, at, sent_at=at if b["total"] else None,
                           skipped_reason=None if b["total"] else "empty")
            row.type = f"briefing_{kind}"
            if _insert(db, row) and b["total"]:
                n = _notification(user_id, at, kind="digest", type=kind, rule=rule, reminder_keys=[], task_ids=[],
                                  title=b["title"], body=b["summary"])
                db.add(n)
                db.flush()
                row.notification_id, row.channel = n.id, "digest"
                out.append(n.id)
    return out


# ---------- 실행 ----------

def run(db: Session, user_id: int, at: datetime | None = None) -> dict:
    """한 사용자 · 한 시각. 커밋한다."""
    at = (at or now()).replace(second=0, microsecond=0)
    its = items(db, user_id, at)
    out = deliver(db, user_id, plan(db, user_id, at, its), at)
    out["notifications"] += _briefing_sends(db, user_id, at, its)
    db.commit()
    return {"user_id": user_id, **out}


def run_all(db: Session, at: datetime | None = None) -> list[dict]:
    """모든 사용자. 한 사용자가 실패해도 다음 사용자는 돈다."""
    at = at or now()
    results = []
    for user_id in db.scalars(select(User.id).order_by(User.id)).all():
        try:
            results.append(run(db, user_id, at))
        except Exception:  # noqa: BLE001 - 스케줄러는 죽지 않는다
            db.rollback()
            log.exception("리마인더 엔진 실패(user %s)", user_id)
            results.append({"user_id": user_id, "error": True, "sent": [], "skipped": [], "notifications": []})
    return results

