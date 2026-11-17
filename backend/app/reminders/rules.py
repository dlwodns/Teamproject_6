"""리마인더 항목 계산 — 지금 사용자가 챙길 것 (명세 reminders.md 2 · 3절, BE-D26 · BE-D27).

- 저장된 값(업무 상태 · 기한 · 발신자 · 보낸 메일 · 설정)과 AI 신호(commitments · reminder_signals)만 읽는다. 모델을 부르지 않고
  어떤 행도 쓰지 않는다(PL-16 S1). 알림을 몇 번 보냈는지(state · notify_count)는 engine.py가 붙인다.
- 제안 카드(D50, services/suggestions.py)의 판정 규칙을 여기로 옮겼다. 제안 카드 API는 이 목록의 앞쪽 N건을 카드 형식으로 바꿔 보낸다.
- 업무 하나에는 항목 하나. 여러 유형에 걸리면 types.TASK_PRIORITY에서 앞선 것만 띄운다(D50 원칙 4).
- 숨긴 항목(다음 R-아침까지)과 '회신 대기 종료' · 신호 거절은 목록에서 뺀다. 그 밖의 이유로 목록에서 영구히 빼지 않는다(누락 0, D13).
"""
import re
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.models import (Account, Commitment, Contact, Mail, ReminderFeedback, ReminderSignal, SuggestionHide, Task,
                        UserSettings)
from app.reminders import policy as pol
from app.reminders.types import TASK_PRIORITY, TYPES

DUE_SOON = timedelta(hours=24)  # 기한 임박(suggestion_cards.md 3절 ③)
SUPERIOR_AFTER = timedelta(hours=2)  # 상급자 메일(D50 ④)
STALE_AFTER = timedelta(days=3)  # 오래 둔 일: 기한 없는 미처리를 받은 지 3일
STALLED_AFTER = timedelta(days=2)  # 끊긴 대화: 나에게 온 질문에 2일째 답하지 않음
MY_PROMISE_NO_DUE = timedelta(days=3)  # 기한 없는 내 약속은 3일 뒤부터
CLUSTER_MIN = 3  # 기한 몰림: 하루 기한 3건 이상(명세 11절 결정 11-14, 시연 데이터 10/19 주 평일 6~10건 · 그 뒤 3건 이상은 하루)
MEETING_KIND = "K09"  # 메일 성격: 회의 · 행사 초대(D50 #41)
DRAFT_CATEGORIES = ("회신", "요청", "검토")  # 답장으로 끝나는 업무 → 주 버튼 [초안 보기]
QUESTION_CATEGORIES = ("회신",)  # 규칙으로 보는 '나에게 온 질문'(회신 요청). 그 밖에는 AI 신호(question)
NOT_REQUEST_SENT = ("공지", "기타")
REPLY_PREFIX = re.compile(r"^\s*(re|fw|fwd|회신|답장|전달)\s*[:：]", re.IGNORECASE)
KEY = re.compile(r"^([a-z_]{3,20}):(task|sent_mail|commitment|day):([0-9]{1,19})$")
WEEKDAYS = "월화수목금토일"
RESOLVED_REASON = {"done_by_other": "다른 담당자가 처리했다는 회신이 있습니다", "cancelled": "취소되었다는 회신이 있습니다",
                   "not_needed": "처리가 필요 없다는 회신이 있습니다"}


# ---------- 문구 ----------

def when(dt: datetime, at: datetime) -> str:
    hm = dt.strftime("%H:%M")
    gap = (dt.date() - at.date()).days
    if gap == 0:
        return f"오늘 {hm}"
    if gap == 1:
        return f"내일 {hm}"
    return f"{dt.month}/{dt.day}({WEEKDAYS[dt.weekday()]}) {hm}"


def day_label(d: date) -> str:
    return f"{d.month}/{d.day}({WEEKDAYS[d.weekday()]})"


def short(text: str, n: int = 30) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def who(address: str, contact: Contact | None, facts: dict | None = None) -> str:
    """'김민준 팀장님'. 문맥 기억(BE-D21)이 있으면 맡은 일을, 없으면 소속을 괄호로 붙인다."""
    name = (contact.name if contact and contact.name else None) or address.split("@")[0]
    position = contact.position if contact else None
    out = f"{name} {position}님" if position else f"{name}님"
    facts = facts or {}
    if facts.get("works_on"):
        return f"{out}({facts['works_on']} 담당)"
    if facts.get("org"):
        return f"{out}({facts['org']})"
    return out


