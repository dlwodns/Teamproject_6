"""에이전트 실행기 — ai가 해석한 명령(plan)을 검증 → 대상 해석 → 확인 판정 → 실행 · 미리보기 (BE-11, docs/30_backend/detail.md 4절).

plan은 ai `/agent/plan` 응답(`app/schemas/ai.PlanResult`)을 dict로 바꾼 것이다: {action, action_name, target, params, source, reason}.
상태 변경 · 기록 · 되돌리기는 `app/services/task_status.py`를 그대로 쓴다(REST 버튼과 같은 길). 커밋은 부르는 쪽이 한다.
"""
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import privacy
from app.agent.policy import needs_confirm
from app.agent.resolve import match_contacts, resolve
from app.agent.tools.registry import REGISTRY, ActionDef
from app.core.clock import as_kst, now, to_kst_naive
from app.mail.body import fetch_body
from app.models import Account, ActionLog, Contact, Mail, Task, User
from app.reminders import briefings
from app.reminders import policy as pol
from app.schemas.agent import AgentDraft, AgentResult, AgentSend, AgentSummary, AgentSummaryItem, AgentTarget
from app.services import calendar, nudge, task_status
from app.services.awaiting import MAX_DAYS, MIN_DAYS, list_awaiting
from app.services.learn import reads_body
from app.services.task_status import UNDO, StatusError

