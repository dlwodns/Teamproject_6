"""에이전트 실행기 — ai가 해석한 명령(plan)을 검증 → 대상 해석 → 확인 판정 → 실행 · 미리보기 (BE-11, docs/30_backend/detail.md 4절).

plan은 ai `/agent/plan` 응답(`app/schemas/ai.PlanResult`)을 dict로 바꾼 것이다: {action, action_name, target, params, source, reason}.
상태 변경 · 기록 · 되돌리기는 `app/services/task_status.py`를 그대로 쓴다(REST 버튼과 같은 길). 커밋은 부르는 쪽이 한다.
"""
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import privacy
from app.agent import ask
from app.ai_client.client import AIError
from app.mail.body import fetch_body
from app.agent.policy import needs_confirm
from app.agent.resolve import match_contacts, resolve, resolve_ids
from app.agent.tools.registry import REGISTRY, ActionDef
from app.core.clock import as_kst, now, to_kst_naive
from app.models import Account, ActionLog, Contact, ContactFact, Mail, Task
from app.models.mail import visible_mail
from app.reminders import actions as reminder_actions
from app.reminders import briefings
from app.reminders import policy as pol
from app.schemas.agent import (AgentMail, AgentPerson, AgentPersonFact, AgentPersonMail, AgentResult, AgentSend, AgentSummary,
                               AgentSummaryItem, AgentTarget)
from app.services import calendar, learn, memory, nudge, task_status
from app.services.awaiting import MAX_DAYS, MIN_DAYS, list_awaiting
from app.services.task_status import UNDO, StatusError

SOURCE = {"rule": "agent_rule", "model": "agent_model"}
STATUS = {"T03": "done", "T05": "snoozed", "T10": "excluded"}  # 상태 변경 행동 → 바꿀 상태
# 11-17 결정(문규남): 초안은 캐치봇에서 만들지 않는다. 메일 화면 답장 칸에서 쓰고 [다듬기](/polish)로 다듬는다.
# 행동은 레지스트리 · ai 목록에 남겨 둔다 — 모델이 '답장 써줘'를 알아듣고 어디로 가면 되는지 안내하기 위해서다
NOT_IN_BOT = {"T07": "회신은 메일 화면의 답장 칸에서 작성하고 [다듬기]로 업무 문장으로 다듬을 수 있습니다",
              "T12": "새 메일은 메일 화면에서 작성하고 [다듬기]로 업무 문장으로 다듬을 수 있습니다"}
ASK = {"until": "다시 알림 받을 시각을 알려 주십시오", "due_at": "바꿀 기한 날짜를 알려 주십시오", "start": "등록할 날짜와 시각을 함께 알려 주십시오",
       "min_days": "며칠 넘게 답이 없는 메일을 볼지 1~30일로 알려 주십시오"}


def _verb(status: str, until: datetime | None, done: bool) -> str:
    if status == "snoozed":
        return f"{until:%m/%d %H:%M}까지 " + ("연기했습니다" if done else "연기하시겠습니까?")
    if status == "excluded":
        return "목록에서 " + ("제외했습니다" if done else "제외하시겠습니까?")
    return "완료로 " + ("변경했습니다" if done else "변경하시겠습니까?")


def _targets(db: Session, ids: list[int]) -> list[AgentTarget]:
    rows = {t.id: t for t in db.scalars(select(Task).where(Task.id.in_(ids)))}
    return [AgentTarget(id=i, mail_id=rows[i].mail_id, text=rows[i].text, status=rows[i].status,
                        snoozed_until=as_kst(rows[i].snoozed_until)) for i in ids if i in rows]


def _until(v: Any) -> datetime | None:
    """T05 params.until → 저장 형식(시간대 없는 KST, D47). 시간대가 붙어 와도 KST로 바꿔 뗀다. 못 읽으면 ValueError."""
    if v is None:
        return None
    return to_kst_naive(v if isinstance(v, datetime) else datetime.fromisoformat(str(v)))