def is_request_sent(mail: Mail) -> bool:
    """보낸 메일 중 상대의 답이 필요한 요청 메일인가 (기획 detail 5절, 판정 방법은 [결정 필요]).
    [제안] 공지 · 기타로 분류된 메일과 답장 · 전달(제목 머리말 RE: · FW: · 회신: 등)은 뺀다."""
    if mail.category in NOT_REQUEST_SENT:
        return False
    return not REPLY_PREFIX.match(mail.subject or "")


def make_key(type_: str, subject_kind: str, subject_id: int) -> str:
    return f"{type_}:{subject_kind}:{subject_id}"


def parse_key(key: str) -> tuple[str, str, int] | None:
    m = KEY.fullmatch(key)
    if not m or m.group(1) not in TYPES:
        return None
    return m.group(1), m.group(2), int(m.group(3))


# ---------- 버튼 ----------

def _act(id_: str, label: str, action: str, *, primary: bool = False, **params) -> dict:
    """action: 행동 레지스트리 T코드 · open_mail(메일 화면으로) · apply(POST …/apply) · dismiss(POST …/dismiss, params.reason)."""
    return {"id": id_, "label": label, "action": action, "primary": primary, "params": params}


def _task_actions(type_: str, task: Task, mail: Mail) -> list[dict]:
    draft = mail.category in DRAFT_CATEGORIES
    open_mail = _act("open_mail", "메일 열기", "open_mail", mail_id=mail.id)
    snooze = _act("snooze", "연기", "T05", until=None)
    done = _act("done", "완료 처리", "T03")
    not_mine = _act("not_mine", "담당 아님", "dismiss", reason="not_mine")
    if type_ in ("overdue", "due_soon", "priority_sender"):
        first = _act("draft", "회신 작성", "T07", mail_id=mail.id, tone="polite") if draft else open_mail
        acts = [first, snooze, done]
    elif type_ == "due_changed":
        acts = [_act("apply", "변경 기한 적용", "apply"), _act("keep", "현행 유지", "dismiss", reason="keep")]
    elif type_ in ("resolved", "reply_confirm"):
        acts = [_act("apply", "완료 처리", "apply"), _act("keep", "미완료 유지", "dismiss", reason="keep")]
    elif type_ == "snooze_due":
        acts = [done, _act("snooze", "재연기", "T05", until=None), open_mail]
    elif type_ == "cc_mention":
        acts = [open_mail, snooze, not_mine]
    elif type_ == "stale":
        acts = [done, snooze, not_mine]
    elif type_ == "stalled_thread":
        acts = [_act("draft", "회신 작성", "T07", mail_id=mail.id, tone="polite"), open_mail, snooze]
    elif type_ == "meeting_prep":
        acts = [open_mail, _act("draft", "참석 회신 작성", "T07", mail_id=mail.id, tone="polite")]
    else:
        acts = [open_mail]
    acts[0]["primary"] = True
    return acts[:3]


# ---------- 읽기 ----------