SOURCE = {"rule": "agent_rule", "model": "agent_model"}
STATUS = {"T03": "done", "T05": "snoozed", "T10": "excluded"}  # 상태 변경 행동 → 바꿀 상태
ASK = {"until": "다시 알림 받을 시각을 알려 주십시오", "start": "등록할 날짜와 시각을 함께 알려 주십시오",
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


def run(db: Session, user_id: int, plan: dict[str, Any], ai: Any = None) -> AgentResult:
    """ai는 초안(T07)처럼 실행 중에 ai를 다시 부르는 행동만 쓴다. ai 오류(AIError)는 부른 쪽(503)으로 그대로 올린다."""
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
    if not a.ready:
        return AgentResult(kind="unsupported", title=f"'{a.name}'은(는) 준비 중인 기능입니다", **base)
    if missing := [k for k in a.required if params.get(k) is None]:  # 못 읽은 값은 키를 두고 null로 온다(#6 리뷰)
        return AgentResult(kind="ask", title=ASK.get(missing[0], "필요한 값을 알려 주십시오"), **base)
    try:
        until = _until(params.get("until"))
        if a.id == "T15":  # 일정 시작 · 끝도 같은 형식. 못 읽으면 되묻는다
            params = {**params, "start": _until(params.get("start")), "end": _until(params.get("end"))}
    except (TypeError, ValueError):  # '금요일'처럼 시각으로 못 읽는 값 → 500 대신 되묻기(#28 리뷰)
        return AgentResult(kind="ask", title=ASK["start" if a.id == "T15" else "until"], **base)
    if until is not None and until <= now():  # 지난 시각으로는 미루지 않는다(#31 리뷰)
        return AgentResult(kind="ask", title=ASK["until"], notes=[f"{until:%m/%d %H:%M}은 이미 지난 시각입니다"], **base)

    if a.id == "T01":
        return _summary(db, user_id, params, base)
    if a.id == "T06":
        return _awaiting(db, user_id, params.get("min_days"), base)
    if a.id == "T07":
        return _draft(db, user_id, plan.get("target") or {}, params.get("tone"), base, ai)
    if a.id == "T14":
        return _nudge(db, user_id, plan.get("target") or {}, params, source, base)
    if a.id == "T04":
        return _undo(db, user_id, params.get("action_id"), source, base)
    if a.id == "T15":
        return _calendar(db, user_id, plan.get("target") or {}, params, source, base)

    try:
        res = resolve(db, user_id, plan.get("target") or {}, by_due=(a.id == "T02"), allow_all=(a.kind == "query"))
    except (TypeError, ValueError, KeyError):  # 메일 id가 숫자가 아님 · 기간 끝이 없음 등 → 500 대신 되묻기(#28 리뷰)
        return AgentResult(kind="ask", title="대상을 확인하지 못했습니다. 다시 말씀해 주십시오", **base)
    if res.no_filter:
        return AgentResult(kind="ask", title="어떤 업무인지 알려 주세요(보낸 사람 · 분류 · 기간 · 메일 선택)", **base)
    if not res.task_ids:
        return AgentResult(kind="empty", title="해당하는 미처리 업무가 없습니다", notes=res.notes, **base)
    if a.kind == "query":
        targets = _targets(db, res.task_ids)
        later = sum(t.status == "snoozed" for t in targets)
        return AgentResult(kind="query", title=f"미처리 업무 {len(targets)}건입니다" + (f"(연기 {later}건 포함)" if later else ""),
                           targets=targets, notes=res.notes, **base)

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


DRAFT_PICK = "회신 초안을 쓸 메일을 골라 주십시오"


def _draft_mail(db: Session, user_id: int, target: dict[str, Any]) -> tuple[Mail | None, AgentResult | None, list[str]]:
    """초안을 쓸 받은 메일 하나. (메일, 되묻거나 없음 카드, 해석 노트).
    1) 고른 메일('이거') 2) 보낸 사람만 말했으면 그 사람의 받은 메일 중 가장 최근 1통(업무가 없거나 끝난 메일도, #204 리뷰)
    3) 분류 · 키워드 · 기간이 있으면 끝나지 않은 업무가 있는 메일에서 찾는다(resolve)."""
    mine = select(Mail).join(Account, Mail.account_id == Account.id).where(Account.user_id == user_id,
                                                                          Mail.direction == "received")
    try:
        ids = [int(i) for i in target.get("mail_ids") or []]
    except (TypeError, ValueError):  # 메일 id가 숫자가 아님 → 500 대신 되묻기(#28 리뷰)
        return None, AgentResult(kind="ask", title=DRAFT_PICK), []
    sender = target.get("sender")
    if ids:
        mails, notes = db.scalars(mine.where(Mail.id.in_(ids))).all(), [f"선택한 메일 {len(ids)}통"]
    elif sender and not any(target.get(k) for k in ("category", "keyword", "date_range")):
        people = match_contacts(db, user_id, sender)
        if not people:
            return None, None, [f"'{sender}'에 맞는 연락처가 없어요"]
        if len(people) > 1:
            names = " · ".join(f"{c.name or c.email} {c.position or ''}".strip() for c in people)
            return None, AgentResult(kind="ask", title=f"'{sender}'에 맞는 분이 {len(people)}명입니다. {DRAFT_PICK}"), [names]
        c = people[0]
        latest = db.scalars(mine.where(func.lower(Mail.sender) == c.email.lower())
                            .order_by(Mail.sent_at.desc(), Mail.id.desc()).limit(1)).first()
        who = f"{c.name or c.email} {c.position or ''}".strip()
        if latest is None:
            return None, None, [f"'{sender}' → {who}님에게 받은 메일이 없어요"]
        return latest, None, [f"'{sender}' → {who}님의 가장 최근 메일({latest.sent_at.month}/{latest.sent_at.day})"]
    else:
        res = resolve(db, user_id, target)
        if res.no_filter:
            return None, AgentResult(kind="ask", title=DRAFT_PICK), []
        mail_ids = {t.mail_id for t in db.scalars(select(Task).where(Task.id.in_(res.task_ids)))}
        mails, notes = db.scalars(mine.where(Mail.id.in_(mail_ids))).all(), res.notes
        if not mails:  # 이 경로는 업무 기준이라 범위를 밝힌다(메일이 있어도 '없다'로 읽히지 않게, #204 리뷰)
            return None, AgentResult(kind="empty", title=f"끝나지 않은 업무가 있는 메일 중 회신 초안을 쓸 메일을 찾지 못했습니다. "
                                                          f"{DRAFT_PICK}"), notes
    if len(mails) > 1:
        return None, AgentResult(kind="ask", title=f"메일이 {len(mails)}통입니다. 회신 초안을 쓸 메일을 하나만 골라 주십시오"), notes
    return (mails[0] if mails else None), None, notes


def _draft(db: Session, user_id: int, target: dict[str, Any], tone: Any, base: dict, ai: Any) -> AgentResult:
    """T07 회신 초안: 원 메일 · 내 이름을 개인정보 가리기(BE-6)한 뒤 ai /draft → 되돌려 초안 카드. 보내지 않는다(D37).
    본문 읽기가 꺼져 있으면 원 메일 본문은 보내지 않는다(제목만). ai를 쓸 수 없으면 AIError를 올린다(부른 쪽 503)."""
    mail, ask, notes = _draft_mail(db, user_id, target)
    if ask is not None:
        return ask.model_copy(update={**base, "notes": notes})
    if mail is None:
        return AgentResult(kind="empty", title="회신 초안을 쓸 메일을 찾지 못했습니다", notes=notes, **base)
    if ai is None:  # 테스트 · 내부 호출에서 ai 없이 부른 경우
        return AgentResult(kind="unsupported", title="'회신_초안'은(는) 준비 중인 기능입니다", **base)
    me = db.get(User, user_id)
    body = (fetch_body(db, mail) or "") if reads_body(db, user_id) else ""
    masker = privacy.masker_for(db, user_id)
    payload = masker.mask_obj({"kind": "reply", "tone": tone if tone in ("polite", "short") else "polite",
                               "mail": {"subject": mail.subject or "", "body": body, "sender": mail.sender},
                               "signer": me.name if me else None})
    out = masker.unmask_model(ai.draft(payload))
    contact = db.scalar(select(Contact).where(Contact.user_id == user_id, func.lower(Contact.email) == mail.sender.lower()))
    to = " ".join(x for x in ((contact.name if contact and contact.name else mail.sender.split("@")[0]),
                              contact.position if contact else None) if x)
    if out.source != "exaone":
        notes = [*notes, "모델을 쓰지 못해 기본 문장으로 작성했습니다"]
    subject = out.subject or f"RE: {mail.subject or ''}".strip()
    return AgentResult(kind="draft", title=f"{to}님께 보낼 회신 초안입니다", notes=notes,
                       draft=AgentDraft(mail_id=mail.id, to=to, subject=subject, text=out.body), **base)


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
            items.append(AgentSummaryItem(task_id=t.id, mail_id=t.mail_id, text=t.text, due_at=as_kst(t.due_at), due_raw=t.due_raw))
    text = " · ".join(f"{s['label']} {s['count']}건" for s in b["sections"] if s["count"]) or b["summary"]
    return AgentResult(kind="summary", title=b["title"], summary=AgentSummary(text=text, items=items), **base)