def run(db: Session, user_id: int, plan: dict[str, Any], scope_task_ids: list[int] | None = None,
        text: str = "", ai: Any = None) -> AgentResult:
    """scope_task_ids: 화면에서 고른 업무(캐치봇 '고른 리마인더'). 말에 다른 사람 · 분류 · 낱말을 대지 않으면 이 업무가 대상이다.
    조회인데 기간을 말했으면 고른 업무 대신 그 기간으로 찾는다.
    text: 사용자가 한 말 원문(가리기 전). T18 메일 내용 질문이 질문 낱말 · 종류(어디 · 언제)를 읽는다.
    ai: ai 클라이언트. T20 메일 요약만 쓴다."""
    action_id, reason = plan.get("action"), plan.get("reason")
    source = SOURCE.get(plan.get("source") or "", "agent_rule")
    base = {"action": action_id, "action_name": plan.get("action_name"), "source": source}

    if action_id is None:
        if reason == "ambiguous":
            return AgentResult(kind="ask", title="요청 내용을 조금 더 구체적으로 말씀해 주십시오", **base)
        return AgentResult(kind="unsupported", title="지원하지 않는 요청입니다", **base)
    a: ActionDef | None = REGISTRY.get(action_id)
    params: dict[str, Any] = plan.get("params") or {}
    if a is None or not set(params) <= set(a.params):  # 레지스트리에 없는 행동 · 계약에 없는 params 키(D47)
        return AgentResult(kind="unsupported", title="지원하지 않는 요청입니다", **base)
    base["action_name"] = a.name
    if a.id in NOT_IN_BOT:
        return AgentResult(kind="unsupported", title=NOT_IN_BOT[a.id], **base)
    if not a.ready:
        return AgentResult(kind="unsupported", title=f"'{a.name}'은(는) 준비 중인 기능입니다", **base)
    if missing := [k for k in a.required if params.get(k) is None]:  # 못 읽은 값은 키를 두고 null로 온다(#6 리뷰)
        return AgentResult(kind="ask", title=ASK.get(missing[0], "필요한 값을 알려 주십시오"), **base)
    try:
        until = _until(params.get("until"))
        if a.id == "T16":  # 새 기한도 같은 형식
            params = {**params, "due_at": _until(params.get("due_at"))}
        if a.id == "T15":  # 일정 시작 · 끝도 같은 형식. 못 읽으면 되묻는다
            params = {**params, "start": _until(params.get("start")), "end": _until(params.get("end"))}
    except (TypeError, ValueError):  # '금요일'처럼 시각으로 못 읽는 값 → 500 대신 되묻기(#28 리뷰)
        return AgentResult(kind="ask", title=ASK["start" if a.id == "T15" else "due_at" if a.id == "T16" else "until"], **base)
    if until is not None and until <= now():  # 지난 시각으로는 미루지 않는다(#31 리뷰)
        return AgentResult(kind="ask", title=ASK["until"], notes=[f"{until:%m/%d %H:%M}은 이미 지난 시각입니다"], **base)

    if a.id == "T01":
        return _summary(db, user_id, params, base)
    if a.id == "T06":
        return _awaiting(db, user_id, params.get("min_days"), base)
    if a.id == "T14":
        return _nudge(db, user_id, plan.get("target") or {}, params, source, base)
    if a.id == "T04":
        return _undo(db, user_id, params.get("action_id"), source, base)
    if a.id == "T15":
        return _calendar(db, user_id, plan.get("target") or {}, params, source, base)
    if a.id == "T17":
        return _person(db, user_id, plan.get("target") or {}, base)
    if a.id == "T18":
        return _ask_mail(db, user_id, plan.get("target") or {}, text, base)
    if a.id == "T19":
        return _find_mails(db, user_id, plan.get("target") or {}, bool(params.get("sent")), base)
    if a.id == "T13":
        return _schedule(db, user_id, plan.get("target") or {}, base)
    if a.id == "T08":
        return _evidence(db, user_id, plan.get("target") or {}, scope_task_ids, base)
    if a.id == "T20":
        return _summarize_mail(db, user_id, plan.get("target") or {}, text, ai, base)

    target = plan.get("target") or {}
    try:
        # T16은 1건씩 바꾸므로 되묻기에서 고른 업무(task_ids)가 오면 말의 조건과 관계없이 그 업무다(11-19)
        # 조회(T02 '이번 주 마감인 거 보여줘')는 기간을 살린다. 기간을 버리는 건 상태 변경('이거 내일로 미뤄'의 '내일')만(#243 리뷰)
        if scope_task_ids and (a.id == "T16" or (not any(target.get(k) for k in ("sender", "category", "keyword"))
                                               and not (a.kind == "query" and target.get("date_range")))):
            res = resolve_ids(db, user_id, scope_task_ids)
        else:
            res = resolve(db, user_id, target, by_due=(a.id == "T02"), allow_all=(a.kind == "query"))
    except (TypeError, ValueError, KeyError):  # 메일 id가 숫자가 아님 · 기간 끝이 없음 등 → 500 대신 되묻기(#28 리뷰)
        return AgentResult(kind="ask", title="대상을 확인하지 못했습니다. 다시 말씀해 주십시오", **base)
    if res.no_filter:
        return AgentResult(kind="ask", title="어떤 업무인지 알려 주세요(보낸 사람 · 분류 · 기간 · 메일 선택)", **base)
    which = {"done": "끝낸", "snoozed": "미룬"}.get(target.get("status") or "", "미처리")
    if not res.task_ids:
        return AgentResult(kind="empty", title=f"해당하는 {which} 업무가 없습니다", notes=res.notes, **base)
    if a.kind == "query":
        targets = _targets(db, res.task_ids)
        later = sum(t.status == "snoozed" for t in targets) if which == "미처리" else 0
        return AgentResult(kind="query", title=f"{which} 업무 {len(targets)}건입니다" + (f"(연기 {later}건 포함)" if later else ""),
                           targets=targets, notes=res.notes, **base)
    if a.id == "T16":
        return _change_due(db, user_id, res.task_ids, params["due_at"], source, res.notes, base)

    status = STATUS[a.id]
    n = len(res.task_ids)
    if needs_confirm(a, res.task_ids, res.ambiguous):
        p, _ = task_status.preview(db, res.task_ids, status, until, action=a.id, source=source)
        return AgentResult(kind="confirm", title=f"업무 {n}건을 {_verb(status, until, False)}",
                           targets=_targets(db, res.task_ids), notes=res.notes, preview_id=p.preview_id,
                           expires_at=as_kst(p.expires_at), **base)
    log, _ = task_status.change_status(db, res.task_ids, status, until, action=a.id, source=source)
    return AgentResult(kind="done", title=f"{n}건을 {_verb(status, until, True)}", targets=_targets(db, res.task_ids),
                       notes=res.notes, action_id=log.id if log else None, **base)