class Context:
    """한 사용자 · 한 시각의 판정 재료. 한 번 읽어 여러 규칙이 같이 쓴다."""

    def __init__(self, db: Session, user_id: int, at: datetime):
        self.db, self.user_id, self.at = db, user_id, at
        self.policy = pol.load(db, user_id)
        accounts = db.execute(select(Account.id, Account.email).where(Account.user_id == user_id)).all()
        self.account_ids = [a.id for a in accounts]
        self.mine = {a.email.lower() for a in accounts}
        self.contacts = {c.email.lower(): c for c in db.scalars(select(Contact).where(Contact.user_id == user_id))}
        from app.services.memory import facts_by_contact  # memory는 reminders를 부르지 않는다(순환 없음)

        self.facts = facts_by_contact(db, user_id)
        # 같은 계정 · 같은 대화의 메일(시각순). 대화 id는 메일함마다 따로 매겨지므로 계정까지 맞춘다
        self.threads: dict[tuple[int, str], list[Mail]] = defaultdict(list)
        if self.account_ids:
            for m in db.scalars(select(Mail).where(Mail.account_id.in_(self.account_ids), Mail.conversation_id.is_not(None))
                                .order_by(Mail.sent_at, Mail.id)):
                self.threads[(m.account_id, m.conversation_id)].append(m)
        self.feedback = list(db.scalars(select(ReminderFeedback).where(ReminderFeedback.user_id == user_id)))
        # '담당 아님'은 그 업무가 지금도 제외 상태일 때만 센다. 제외를 되돌렸으면(T04) 같은 발신자 · 유형 알림도 다시 켠다
        reported = {f.id: k[2] for f in self.feedback if f.reason == "not_mine" and (k := parse_key(f.key)) and k[1] == "task"}
        excluded = set(db.scalars(select(Task.id).where(Task.id.in_(set(reported.values())), Task.status == "excluded"))) \
            if reported else set()
        self.not_mine_marks = {(f.sender, f.type) for f in self.feedback if reported.get(f.id) in excluded}
        self.hides = {h.key for h in db.scalars(select(SuggestionHide).where(SuggestionHide.user_id == user_id,
                                                                            SuggestionHide.until > at))}

    def contact(self, address: str) -> Contact | None:
        return self.contacts.get((address or "").lower())

    def who(self, address: str) -> str:
        c = self.contact(address)
        return who(address, c, self.facts.get(c.id) if c else None)

    def counterpart(self, address: str | None) -> dict | None:
        if not address:
            return None
        c = self.contact(address)
        return {"email": address, "name": (c.name if c and c.name else address.split("@")[0]),
                "position": c.position if c else None, "label": self.who(address)}

    def thread(self, mail: Mail) -> list[Mail]:
        return self.threads.get((mail.account_id, mail.conversation_id), []) if mail.conversation_id else []

    def from_me(self, mail: Mail) -> bool:
        return mail.direction == "sent" or mail.sender.lower() in self.mine

    def dismissed(self, key: str, ref_id: int | None = None) -> bool:
        """'회신 대기 종료' · 신호 거절(아직 남았어요 · 그대로 두기 · 잘못 알아챘어요)로 끝낸 항목인가.
        답장 감지(reply_confirm)는 그 답장(ref_id)에 대한 답만 본다. 새 답장을 보내면 다시 묻는다."""
        return any(f.key == key and f.reason != "not_mine" and (ref_id is None or f.ref_id == ref_id)
                   for f in self.feedback)

    def not_mine(self, sender: str | None, type_: str) -> bool:
        """같은 발신자 · 같은 유형을 '담당 아님'으로 신고한 적이 있나 → 알림 대신 목록에만(명세 4.2절 6번)."""
        s = (sender or "").lower()
        return bool(s) and (s, type_) in self.not_mine_marks


def _open_tasks(ctx: Context) -> list[tuple[Task, Mail]]:
    """미처리 업무: pending, 또는 나중에(snoozed)인데 그 시각이 지난 것. 받은 메일의 업무만."""
    if not ctx.account_ids:
        return []
    rows = ctx.db.execute(
        select(Task, Mail).join(Mail, Task.mail_id == Mail.id)
        .where(Mail.account_id.in_(ctx.account_ids), Mail.direction == "received",
               (Task.status == "pending") | ((Task.status == "snoozed") & (Task.snoozed_until <= ctx.at)))
        .order_by(Task.id)
    ).all()
    return [(t, m) for t, m in rows]


def _since(task: Task, mail: Mail, formula: datetime) -> datetime:
    """조건이 처음 맞은 시각. 메일이 늦게 왔거나 '나중에'가 풀린 경우에는 그 시각이다(✦ '새 항목' 판정)."""
    marks = [formula, mail.sent_at]
    if task.status == "snoozed" and task.snoozed_until is not None:
        marks.append(task.snoozed_until)
    return max(marks)


