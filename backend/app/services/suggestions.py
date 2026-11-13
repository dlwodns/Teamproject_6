"""에이전트 제안 카드 판정 (D50 · `docs/10_planning/suggestion_cards.md`).

카드를 띄울지는 저장된 값(업무 상태 · 기한 · 발신자 · 보낸 메일)으로만 정한다. 모델을 부르지 않는다.
이 모듈은 **읽기만 한다**. 어떤 행동도 실행하지 않고 어떤 행도 쓰지 않는다(PL-16 S1). 숨기기만 hide()가 쓴다.

지금 만드는 카드: ① 아침 요약 · ② 기한 지남 · ③ 기한 임박 · ④ 상급자 · ⑥ 응답 대기.
- ⑤ 일정 참석은 캘린더(T15)가 backend에 생기는 11/21에 붙인다. 조건은 메일 성격(mails.kind)이 회의 · 행사 초대(K09)인
  메일이다(D50 #41). 업무마다 '일정참석' 같은 유형은 저장하지 않으므로 그 값으로 판정하지 않는다.
- ④의 ASAP(급함) 조건은 아직 붙이지 않아 상급자 조건만 본다. 급함 칸(tasks.urgent, #30)은 생겼고 분류 결과로 채운다.
"""
import re
from datetime import datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.models import Account, Contact, Mail, SuggestionHide, Task, UserSettings

RULES = ("morning", "overdue", "due_soon", "priority_sender", "meeting", "no_reply")  # 표시 순서(①~⑥)
DUE_SOON = timedelta(hours=24)  # [제안] suggestion_cards.md 3절 ③
SUPERIOR_AFTER = timedelta(hours=2)  # [제안] 3절 ④
DEFAULT_REMIND = "08:30"
DEFAULT_AWAIT_DAYS = 3
DRAFT_CATEGORIES = ("회신", "요청", "검토")  # 답장으로 끝나는 업무 → 주 버튼 [초안 보기] (3.1절)
NOT_REQUEST_SENT = ("공지", "기타")
REPLY_PREFIX = re.compile(r"^\s*(re|fw|fwd|회신|답장|전달)\s*[:：]", re.IGNORECASE)
KEY = re.compile(r"^(morning|overdue|due_soon|priority_sender|meeting|no_reply):[0-9A-Za-z:_\-]{1,80}$")
WEEKDAYS = "월화수목금토일"


class SuggestionError(Exception):
    pass


# ---------- 시각 · 문구 ----------

def _hm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


def _settings(db: Session, user_id: int) -> tuple[time, int]:
    s = db.get(UserSettings, user_id)
    remind = _hm(s.remind_time if s and s.remind_time else DEFAULT_REMIND)
    days = s.awaiting_reply_days if s and s.awaiting_reply_days is not None else DEFAULT_AWAIT_DAYS
    return remind, max(1, days)  # 0 이하는 1일로 본다(같은 날 보낸 요청까지 모두 잡지 않게)


MIN_HIDE = timedelta(hours=1)


def next_morning(at: datetime, remind: time) -> datetime:
    """숨김이 풀리는 때: 다음 R-아침 시각. 그 시각까지 1시간도 안 남았으면 그다음 날 R-아침
    (08:29에 숨긴 카드가 1분 뒤 다시 뜨지 않게 하는 방어선, 확정: 문규남 11-11 · BE-D16)."""
    today = datetime.combine(at.date(), remind)
    until = today if at < today else today + timedelta(days=1)
    return until if until - at >= MIN_HIDE else until + timedelta(days=1)


def _when(dt: datetime, at: datetime) -> str:
    hm = dt.strftime("%H:%M")
    gap = (dt.date() - at.date()).days
    if gap == 0:
        return f"오늘 {hm}"
    if gap == 1:
        return f"내일 {hm}"
    return f"{dt.month}/{dt.day}({WEEKDAYS[dt.weekday()]}) {hm}"