def _undo(db: Session, user_id: int, target_id: Any, source: str, base: dict) -> AgentResult:
    """T04: 지정한 행동, 없으면 방금 한 행동을 되돌린다. 1건이므로 바로 실행한다(detail 3.2절 [제안]).
    방금 한 행동은 그 사용자의 가장 최근 기록 1건이다. 그게 되돌리기면 그 전 행동을 조용히 되돌리지 않고 되묻는다
    (#31 리뷰: "취소해"를 연달아 말해도 사용자가 모르는 사이 상태가 바뀌지 않게, 시연 ③)."""
    if target_id is not None:
        try:
            target_id = int(target_id)
        except (TypeError, ValueError):
            return AgentResult(kind="ask", title="취소할 작업을 알려 주십시오", **base)
        owned = db.get(ActionLog, target_id)
        if owned is None or owned.user_id != user_id:  # 다른 사용자의 행동은 되돌리지 않는다
            return AgentResult(kind="empty", title="취소할 작업이 없습니다", **base)
    else:
        latest = db.scalar(select(ActionLog).where(ActionLog.user_id == user_id).order_by(ActionLog.id.desc()).limit(1))
        if latest is None:
            return AgentResult(kind="empty", title="취소할 작업이 없습니다", **base)
        if latest.action == UNDO:
            return AgentResult(kind="ask", title="방금 되돌린 걸 다시 할까요, 그 전 것도 되돌릴까요?",
                               notes=[f"방금 행동 #{(latest.params_json or {}).get('action_id')}을(를) 취소했습니다"], **base)
        target_id = latest.id
    try:
        log, back, tasks = task_status.undo(db, target_id, source=source)
    except StatusError as e:
        return AgentResult(kind="empty", title=f"되돌릴 수 없어요: {e}", **base)
    if calendar.is_calendar(log):
        return AgentResult(kind="done", title="캘린더 일정 등록을 취소했습니다", action_id=back.id,
                           notes=[f"행동 #{log.id}({calendar.describe(log)})를 되돌림"], **base)
    return AgentResult(kind="done", title=f"{len(tasks)}건의 처리를 취소했습니다", targets=_targets(db, [t.id for t in tasks]),
                       action_id=back.id, notes=[f"행동 #{log.id}({log.action})를 되돌림"], **base)