def _item(ctx: Context, type_: str, subject_kind: str, subject_id: int, *, title: str, reason: str, created_at: datetime,
          actions: list[dict], card_title: str, task: Task | None = None, mail: Mail | None = None,
          commitment: Commitment | None = None, due_at: datetime | None = None, evidence: str | None = None,
          counterpart: str | None = None, task_ids: list[int] | None = None, sender: str | None = None,
          ref_id: int | None = None, notify: str | None = None) -> dict:
    t = TYPES[type_]
    return {
        "key": make_key(type_, subject_kind, subject_id), "type": type_, "type_label": t.label, "group": t.group,
        "title": title, "reason": reason, "evidence": evidence,
        "task_id": task.id if task else None, "task_ids": task_ids if task_ids is not None else ([task.id] if task else []),
        "task_type": task.type if task else None,  # 캐치봇 리마인더 칸을 업무 유형별로 나눈다(11-14)
        "mail_id": mail.id if mail else None, "commitment_id": commitment.id if commitment else None,
        "due_at": due_at, "counterpart": ctx.counterpart(counterpart), "created_at": created_at,
        "state": "active", "notify_count": 0, "actions": actions,
        # 아래는 응답에 넣지 않는다(엔진 · 제안 카드용)
        "_subject": (subject_kind, subject_id), "_sender": (sender or "").lower() or None, "_ref": ref_id,
        "_card_title": card_title, "_notify": notify if notify is not None else t.notify,
        "_task_status": task.status if task else None,
        # 미뤘다가 그 시각이 지나 다시 열린 업무의 미룬 시각. 카드가 기한 임박 등 다른 유형이어도 이 시각에 '연기 업무' 알림을
        # 따로 보낸다(engine._snooze_alert, 11-15 임동하 결함 보고)
        "_snoozed_until": task.snoozed_until if task is not None and task.status == "snoozed" else None,
    }


# ---------- 업무 항목 ----------

