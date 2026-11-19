"""요약 · 회고 머리 문장 미리 만들기 (AI-29, ai io_spec 3절).

정한 시각(아침 R-아침 · 퇴근 회고 · 금요일 주간 회고)부터 1시간 안에 한 번, 그 브리핑의 묶음을 ai `/summarize`에 보내
머리 문장(최대 3문장)을 받아 briefing_headlines에 저장한다. 모델 1회가 수 분이라(AI-D21) 화면 · 대화는 저장본만 읽는다
(app/reminders/briefings.build). 목록 · 건수는 코드가 세고 모델은 문장만 쓴다.
- 보내기 전에 개인정보를 가리고(BE-6) 받은 문장은 되돌린다.
- ai가 꺼져 있거나 제한 시간을 넘기면 저장하지 않는다 → 다음 틱(1시간 안)에 다시 부른다. 그래도 없으면 화면은 건수 문장.
- ai가 모델 실패로 코드 문장을 주면 그것을 저장한다(source=code, fallback에 사유).
- 끄기: BRIEFING_HEADLINE=0. 스케줄러(REMINDER_SCHEDULER=1)가 켜져 있을 때만 돈다.
"""
import logging
import os
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import privacy
from app.ai_client.client import AIClient, AIError
from app.core.clock import now
from app.models import BriefingHeadline, Mail, Task, User
from app.reminders import briefings, rules
from app.reminders import policy as pol

log = logging.getLogger("app.reminders.headlines")
EVENT_TYPE = "일정참석"  # 시각이 정해진 일정(ai SummaryItem.is_event)
MORNING_IDS = ("overdue", "due_today_allday", "due_today_am", "due_today_pm")
RETRY_AFTER = timedelta(minutes=20)  # 코드 문장을 저장한 뒤 다시 불러 볼 간격
WINDOW = timedelta(hours=1)  # 정한 시각에서 1시간 안에만(늦게 켜진 서버가 밤에 아침 요약을 만들지 않게)


def enabled() -> bool:
    return os.environ.get("BRIEFING_HEADLINE", "").strip().lower() not in ("0", "off", "false")


def _person(ctx: rules.Context, address: str) -> tuple[str, bool]:
    """ai에 보낼 '이름 직책'(님 · 담당 업무 없이)과 상급자 여부. 연락처 이름이 없으면 주소 전체(가리개가 user1@도메인으로 가린다 —
    앞부분만 보내면 가려지지 않는다)."""
    c = ctx.contact(address)
    if not (c and c.name):
        return address or "", bool(c and c.is_superior)
    return (f"{c.name} {c.position}" if c.position else c.name), c.is_superior


def payload(db: Session, user_id: int, b: dict) -> dict:
    """브리핑 묶음 → ai `/summarize` 요청(io_spec 3.5절). 아침은 mode=today(items), 회고는 sections."""
    ctx = rules.Context(db, user_id, b["as_of"])
    ids = {x["task_id"] for s in b["sections"] for x in s["items"] if x["task_id"] is not None}
    rows = {t.id: (t, m) for t, m in db.execute(select(Task, Mail).join(Mail, Task.mail_id == Mail.id).where(Task.id.in_(ids)))}

    def item(line: dict) -> dict:
        t, m = rows.get(line["task_id"], (None, None))
        if t is None:  # 회신 대기 같은 업무 아닌 줄
            return {"task_id": None, "text": line["title"], "due_at": line["due_at"]}
        sender, sup = _person(ctx, m.sender)
        return {"task_id": str(t.id), "text": t.text, "sender": sender, "is_superior": sup, "is_event": t.type == EVENT_TYPE,
                "due_at": t.due_at, "due_time_stated": t.due_time_stated, "done_at": t.done_at}

    if b["kind"] == "morning":
        lines = [x for s in b["sections"] if s["id"] in MORNING_IDS for x in s["items"]]
        items = [{**item(x), "status": "pending"} for x in lines if x["task_id"] is not None]
        no_reply = next((s["count"] for s in b["sections"] if s["id"] == "no_reply"), 0)
        return {"mode": "today", "now": b["as_of"], "items": items, "awaiting_reply_count": no_reply}
    mode = "evening" if b["kind"] == "evening" else "weekly"
    return {"mode": mode, "now": b["as_of"],
            "sections": [{"id": s["id"], "label": s["label"], "items": [item(x) for x in s["items"]]} for s in b["sections"]]}