def _calendar(db: Session, user_id: int, target: dict, params: dict[str, Any], source: str, base: dict) -> AgentResult:
    """T15 일정 등록(D50 결정 6). 1건이고 되돌릴 수 있어 확인 없이 바로 넣고 결과 카드에 되돌리기를 준다.
    시각: 말로 준 start → 없으면 고른 메일(한 통)의 일정참석 업무 시각(메일에 시각이 적힌 것만) → 그것도 없으면 되묻는다.
    지난 시각 · 끝이 시작보다 앞이면 넣지 않고 되묻는다."""
    start, end, title = params.get("start"), params.get("end"), params.get("title")
    mail_ids = [int(i) for i in target.get("mail_ids") or [] if str(i).isdigit()]
    if len(mail_ids) > 1:
        return AgentResult(kind="ask", title="일정은 메일 1건씩 등록할 수 있습니다. 1건만 선택해 주십시오", **base)
    mail_id = mail_ids[0] if mail_ids else None
    task_id, notes = None, []
    if start is None and mail_id is None and target.get("keyword"):  # 11-18 '킥오프 미팅 캘린더에 넣어줘' → 낱말로 메일을 찾는다
        found = ask.find(db, user_id, "", target["keyword"], [])
        if isinstance(found, ask.Answer):
            mail_id = found.mail.id
            notes.append(f"'{found.mail.subject}' 메일을 찾았습니다")
    if start is None and mail_id is not None:
        meeting = calendar.mail_meeting(db, user_id, mail_id)
        if meeting is not None:
            start, end, task_id = meeting.due_at, end or meeting.end_at, meeting.id
            notes.append("선택한 메일의 회의 시각으로 등록했습니다")
    if start is None:
        return AgentResult(kind="ask", title=ASK["start"], **base)
    if start <= now():
        return AgentResult(kind="ask", title=ASK["start"], notes=[f"{start:%m/%d %H:%M}은 이미 지난 시각입니다"], **base)
    try:
        ev, log = calendar.add(db, user_id, title=title, start=start, end=end, mail_id=mail_id, task_id=task_id,
                               action="T15", source=source)
    except StatusError as e:
        kind = "ask" if e.kind == "invalid" else "empty"
        return AgentResult(kind=kind, title=str(e), **base)
    return AgentResult(kind="done", title=f"{ev.start_at:%m/%d %H:%M} '{ev.title}'을(를) 캘린더에 등록했습니다",
                       notes=notes + [f"{ev.start_at:%H:%M}~{ev.end_at:%H:%M}"], action_id=log.id, **base)


PERSON_MAILS = 10  # 카드에 싣는 최근 메일 수. 전체 수는 mail_total
PERSON_TASKS = 20