def _short(text: str, n: int = 30) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _who(mail: Mail, contact: Contact | None, facts: dict | None = None) -> str:
    """'김민준 팀장님'. 문맥 기억(BE-D21)이 있으면 맡은 일을, 없으면 소속을 괄호로 붙인다: '장민호 차장님(한빛은행 IT기획부)'."""
    name = (contact.name if contact and contact.name else None) or mail.sender.split("@")[0]
    position = contact.position if contact else None
    who = f"{name} {position}님" if position else f"{name}님"
    facts = facts or {}
    if facts.get("works_on"):
        return f"{who}({facts['works_on']} 담당)"
    if facts.get("org"):
        return f"{who}({facts['org']})"
    return who


# ---------- 버튼 ----------

def _btn(label: str, action: str, *, task_ids=(), mail_ids=(), params=None, primary=False, kind="action") -> dict:
    return {"label": label, "kind": kind, "action": action, "primary": primary, "params": params or {},
            "target": {"task_ids": list(task_ids), "mail_ids": list(mail_ids)}}


def _task_buttons(task: Task, mail: Mail) -> tuple[list[dict], list[dict]]:
    if mail.category in DRAFT_CATEGORIES:
        first = _btn("초안 보기", "T07", task_ids=[task.id], mail_ids=[mail.id], params={"tone": "polite"}, primary=True)
    else:  # 조치요청 등 답장으로 끝나지 않는 업무는 메일로 보낸다(행동 아님)
        first = _btn("메일 열기", "open_mail", task_ids=[task.id], mail_ids=[mail.id], primary=True, kind="navigate")
    buttons = [first,
               _btn("나중에", "T05", task_ids=[task.id], mail_ids=[mail.id], params={"until": None}),
               _btn("완료", "T03", task_ids=[task.id], mail_ids=[mail.id])]
    menu = [_btn("업무 아님", "T10", task_ids=[task.id], mail_ids=[mail.id]),
            _btn("이 제안 숨기기", "hide", kind="hide")]
    return buttons, menu


def _card(key: str, rule: str, created_at: datetime, title: str, buttons: list[dict], menu: list[dict] | None = None,
          task_ids=(), mail_ids=(), detail: list[str] | None = None, sort=None) -> dict:
    return {"key": key, "rule": rule, "via": f"suggestion:{rule}", "created_at": created_at, "title": title,
            "detail": detail or [], "task_ids": list(task_ids), "mail_ids": list(mail_ids), "buttons": buttons,
            "menu": menu if menu is not None else [_btn("이 제안 숨기기", "hide", kind="hide")], "_sort": sort}


# ---------- 판정 ----------

def _open_tasks(db: Session, user_id: int, at: datetime) -> list[tuple[Task, Mail]]:
    """미처리 업무: pending, 또는 나중에(snoozed)인데 그 시각이 지난 것. 받은 메일의 업무만."""
    rows = db.execute(
        select(Task, Mail).join(Mail, Task.mail_id == Mail.id).join(Account, Mail.account_id == Account.id)
        .where(Account.user_id == user_id, Mail.direction == "received",
               (Task.status == "pending") | ((Task.status == "snoozed") & (Task.snoozed_until <= at)))
    ).all()
    return [(t, m) for t, m in rows]


def _contacts(db: Session, user_id: int) -> dict[str, Contact]:
    return {c.email.lower(): c for c in db.scalars(select(Contact).where(Contact.user_id == user_id))}


def _since(task: Task, mail: Mail, formula: datetime) -> datetime:
    """카드 조건이 처음 맞은 시각. 메일이 늦게 왔거나 '나중에'가 풀린 경우에는 그 시각이다(✦ 배지의 '새 카드' 판정)."""
    marks = [formula, mail.sent_at]
    if task.status == "snoozed" and task.snoozed_until is not None:
        marks.append(task.snoozed_until)
    return max(marks)


