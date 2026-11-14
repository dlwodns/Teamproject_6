"""에이전트 실행기 — ai가 해석한 명령(plan)을 검증 → 대상 해석 → 확인 판정 → 실행 · 미리보기 (BE-11, docs/30_backend/detail.md 4절).

plan은 ai `/agent/plan` 응답(`app/schemas/ai.PlanResult`)을 dict로 바꾼 것이다: {action, action_name, target, params, source, reason}.
상태 변경 · 기록 · 되돌리기는 `app/services/task_status.py`를 그대로 쓴다(REST 버튼과 같은 길). 커밋은 부르는 쪽이 한다.
"""
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.policy import needs_confirm
from app.agent.resolve import resolve
from app.agent.tools.registry import REGISTRY, ActionDef
from app.core.clock import as_kst, now, to_kst_naive
from app.models import ActionLog, Task
from app.reminders import briefings
from app.schemas.agent import AgentResult, AgentSummary, AgentSummaryItem, AgentTarget
from app.services import calendar, task_status
from app.services.task_status import UNDO, StatusError

SOURCE = {"rule": "agent_rule", "model": "agent_model"}
STATUS = {"T03": "done", "T05": "snoozed", "T10": "excluded"}  # 상태 변경 행동 → 바꿀 상태
ASK = {"until": "다시 알림 받을 시각을 알려 주십시오", "start": "등록할 날짜와 시각을 함께 알려 주십시오"}


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


def run(db: Session, user_id: int, plan: dict[str, Any]) -> AgentResult:
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