def _task_item(ctx: Context, task: Task, mail: Mail, signals: dict, replies: dict) -> dict | None:
    """업무 하나에 항목 하나. TASK_PRIORITY 순서에서 처음 걸리는 유형."""
    at = ctx.at
    w, what = ctx.who(mail.sender), short(task.text)
    common = {"task": task, "mail": mail, "evidence": task.evidence_text, "counterpart": mail.sender,
              "sender": mail.sender, "due_at": task.due_at}

    def item(type_, reason, created, card=None, **kw):
        merged = {**common, **kw}
        return _item(ctx, type_, "task", task.id, title=task.text, reason=reason, created_at=created,
                     actions=_task_actions(type_, task, mail), card_title=card or f"{w} '{what}' {reason}.", **merged)

    meeting = mail.kind == MEETING_KIND and task.due_at is not None
    for type_ in TASK_PRIORITY:
        if type_ == "resolved" and (sig := signals.get((task.id, "resolved"))):
            reason = RESOLVED_REASON.get(sig.reason or "", "종결되었다는 회신이 있습니다")
            return item("resolved", f"같은 대화의 새 메일에서 {reason}", sig.created_at, evidence=sig.evidence_text)
        if type_ == "reply_confirm" and (reply := replies.get(task.id)):
            key = make_key("reply_confirm", "task", task.id)
            if not ctx.dismissed(key, reply.id):
                return item("reply_confirm", "이 메일에 회신하셨습니다. 완료 처리하시겠습니까?", reply.sent_at, ref_id=reply.id)
        if type_ == "due_changed" and (sig := signals.get((task.id, "due_change"))) and sig.new_due_at != task.due_at:
            old = when(task.due_at, at) if task.due_at else "기한 없음"
            new = when(sig.new_due_at, at) if sig.new_due_at else (sig.new_due_raw or "새 기한")
            return item("due_changed", f"기한이 {old}에서 {new}(으)로 변경되었다는 메일이 수신되었습니다", sig.created_at,
                        evidence=sig.evidence_text)
        if type_ == "overdue" and task.due_at is not None and task.due_at < at:
            days = (at.date() - task.due_at.date()).days
            late = f"기한({when(task.due_at, at)})이 {days}일 경과했습니다" if days >= 1 else f"기한({task.due_at:%H:%M})이 경과했습니다"
            return item("overdue", late, _since(task, mail, task.due_at), card=f"{w} '{what}' {late}.")
        if type_ == "due_soon" and task.due_at is not None and task.due_at - at <= DUE_SOON:
            if meeting and task.due_at - at <= pol.MEETING_BEFORE:
                continue  # 회의 · 행사 초대는 마지막 30분에 '회의 준비'로 넘긴다(BE-D27)
            reason = f"기한은 {when(task.due_at, at)}입니다"
            ask = "회신을 작성하시겠습니까?" if mail.category in DRAFT_CATEGORIES else "메일을 확인하시겠습니까?"
            return item("due_soon", reason, _since(task, mail, task.due_at - DUE_SOON), card=f"{w} '{what}' {reason}. {ask}")
        if type_ == "meeting_prep" and meeting and timedelta(0) < task.due_at - at <= pol.MEETING_BEFORE:
            return item("meeting_prep", f"회의가 {task.due_at:%H:%M}에 시작합니다", _since(task, mail, task.due_at - pol.MEETING_BEFORE))
        if type_ == "snooze_due" and task.status == "snoozed":
            return item("snooze_due", f"연기한 시각({when(task.snoozed_until, at)})이 되었습니다", task.snoozed_until)
        if type_ == "priority_sender":
            contact = ctx.contact(mail.sender)
            if contact is not None and contact.is_superior and at - mail.sent_at >= SUPERIOR_AFTER:
                hours = int((at - mail.sent_at).total_seconds() // 3600)
                ago = f"{hours}시간" if hours < 24 else f"{hours // 24}일"
                return item("priority_sender", f"{w} 메일 수신 후 {ago} 경과했습니다",
                            _since(task, mail, mail.sent_at + SUPERIOR_AFTER), card=f"{w} 메일 수신 후 {ago} 경과했습니다.")
        if type_ == "cc_mention" and task.mentioned_me:
            to = {a.lower() for a in (mail.recipients or [])}
            cc = {a.lower() for a in (mail.cc or [])}
            if not (to & ctx.mine) and (cc & ctx.mine):
                return item("cc_mention", "참조 수신 메일이지만 본문에 요청 사항이 있습니다", mail.sent_at)
        if type_ == "stalled_thread" and at - mail.sent_at >= STALLED_AFTER:
            thread = ctx.thread(mail)
            later = [m for m in thread if (m.sent_at, m.id) > (mail.sent_at, mail.id)]
            talked = any(ctx.from_me(m) for m in thread if (m.sent_at, m.id) < (mail.sent_at, mail.id))
            asks = mail.category in QUESTION_CATEGORIES or (mail.id in signals.get("question", set()))
            if thread and not later and talked and asks:
                days = (at - mail.sent_at).days
                return item("stalled_thread", f"나에게 온 질문에 {days}일째 회신하지 않았습니다",
                            _since(task, mail, mail.sent_at + STALLED_AFTER))
        if type_ == "stale" and task.due_at is None and task.status == "pending" and at - mail.sent_at >= STALE_AFTER:
            days = (at - mail.sent_at).days
            return item("stale", f"기한 없이 수신 후 {days}일째입니다", mail.sent_at + STALE_AFTER)
    return None


def _signals(ctx: Context, task_ids: list[int], mail_ids: list[int]) -> dict:
    """열린 AI 신호: (task_id, kind) → 가장 최근 신호, 'question' → 질문 메일 id 집합."""
    out: dict = {"question": set()}
    if not task_ids and not mail_ids:
        return out
    q = select(ReminderSignal).where(ReminderSignal.status == "open",
                                     ReminderSignal.task_id.in_(task_ids) | ReminderSignal.mail_id.in_(mail_ids))
    for s in ctx.db.scalars(q.order_by(ReminderSignal.id)):
        if s.kind == "question":
            out["question"].add(s.mail_id)
        elif s.task_id in task_ids:
            out[(s.task_id, s.kind)] = s
    return out


def _replies(ctx: Context, open_tasks: list[tuple[Task, Mail]]) -> dict[int, Mail]:
    """답장 감지(D48 (나)): 업무 메일 뒤에 같은 대화로 내가 보낸 메일이 있으면 그 답장(가장 최근)."""
    out = {}
    for task, mail in open_tasks:
        if task.status != "pending":
            continue
        sent = [m for m in ctx.thread(mail) if m.direction == "sent" and (m.sent_at, m.id) > (mail.sent_at, mail.id)]
        if sent:
            out[task.id] = sent[-1]
    return out


# ---------- 업무가 아닌 항목 ----------

def _due_cluster(ctx: Context, open_tasks: list[tuple[Task, Mail]]) -> list[dict]:
    by_day: dict[date, list[tuple[Task, Mail]]] = defaultdict(list)
    for t, m in open_tasks:
        if t.due_at is not None and t.due_at.date() >= ctx.at.date():
            by_day[t.due_at.date()].append((t, m))
    out = []
    for day, rows in sorted(by_day.items()):
        if len(rows) < CLUSTER_MIN:
            continue
        rows.sort(key=lambda r: (r[0].due_at, r[0].id))
        title = f"{day_label(day)} 기한 {len(rows)}건"
        reason = f"하루에 기한이 {len(rows)}건 집중되어 있습니다"
        acts = [_act("open_day", "당일 업무 보기", "T13", primary=True, start=day.isoformat(), end=day.isoformat()),
                _act("snooze_one", "1건 연기", "T05", until=None)]
        out.append(_item(ctx, "due_cluster", "day", int(day.strftime("%Y%m%d")), title=title, reason=reason,
                         created_at=max(m.sent_at for _, m in rows), actions=acts, card_title=f"{title}이 집중되어 있습니다.",
                         due_at=rows[-1][0].due_at, task_ids=[t.id for t, _ in rows]))  # 그날 마지막 기한(그 업무들 뒤에 보이게)
    return out


def awaiting_requests(ctx: Context, days: int | None = None) -> list[Mail]:
    """응답 대기: 내가 보낸 요청 중 기준일(기본 3일 = 72시간) 넘게 답이 없는 메일(기획 detail 5절 · BE-13).
    리마인더(no_reply) · GET /api/awaiting · 대시보드 · 에이전트 T06이 모두 이 함수 하나로 센다.
    - 대화마다 마지막 요청 1건만 본다. 그 뒤에 나 아닌 사람에게 받은 메일이 있으면 답이 온 것이다(내 사본은 답이 아니다).
      → 회신 뒤 다시 요청하면 그 시각부터 다시 센다 · 여러 명 중 한 명이라도 답하면 뺀다.
    - '회신 대기 종료'로 끝낸 메일은 뺀다. 자동회신 구분은 P1(지금은 받은 메일이면 답으로 본다).
    - 보낸 시각 순(오래된 것부터)."""
    limit = ctx.at - timedelta(days=ctx.policy.await_days if days is None else days)
    out = []
    for thread in ctx.threads.values():
        requests = [m for m in thread if m.direction == "sent" and is_request_sent(m)]
        if not requests:
            continue
        last = requests[-1]
        if last.sent_at > limit:
            continue
        if any(m.direction == "received" and not ctx.from_me(m) and m.sent_at > last.sent_at for m in thread):
            continue
        if ctx.dismissed(make_key("no_reply", "sent_mail", last.id)):
            continue
        out.append(last)
    return sorted(out, key=lambda m: (m.sent_at, m.id))


def recipients_label(ctx: Context, mail: Mail) -> str:
    """응답 대기 줄의 받는 사람 표시: '박지호 매니저', 여럿이면 '박지호 매니저 외 1명'. 연락처가 없으면 주소 앞부분."""
    to = list(mail.recipients or [])
    if not to:
        return "(받는 사람 없음)"
    c = ctx.contact(to[0])
    name = (c.name if c and c.name else None) or to[0].split("@")[0]
    first = f"{name} {c.position}" if c and c.position else name
    return f"{first} 외 {len(to) - 1}명" if len(to) > 1 else first


def _no_reply(ctx: Context) -> list[dict]:
    """응답 대기 메일 한 통에 리마인더 항목 하나(awaiting_requests)."""
    days = ctx.policy.await_days
    out = []
    for last in awaiting_requests(ctx):
        n = (ctx.at - last.sent_at).days
        to = (last.recipients or [None])[0]
        subject = last.subject or "(제목 없음)"
        acts = [_act("nudge", "회신 요청 작성", "T07", primary=True, mail_id=last.id, tone="nudge"),
                _act("open_mail", "메일 열기", "open_mail", mail_id=last.id),
                _act("stop_waiting", "회신 대기 종료", "dismiss", reason="stop_waiting")]
        out.append(_item(ctx, "no_reply", "sent_mail", last.id, title=subject, reason=f"보낸 지 {n}일째 회신이 없습니다",
                         created_at=last.sent_at + timedelta(days=days), actions=acts, mail=last,
                         card_title=f"보낸 요청 '{short(subject, 40)}'에 {n}일째 회신이 없습니다.", counterpart=to, sender=to))
    return out


def _commitments(ctx: Context) -> list[dict]:
    if not ctx.account_ids:
        return []
    rows = ctx.db.execute(select(Commitment, Mail).join(Mail, Commitment.mail_id == Mail.id)
                          .where(Mail.account_id.in_(ctx.account_ids), Commitment.status == "open")
                          .order_by(Commitment.id)).all()
    at, out = ctx.at, []
    for c, mail in rows:
        if c.who == "them":
            if c.due_at is None or c.due_at >= at:
                continue  # 기한이 지나야 '상대 약속 기한 경과'이다. 기한 없는 상대 약속은 띄우지 않는다
            arrived = any(m.direction == "received" and m.sender.lower() == mail.sender.lower()
                          and (m.sent_at, m.id) > (mail.sent_at, mail.id) for m in ctx.thread(mail))
            if arrived:
                continue
            key = make_key("their_promise", "commitment", c.id)
            if ctx.dismissed(key):
                continue
            w = ctx.who(mail.sender)
            reason = f"{w}이 {when(c.due_at, at)}까지 회신하기로 했으나 아직 수신되지 않았습니다"
            acts = [_act("nudge", "회신 요청 작성", "T07", primary=True, mail_id=mail.id, tone="nudge"),
                    _act("open_mail", "메일 열기", "open_mail", mail_id=mail.id),
                    _act("apply", "수신 확인", "apply")]
            out.append(_item(ctx, "their_promise", "commitment", c.id, title=c.text, reason=reason, created_at=c.due_at,
                             actions=acts, mail=mail, commitment=c, due_at=c.due_at, evidence=c.evidence_text,
                             counterpart=mail.sender, sender=mail.sender, card_title=f"'{short(c.text)}' {reason}."))
        else:
            if c.due_at is not None:
                start = c.due_at - DUE_SOON
                reason = (f"{when(c.due_at, at)}까지 이행하기로 했습니다" if c.due_at >= at
                          else f"이행 기한({when(c.due_at, at)})이 경과했습니다")
                notify = None
            else:
                start = mail.sent_at + MY_PROMISE_NO_DUE
                reason = f"{(at - mail.sent_at).days}일 전에 이행하기로 했습니다"
                notify = "morning"  # 기한 없는 내 약속은 아침에 몰아서(명세 4.1절)
            if at < start:
                continue
            key = make_key("my_promise", "commitment", c.id)
            if ctx.dismissed(key):
                continue
            to = (mail.recipients or [None])[0]
            acts = [_act("open_mail", "메일 열기", "open_mail", primary=True, mail_id=mail.id),
                    _act("snooze", "연기", "dismiss", reason="hide"),
                    _act("apply", "이행 완료", "apply")]
            out.append(_item(ctx, "my_promise", "commitment", c.id, title=c.text, reason=reason,
                             created_at=max(start, mail.sent_at), actions=acts, mail=mail, commitment=c, due_at=c.due_at,
                             evidence=c.evidence_text, counterpart=to, card_title=f"'{short(c.text)}' {reason}.",
                             notify=notify))
    return out


# ---------- 전체 ----------

def sort_key(item: dict) -> tuple:
    """기한이 이른 순, 기한이 없으면 생긴 순(명세 5절). 조용히 둔 항목은 맨 아래."""
    quiet = item["state"] == "quiet"
    if item["due_at"] is not None:
        return (quiet, 0, item["due_at"], item["created_at"], item["key"])
    return (quiet, 1, item["created_at"], item["created_at"], item["key"])


def compute(db: Session, user_id: int, at: datetime | None = None, *, include_hidden: bool = False) -> list[dict]:
    """지금 띄울 리마인더 항목 전체(숨긴 것 제외). 정렬은 engine.items()가 알림 횟수를 붙인 뒤 한다."""
    ctx = Context(db, user_id, at or now())
    open_tasks = _open_tasks(ctx)
    signals = _signals(ctx, [t.id for t, _ in open_tasks], [m.id for _, m in open_tasks])
    replies = _replies(ctx, open_tasks)
    items = []
    for task, mail in open_tasks:
        if it := _task_item(ctx, task, mail, signals, replies):
            items.append(it)
    items += _due_cluster(ctx, open_tasks)
    items += _no_reply(ctx)
    items += _commitments(ctx)
    if not include_hidden:
        items = [i for i in items if i["key"] not in ctx.hides]
    for i in items:
        i["_not_mine"] = ctx.not_mine(i["_sender"], i["type"])
        i["_muted"] = i["type"] in ctx.policy.mute
    return items


def ensure_settings(db: Session, user_id: int) -> UserSettings:
    """설정 행을 돌려준다. 없으면 기본값으로 만든다(유형 알림 끄기 · 부재 중을 저장하려고). 커밋은 부르는 쪽이 한다."""
    s = db.get(UserSettings, user_id)
    if s is None:
        s = UserSettings(user_id=user_id)
        db.add(s)
        db.flush()
    return s