def _task_card(task: Task, mail: Mail, contact: Contact | None, at: datetime, facts: dict | None = None) -> dict | None:
    """업무 하나에 카드 하나. ② → ③ → ④ 순서에서 처음 걸리는 것만(2절 원칙 4).
    기한 지남의 D+n은 날짜 차이다(어제 23:30 기한을 오늘 00:10에 보면 D+1)."""
    who, what = _who(mail, contact, facts), _short(task.text)
    buttons, menu = _task_buttons(task, mail)
    common = {"buttons": buttons, "menu": menu, "task_ids": [task.id], "mail_ids": [mail.id]}
    if task.due_at is not None and task.due_at < at:
        days = (at.date() - task.due_at.date()).days
        late = f"기한이 D+{days} 지났어요" if days >= 1 else f"기한({task.due_at:%H:%M})이 지났어요"
        return _card(f"overdue:task:{task.id}", "overdue", _since(task, mail, task.due_at), f"{who} '{what}' {late}.",
                     sort=(task.due_at, mail.sent_at), **common)
    if task.due_at is not None and task.due_at - at <= DUE_SOON:
        ask = "초안을 써 둘까요?" if buttons[0]["action"] == "T07" else "메일을 확인해 볼까요?"
        return _card(f"due_soon:task:{task.id}", "due_soon", _since(task, mail, task.due_at - DUE_SOON),
                     f"{who} '{what}' 기한이 {_when(task.due_at, at)}이에요. {ask}", sort=(task.due_at, mail.sent_at),
                     **common)
    if contact is not None and contact.is_superior and at - mail.sent_at >= SUPERIOR_AFTER:
        hours = int((at - mail.sent_at).total_seconds() // 3600)
        ago = f"{hours}시간" if hours < 24 else f"{hours // 24}일"
        return _card(f"priority_sender:task:{task.id}", "priority_sender",
                     _since(task, mail, mail.sent_at + SUPERIOR_AFTER),
                     f"{who} 메일을 받은 지 {ago} 지났어요.", sort=(task.due_at or datetime.max, mail.sent_at), **common)
    return None


def morning_window(day, remind: time) -> tuple[datetime, datetime]:
    """그날 아침 요약 카드가 뜨는 때. 기본은 R-아침부터 정오 전까지.
    정오까지 1시간이 안 남았거나 정오 뒤로 옮긴 사용자는 R-아침부터 4시간(자정을 넘을 수 있다)."""
    start = datetime.combine(day, remind)
    noon = datetime.combine(day, time(12, 0))
    return start, (noon if noon - start >= timedelta(hours=1) else start + timedelta(hours=4))


def _morning(open_tasks: list[tuple[Task, Mail]], remind: time, at: datetime) -> dict | None:
    if not open_tasks:
        return None
    for day in (at.date(), at.date() - timedelta(days=1)):  # 어제 저녁에 시작한 창이 자정을 넘었을 수 있다
        start, end = morning_window(day, remind)
        if start <= at < end:
            break
    else:
        return None
    today = sum(1 for t, _ in open_tasks if t.due_at is not None and t.due_at.date() == at.date())
    day = start.date().isoformat()
    return _card(f"morning:{day}", "morning", start, f"오늘 챙길 업무 {len(open_tasks)}건, 그중 오늘 마감 {today}건이에요.",
                 [_btn("오늘 요약 보기", "T01", params={"date": day}, primary=True)], sort=(start,))


def is_request_sent(mail: Mail) -> bool:
    """보낸 메일 중 상대의 답이 필요한 요청 메일인가 (기획 detail 5절, 판정 방법은 [결정 필요]).
    [제안] 공지 · 기타로 분류된 메일과 답장 · 전달(제목 머리말 RE: · FW: · 회신: 등)은 뺀다."""
    if mail.category in NOT_REQUEST_SENT:
        return False
    return not REPLY_PREFIX.match(mail.subject or "")


NO_REPLY_KEY = "no_reply:waiting"


def _no_reply(db: Session, user_id: int, days: int, at: datetime) -> dict | None:
    """같은 계정 · 같은 대화에 나 아닌 사람의 받은 메일이 보낸 뒤로 없으면 응답 대기.
    대화 id는 메일함마다 따로 매겨지므로 계정이 달라도 같은 값이 나올 수 있어 계정까지 맞춘다.
    내가 속한 목록으로 돌아온 내 메일 사본(발신자가 내 계정 주소)은 답장이 아니다."""
    limit = at - timedelta(days=days)
    accounts = db.execute(select(Account.id, Account.email).where(Account.user_id == user_id)).all()
    if not accounts:
        return None
    account_ids = [a.id for a in accounts]
    mine = {a.email.lower() for a in accounts}
    sent = [m for m in db.scalars(
        select(Mail).where(Mail.account_id.in_(account_ids), Mail.direction == "sent",
                           Mail.conversation_id.is_not(None), Mail.sent_at <= limit).order_by(Mail.sent_at, Mail.id)
    ) if is_request_sent(m)]
    if not sent:
        return None
    convs = {m.conversation_id for m in sent}
    latest: dict[tuple[int, str], datetime] = {}  # (계정, 대화) → 나 아닌 사람에게 받은 가장 늦은 메일 시각
    for acc, conv, sender, sent_at in db.execute(
            select(Mail.account_id, Mail.conversation_id, Mail.sender, Mail.sent_at)
            .where(Mail.account_id.in_(account_ids), Mail.direction == "received", Mail.conversation_id.in_(convs))):
        if sender.lower() in mine:
            continue
        k = (acc, conv)
        if k not in latest or sent_at > latest[k]:
            latest[k] = sent_at
    waiting = [m for m in sent if not ((r := latest.get((m.account_id, m.conversation_id))) and r > m.sent_at)]
    if not waiting:
        return None
    return _card(NO_REPLY_KEY, "no_reply", waiting[-1].sent_at + timedelta(days=days),
                 f"보낸 요청 {len(waiting)}건에 {days}일 넘게 답이 없어요.",
                 [_btn("응답 대기 보기", "T06", mail_ids=[m.id for m in waiting], primary=True)],
                 mail_ids=[m.id for m in waiting], detail=[_short(m.subject or "(제목 없음)", 40) for m in waiting[:3]],
                 sort=(waiting[0].sent_at,))


def compute(db: Session, user_id: int, at: datetime | None = None) -> list[dict]:
    """지금 띄울 카드 전체(숨긴 것 제외), 표시 순서대로."""
    at = at or now()
    remind, days = _settings(db, user_id)
    open_tasks = _open_tasks(db, user_id, at)
    contacts = _contacts(db, user_id)
    from app.services.memory import facts_by_contact  # memory가 suggestions를 부르지 않으므로 순환 없음

    facts = facts_by_contact(db, user_id)
    cards = []
    if c := _morning(open_tasks, remind, at):
        cards.append(c)
    for task, mail in open_tasks:
        contact = contacts.get(mail.sender.lower())
        if c := _task_card(task, mail, contact, at, facts.get(contact.id) if contact else None):
            cards.append(c)
    if c := _no_reply(db, user_id, days, at):
        cards.append(c)
    hides = {h.key: h for h in db.scalars(select(SuggestionHide).where(SuggestionHide.user_id == user_id,
                                                                         SuggestionHide.until > at))}
    cards = [c for c in cards if not _is_hidden(c, hides.get(c["key"]))]
    cards.sort(key=lambda c: (RULES.index(c["rule"]), c["_sort"]))
    for c in cards:
        del c["_sort"]
    return cards


def _is_hidden(card: dict, h: SuggestionHide | None) -> bool:
    """응답 대기는 숨긴 때 기다리던 메일만 남아 있으면 계속 숨긴다. 새로 기다리는 메일이 생기면 다시 뜬다
    (숨긴 뒤 몇 건에 답이 와도 다시 뜨지 않는다)."""
    if h is None:
        return False
    if card["rule"] == "no_reply":
        return set(card["mail_ids"]) <= set(h.mail_ids or [])
    return True


def hide(db: Session, user_id: int, key: str, at: datetime | None = None) -> SuggestionHide:
    """[이 제안 숨기기]. 다음 R-아침까지. 커밋은 부르는 쪽이 한다."""
    if not KEY.fullmatch(key):
        raise SuggestionError(f"카드 키 형식이 아닙니다: {key}")
    at = at or now()
    remind, days = _settings(db, user_id)
    until = next_morning(at, remind)
    mail_ids = []
    if key == NO_REPLY_KEY and (card := _no_reply(db, user_id, days, at)):
        mail_ids = card["mail_ids"]
    row = db.scalar(select(SuggestionHide).where(SuggestionHide.user_id == user_id, SuggestionHide.key == key))
    if row is None:
        row = SuggestionHide(user_id=user_id, key=key, until=until, created_at=at, mail_ids=mail_ids)
        db.add(row)
    else:
        row.until, row.created_at, row.mail_ids = until, at, mail_ids
    db.flush()
    return row