def _person(db: Session, user_id: int, target: dict, base: dict) -> AgentResult:
    """T17 사람 조회(11-17 결정). 사람은 말한 이름(target.sender) → 없으면 고른 메일 한 통의 보낸 사람.
    맡은 일 · 소속은 '메일 내용 분석 허용'이 켜져 있을 때만 싣는다(켜기 = 저장하고 그 정보로 답하기에 동의).
    메일 · 업무는 끝난 것도 싣는다 — '그 사람이 무엇을 보냈었나'를 묻는 것이라 미처리만 보이면 답이 아니다."""
    people: list[Contact] = []
    if sender := target.get("sender"):
        people = match_contacts(db, user_id, str(sender))
        if not people:
            return AgentResult(kind="empty", title=f"'{sender}'에 해당하는 연락처가 없습니다", **base)
    else:
        ids = [int(i) for i in target.get("mail_ids") or [] if str(i).isdigit()]
        senders = set(db.scalars(select(Mail.sender).join(Account, Mail.account_id == Account.id)
                                 .where(Account.user_id == user_id, Mail.id.in_(ids), Mail.direction == "received")))
        if len(senders) != 1:
            return AgentResult(kind="ask", title="어느 분을 찾으시는지 이름이나 메일 1건으로 알려 주십시오", **base)
        people = list(db.scalars(select(Contact).where(Contact.user_id == user_id,
                                                       func.lower(Contact.email) == next(iter(senders)).lower())))
        if not people:
            return AgentResult(kind="empty", title="선택한 메일의 보낸 사람이 연락처에 없습니다", **base)
    if len(people) > 1:
        return AgentResult(kind="ask", title="여러 분이 해당됩니다. 이름을 더 정확히 말씀해 주십시오",
                           notes=[" · ".join(f"{c.name or c.email} {c.position or ''}".strip() for c in people)], **base)
    c = people[0]
    learn_on = learn.enabled(db, user_id)
    facts = [AgentPersonFact(kind=f.kind, label=memory.FACT_LABEL[f.kind], value=f.value, evidence=f.evidence, mail_id=f.mail_id)
             for f in db.scalars(select(ContactFact).where(ContactFact.user_id == user_id, ContactFact.contact_id == c.id)
                                 .order_by(ContactFact.kind))] if learn_on else []
    mail_q = (select(Mail).join(Account, Mail.account_id == Account.id)
              .where(Account.user_id == user_id, Mail.direction == "received", visible_mail(),
                     func.lower(Mail.sender) == c.email.lower()))
    total = db.scalar(select(func.count()).select_from(mail_q.subquery())) or 0
    mails = db.scalars(mail_q.order_by(Mail.sent_at.desc(), Mail.id.desc()).limit(PERSON_MAILS)).all()
    task_ids = list(db.scalars(select(Task.id).join(Mail, Task.mail_id == Mail.id).join(Account, Mail.account_id == Account.id)
                               .where(Account.user_id == user_id, Mail.direction == "received", visible_mail(),
                                      func.lower(Mail.sender) == c.email.lower())
                               .order_by(Mail.sent_at.desc(), Task.id).limit(PERSON_TASKS)))
    person = AgentPerson(contact_id=c.id, name=c.name, email=c.email, position=c.position, is_superior=c.is_superior,
                         is_favorite=c.is_favorite, facts=facts, learn_off=not learn_on, mail_total=total,
                         mails=[AgentPersonMail(mail_id=m.id, subject=m.subject or "(제목 없음)", received_at=as_kst(m.sent_at))
                                for m in mails])
    notes = [] if learn_on else ["메일 내용 분석이 꺼져 있어 맡은 일 · 소속은 답하지 않습니다(설정에서 켤 수 있습니다)"]
    who = f"{c.name or c.email} {c.position or ''}".strip()
    return AgentResult(kind="person", title=f"{who}님이 보낸 메일 {total}건입니다", person=person,
                       targets=_targets(db, task_ids), notes=notes, **base)


def _ask_mail(db: Session, user_id: int, target: dict, text: str, base: dict) -> AgentResult:
    """T18 메일 내용 질문(11-18). 답은 메일 본문 문장 그대로(제목 카드), 그 메일의 업무를 함께 싣는다(끝난 것 포함)."""
    mail_ids = [int(i) for i in target.get("mail_ids") or [] if str(i).isdigit()]
    found = ask.find(db, user_id, text, target.get("keyword"), mail_ids)
    if found == "no_terms":
        return AgentResult(kind="ask", title="어떤 메일 내용을 찾으시는지 알려 주십시오(예: 누리물류 킥오프 미팅 장소)", **base)
    if found is None:
        return AgentResult(kind="empty", title="물어보신 내용이 담긴 메일을 찾지 못했습니다", **base)
    m = found.mail
    who = db.scalar(select(Contact.name).where(Contact.user_id == user_id, func.lower(Contact.email) == m.sender.lower()))
    notes = [f"'{m.subject or '(제목 없음)'}' 메일({who or m.sender}, {as_kst(m.sent_at):%m/%d})에서 찾았습니다"]
    if found.line is None:
        notes.append("본문을 읽지 못해(또는 '메일 본문 읽기'가 꺼져 있어) 제목으로만 찾았습니다")
    title = found.line or f"'{m.subject}' 메일입니다"
    if found.quoted:
        notes.append("전달된 원문에서 찾았습니다")
    if found.guess:  # 본문은 읽었지만 질문 낱말이 든 문장이 없다 → 가장 비슷한 문장을 되묻듯 보여 준다
        title = f"이 문장을 말씀하시는 걸까요? “{found.line}”"
        notes.append("물어보신 낱말이 그대로 든 문장이 없어 가장 비슷한 문장을 골랐습니다")
    return AgentResult(kind="query", title=title, targets=_targets(db, found.task_ids),
                       mails=[_mail_view(db, user_id, m)], notes=notes, **base)