def make(db: Session, user_id: int, kind: str, day: date, ai: AIClient, at: datetime | None = None) -> BriefingHeadline | None:
    """한 브리핑의 머리 문장을 만들어 저장한다. 이미 있거나 · 묶음이 비었으면 None.
    모델 실패로 코드 문장(source=code)을 저장했으면 RETRY_AFTER가 지난 뒤 한 번 더 부른다(한도를 매 분 쓰지 않게).
    ai가 꺼졌거나 제한 시간을 넘기면 AIError를 그대로 올린다 — 이번 틱의 남은 호출을 멈춘다(run)."""
    at = at or now()
    old = briefings.headline(db, user_id, kind, day)
    if old is not None and (old.source != "code" or at - old.created_at < RETRY_AFTER):
        return None
    b = briefings.build(db, user_id, kind, day, at)
    if not b["total"]:
        return None
    masker = privacy.masker_for(db, user_id)
    try:
        r = masker.unmask_model(ai.summarize(masker.mask_obj(payload(db, user_id, b))))
    except AIError as e:
        log.warning("머리 문장 실패(user %s %s %s): %s", user_id, kind, day, e.kind)
        if e.kind in ("timeout", "unavailable"):
            raise
        if old is not None:  # 다시 부르다 실패해도 다음 시도는 RETRY_AFTER 뒤(매 분 부르지 않게)
            old.created_at = at
            db.commit()
        return None
    # 다시 불러도 코드 문장이면 새 코드 문장 · 시각으로 덮는다 — created_at이 바뀌어 다음 시도도 RETRY_AFTER 뒤다
    row = old or BriefingHeadline(user_id=user_id, kind=kind, day=briefings.headline_day(kind, day))
    row.text, row.source, row.prompt_version, row.fallback, row.created_at = r.text, r.source, r.prompt_version, r.fallback, at
    db.add(row)
    try:
        db.commit()
    except IntegrityError:  # 다른 틱이 먼저 저장했다
        db.rollback()
        return None
    return row


def due(db: Session, user_id: int, at: datetime) -> list[str]:
    """지금(at) 만들 브리핑 종류: 근무일이고 정한 시각부터 1시간 안.

    정한 시각부터 1시간이 조용한 시간 · 부재 중과 모두 겹치면 그날 머리 문장은 만들지 않고, 화면은 건수 문장만 보인다(#228 리뷰).
    """
    p = pol.load(db, user_id)
    if not p.is_work_day(at.date()) or p.away(at) or p.in_quiet(at):  # 부재 중 · 조용한 시간에는 업무 내용을 밖으로 보내지 않는다
        return []
    out = []
    for kind in briefings.KINDS:
        if kind == "weekly" and at.isoweekday() != pol.WEEKLY_DAY:
            continue
        slot = briefings.scheduled_at(kind, at.date(), p)
        if slot <= at < slot + WINDOW:
            out.append(kind)
    return out


def run(db: Session, ai: AIClient, at: datetime | None = None) -> int:
    """모든 사용자. 만든 수를 돌려준다. 한 사용자가 실패해도 다음 사용자는 돈다."""
    at = at or now()
    made = 0
    for user_id in db.scalars(select(User.id).order_by(User.id)).all():
        for kind in due(db, user_id, at):
            try:
                made += make(db, user_id, kind, at.date(), ai, at) is not None
            except AIError:  # ai가 꺼졌거나 매달림: 다음 사용자도 같을 것이라 이번 틱은 끝낸다(호출 1회 최대 620초)
                db.rollback()
                return made
            except Exception:  # noqa: BLE001 - 스케줄러는 죽지 않는다
                db.rollback()
                log.exception("머리 문장 만들기 실패(user %s %s)", user_id, kind)
    return made