def _change_due(db: Session, user_id: int, task_ids: list[int], due_at: datetime, source: str, notes: list[str],
                base: dict) -> AgentResult:
    """T16 기한 변경(11-18 말로도). 업무 1건만 바로 바꾸고 되돌리기를 준다. 여러 건이면 고르게 되묻는다."""
    if len(task_ids) > 1:
        return AgentResult(kind="ask", title=f"업무 {len(task_ids)}건이 해당합니다. 기한은 1건씩 바꿀 수 있으니 하나를 골라 주십시오",
                           targets=_targets(db, task_ids), notes=notes, **base)
    if due_at <= now():
        return AgentResult(kind="ask", title=ASK["due_at"], notes=[f"{due_at:%m/%d %H:%M}은 이미 지난 시각입니다"], **base)
    log = reminder_actions.change_due(db, user_id, task_ids[0], due_at, via="agent", source=source)
    return AgentResult(kind="done", title=f"기한을 {due_at:%m/%d %H:%M}으로 바꿨습니다", targets=_targets(db, task_ids),
                       notes=notes, action_id=log.id, **base)


WEEKDAY = "월화수목금토일"


def _schedule(db: Session, user_id: int, target: dict, base: dict) -> AgentResult:
    """T13 기간의 일정 · 회의 · 마감(캘린더 화면과 같은 항목, services/calendar.items). 기간이 없으면 오늘부터 7일."""
    rng = target.get("date_range") or {}
    try:
        start = date.fromisoformat(str(rng["start"])) if rng else now().date()
        end = date.fromisoformat(str(rng["end"])) if rng else start + timedelta(days=6)
        rows = calendar.items(db, user_id, start, end)
    except (KeyError, ValueError, StatusError):
        return AgentResult(kind="ask", title="볼 기간을 알려 주십시오(예: 이번 주 · 다음 주 월요일)", **base)
    span = f"{start:%m/%d}~{end:%m/%d}" if end != start else f"{start:%m/%d}"
    if not rows:
        return AgentResult(kind="empty", title=f"{span} 일정 · 기한이 없습니다", **base)
    label = {"event": "일정", "meeting": "회의", "due": "마감", "snoozed": "다시 알림"}
    lines = [f"{r.start:%m/%d}({WEEKDAY[r.start.weekday()]})" + (f" {r.start:%H:%M}" if r.time_stated else "")
             + f" [{label[r.kind]}] {r.title}" for r in rows]
    task_ids = list(dict.fromkeys(r.task_id for r in rows if r.task_id))
    return AgentResult(kind="query", title=f"{span} 일정 · 기한 {len(rows)}건입니다", lines=lines,
                       targets=_targets(db, task_ids), **base)


def _mail_view(db: Session, user_id: int, m: Mail) -> AgentMail:
    return AgentMail(mail_id=m.id, subject=m.subject or "(제목 없음)", who=ask.who(db, user_id, m), direction=m.direction,
                     at=as_kst(m.sent_at))


def _find_mails(db: Session, user_id: int, target: dict, sent: bool, base: dict) -> AgentResult:
    """T19 메일 찾기(11-18). 받은 · 보낸 메일 목록과 건수. 업무가 없는 메일 · 끝난 업무의 메일도 찾는다."""
    mails, total, notes = ask.find_mails(db, user_id, target, sent)
    kind = "보낸" if sent else "받은"
    if not total:
        return AgentResult(kind="empty", title=f"조건에 맞는 {kind} 메일이 없습니다", notes=notes, **base)
    more = f"(최근 {len(mails)}통만 보입니다)" if total > len(mails) else ""
    return AgentResult(kind="query", title=f"{kind} 메일 {total}통입니다{more}",
                       mails=[_mail_view(db, user_id, m) for m in mails], notes=notes, **base)


def _owned_tasks(db: Session, user_id: int, *, mail_ids: list[int] | None = None,
                 task_ids: list[int] | None = None) -> list[Task]:
    q = (select(Task).join(Mail, Task.mail_id == Mail.id).join(Account, Mail.account_id == Account.id)
         .where(Account.user_id == user_id))
    q = q.where(Task.mail_id.in_(mail_ids)) if mail_ids is not None else q.where(Task.id.in_(task_ids or []))
    return list(db.scalars(q.order_by(Task.id)))


def _evidence(db: Session, user_id: int, target: dict, scope_task_ids: list[int] | None, base: dict) -> AgentResult:
    """T08 근거 설명(11-18). 고른 리마인더 · 고른 메일 · 낱말로 찾은 메일의 업무마다 업무로 잡은 문장을 보여 준다."""
    ids = [int(i) for i in target.get("mail_ids") or [] if str(i).isdigit()]
    if scope_task_ids:
        tasks = _owned_tasks(db, user_id, task_ids=scope_task_ids)
    elif ids:
        tasks = _owned_tasks(db, user_id, mail_ids=ids)
    elif target.get("keyword"):
        found = ask.find(db, user_id, "", target.get("keyword"), [])
        tasks = _owned_tasks(db, user_id, task_ids=found.task_ids) if isinstance(found, ask.Answer) else []
    else:
        return AgentResult(kind="ask", title="근거를 볼 메일을 골라 주십시오", **base)
    if not tasks:
        return AgentResult(kind="empty", title="이 메일에서 잡은 업무가 없습니다", **base)
    lines = []
    for t in tasks:
        ev = ask.evidence(db, user_id, t)
        lines.append(f"{t.text} ← \u201c{ev}\u201d" if ev else f"{t.text} ← (근거 문장을 찾지 못했습니다)")
    return AgentResult(kind="query", title=f"업무 {len(tasks)}건을 아래 문장으로 잡았습니다", lines=lines,
                       targets=_targets(db, [t.id for t in tasks]), **base)


def _summarize_mail(db: Session, user_id: int, target: dict, text: str, ai: Any, base: dict) -> AgentResult:
    """T20 메일 요약(11-18). 고른 메일 1통, 없으면 낱말로 찾은 메일 1통. 본문은 가려서 ai /summarize(mode=mail)에 보낸다."""
    ids = [int(i) for i in target.get("mail_ids") or [] if str(i).isdigit()]
    if len(ids) > 1:
        return AgentResult(kind="ask", title="요약은 메일 1통씩 할 수 있습니다. 1통만 골라 주십시오", **base)
    if ids:
        m = db.scalar(select(Mail).join(Account, Mail.account_id == Account.id)
                      .where(Account.user_id == user_id, Mail.id == ids[0]))
    else:
        found = ask.find(db, user_id, text, target.get("keyword"), [])
        if found == "no_terms":
            return AgentResult(kind="ask", title="요약할 메일을 고르거나 제목 낱말을 말씀해 주십시오", **base)
        m = found.mail if isinstance(found, ask.Answer) else None
    if m is None:
        return AgentResult(kind="empty", title="요약할 메일을 찾지 못했습니다", **base)
    view = [_mail_view(db, user_id, m)]
    body = fetch_body(db, m) if learn.reads_body(db, user_id) else None
    if not body or ai is None:
        return AgentResult(kind="unsupported", title="메일 본문을 가져오지 못해 요약할 수 없습니다", mails=view, **base)
    masker = privacy.masker_for(db, user_id)
    try:
        r = ai.summarize({"mode": "mail", "now": now(),
                          "mail": {"subject": masker.mask_text(m.subject or ""), "body": masker.mask_text(body)}})
    except AIError:
        return AgentResult(kind="unsupported", title="지금은 메일을 요약할 수 없습니다. 잠시 뒤 다시 말씀해 주십시오", mails=view, **base)
    s = r.mail_summary
    if s is None:
        return AgentResult(kind="unsupported", title="이 메일은 요약하지 못했습니다. 원문을 열어 보십시오", mails=view, **base)
    # '메일 속 요청': 보낸 사람 · '나'를 ai에 보내지 않아 나에게 온 요청인지 모른다(CC · 회의록 속 다른 팀 요청, DE-D32, #244 리뷰)
    lines = [f"메일 속 요청: {masker.unmask_text(x)}" for x in s.asks] + ([f"기한: {masker.unmask_text(s.due_text)}"] if s.due_text else [])
    return AgentResult(kind="query", title=masker.unmask_text(s.gist), lines=lines, mails=view,
                       targets=_targets(db, [t.id for t in _owned_tasks(db, user_id, mail_ids=[m.id])]), **base)


def _nudge(db: Session, user_id: int, target: dict[str, Any], params: dict[str, Any], source: str,
           base: dict) -> AgentResult:
    """T14 재촉 메일: 응답 대기 메일에 재촉 템플릿 미리보기 → 확인 카드(발송은 늘 확인, D37). 일반 템플릿 전송은 P2."""
    if (params.get("template_kind") or "nudge") != "nudge":
        return AgentResult(kind="unsupported", title="재촉 메일만 보낼 수 있습니다(일반 템플릿 전송은 준비 중)", **base)
    try:
        ids = [int(i) for i in target.get("mail_ids") or []]
    except (TypeError, ValueError):
        return AgentResult(kind="ask", title="재촉할 메일을 골라 주십시오", **base)
    all_waiting = bool(target.get("awaiting_reply")) and not ids
    if not ids and not all_waiting:
        return AgentResult(kind="ask", title="재촉할 메일을 골라 주십시오(예: '답장 안 온 메일' 목록에서)", **base)
    try:
        p, sends, notes = nudge.preview(db, user_id, mail_ids=ids, all_waiting=all_waiting, source=source)
    except StatusError as e:  # Outlook 계정: 아직 보낼 수 없음
        return AgentResult(kind="unsupported", title=str(e), **base)
    if p is None:
        return AgentResult(kind="empty", title="재촉할 응답 대기 메일이 없습니다", notes=notes, **base)
    return AgentResult(kind="confirm", title=f"재촉 메일 {len(sends)}통을 보내시겠습니까?", notes=notes,
                       preview_id=p.preview_id, expires_at=as_kst(p.expires_at),
                       sends=[AgentSend(mail_id=s["mail_id"], to=s["to"], subject=s["subject"], body=s["body"]) for s in sends],
                       **base)


def _awaiting(db: Session, user_id: int, min_days: Any, base: dict) -> AgentResult:
    """T06 무응답 확인(BE-13): 내가 보낸 요청 중 기준일 넘게 답이 없는 메일. 기준일은 말한 값(min_days) 또는 설정(기본 3일).
    대상(보낸 사람 · 분류)은 보지 않는다 — 받는 사람으로 거르는 것은 다음 단계."""
    if min_days is not None:
        try:
            min_days = int(min_days)
        except (TypeError, ValueError):
            return AgentResult(kind="ask", title=ASK["min_days"], **base)
        if not MIN_DAYS <= min_days <= MAX_DAYS:
            return AgentResult(kind="ask", title=ASK["min_days"], **base)
    rows = list_awaiting(db, user_id, min_days=min_days)
    days = min_days if min_days is not None else pol.load(db, user_id).await_days
    if not rows:
        return AgentResult(kind="empty", title=f"보낸 지 {days}일 이상 회신이 없는 요청 메일은 없습니다", **base)
    return AgentResult(kind="awaiting", title=f"보낸 지 {days}일 이상 회신이 없는 요청 메일 {len(rows)}건입니다",
                       awaiting=rows, **base)


def _summary(db: Session, user_id: int, params: dict[str, Any], base: dict) -> AgentResult:
    """T01 하루 요약 · 회고: 그날 브리핑을 채팅 카드로. 업무 줄만 싣고(같은 업무는 한 번), 문장은 브리핑 한 줄 그대로다."""
    kind = "evening" if params.get("kind") == "evening" else "morning"
    try:
        day = date.fromisoformat(params["date"]) if params.get("date") else None
    except (TypeError, ValueError):
        day = None
    b = briefings.build(db, user_id, kind, day)
    seen: set[int] = set()
    items = []
    tasks = {t.id: t for t in db.scalars(select(Task).where(Task.id.in_(
        {line["task_id"] for s in b["sections"] for line in s["items"] if line["task_id"] is not None})))}
    for s in b["sections"]:
        for line in s["items"]:
            t = tasks.get(line["task_id"])
            if t is None or t.id in seen:
                continue
            seen.add(t.id)
            items.append(AgentSummaryItem(task_id=t.id, mail_id=t.mail_id, text=t.text, due_at=as_kst(t.due_at), due_raw=t.due_raw,
                                          section=s["id"]))
    text = " · ".join(f"{s['label']} {s['count']}건" for s in b["sections"] if s["count"]) or b["summary"]
    return AgentResult(kind="summary", title=b["title"], summary=AgentSummary(text=text, items=items), **base)
