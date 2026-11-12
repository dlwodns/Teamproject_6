"""에이전트 실행기 — ai가 해석한 명령(plan)을 검증 → 대상 해석 → 확인 판정 → 실행 · 미리보기 (BE-11, docs/30_backend/detail.md 4절).

plan은 ai `/agent/plan` 응답(`app/schemas/ai.PlanResult`)을 dict로 바꾼 것이다: {action, action_name, target, params, source, reason}.
상태 변경 · 기록 · 되돌리기는 `app/services/task_status.py`를 그대로 쓴다(REST 버튼과 같은 길). 커밋은 부르는 쪽이 한다.
"""
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.policy import needs_confirm
from app.agent.resolve import resolve
from app.agent.tools.registry import REGISTRY, ActionDef
from app.core.clock import as_kst, now, to_kst_naive
from app.models import ActionLog, Task
from app.schemas.agent import AgentResult, AgentTarget
from app.services import task_status
from app.services.task_status import UNDO, StatusError

SOURCE = {"rule": "agent_rule", "model": "agent_model"}
STATUS = {"T03": "done", "T05": "snoozed", "T10": "excluded"}  # 상태 변경 행동 → 바꿀 상태
ASK = {"until": "언제 다시 알려 드릴까요?"}


def _verb(status: str, until: datetime | None, done: bool) -> str:
    if status == "snoozed":
        return f"{until:%m/%d %H:%M}까지 " + ("미뤘어요" if done else "미룰까요?")
    if status == "excluded":
        return "목록에서 " + ("뺐어요" if done else "뺄까요?")
    return "완료로 " + ("바꿨어요" if done else "바꿀까요?")


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
            return AgentResult(kind="ask", title="무엇을 할지 조금 더 구체적으로 말해 주세요", **base)
        return AgentResult(kind="unsupported", title="지원하지 않는 요청이에요", **base)
    a: ActionDef | None = REGISTRY.get(action_id)
    params: dict[str, Any] = plan.get("params") or {}
    if a is None or not set(params) <= set(a.params):  # 레지스트리에 없는 행동 · 계약에 없는 params 키(D47)
        return AgentResult(kind="unsupported", title="지원하지 않는 요청이에요", **base)
    base["action_name"] = a.name
    if not a.ready:
        return AgentResult(kind="unsupported", title=f"'{a.name}'은(는) 아직 준비 중이에요", **base)
    if missing := [k for k in a.required if params.get(k) is None]:  # 못 읽은 값은 키를 두고 null로 온다(#6 리뷰)
        return AgentResult(kind="ask", title=ASK.get(missing[0], "필요한 값을 알려 주세요"), **base)
    try:
        until = _until(params.get("until"))
    except (TypeError, ValueError):  # '금요일'처럼 시각으로 못 읽는 값 → 500 대신 되묻기(#28 리뷰)
        return AgentResult(kind="ask", title=ASK["until"], **base)
    if until is not None and until <= now():  # 지난 시각으로는 미루지 않는다(#31 리뷰)
        return AgentResult(kind="ask", title=ASK["until"], notes=[f"{until:%m/%d %H:%M}은 이미 지난 시각이에요"], **base)

    if a.id == "T04":
        return _undo(db, user_id, params.get("action_id"), source, base)

    try:
        res = resolve(db, user_id, plan.get("target") or {}, by_due=(a.id == "T02"), allow_all=(a.kind == "query"))
    except (TypeError, ValueError, KeyError):  # 메일 id가 숫자가 아님 · 기간 끝이 없음 등 → 500 대신 되묻기(#28 리뷰)
        return AgentResult(kind="ask", title="대상을 알아듣지 못했어요. 다시 말해 주세요", **base)
    if res.no_filter:
        return AgentResult(kind="ask", title="어떤 업무인지 알려 주세요(보낸 사람 · 분류 · 기간 · 메일 선택)", **base)
    if not res.task_ids:
        return AgentResult(kind="empty", title="해당하는 미처리 업무가 없어요", notes=res.notes, **base)
    if a.kind == "query":
        targets = _targets(db, res.task_ids)
        later = sum(t.status == "snoozed" for t in targets)
        return AgentResult(kind="query", title=f"미처리 업무 {len(targets)}건이에요" + (f"(나중에 {later}건 포함)" if later else ""),
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
            return AgentResult(kind="ask", title="어떤 행동을 되돌릴지 알려 주세요", **base)
        owned = db.get(ActionLog, target_id)
        if owned is None or owned.user_id != user_id:  # 다른 사용자의 행동은 되돌리지 않는다
            return AgentResult(kind="empty", title="되돌릴 행동이 없어요", **base)
    else:
        latest = db.scalar(select(ActionLog).where(ActionLog.user_id == user_id).order_by(ActionLog.id.desc()).limit(1))
        if latest is None:
            return AgentResult(kind="empty", title="되돌릴 행동이 없어요", **base)
        if latest.action == UNDO:
            return AgentResult(kind="ask", title="방금 되돌린 걸 다시 할까요, 그 전 것도 되돌릴까요?",
                               notes=[f"방금 행동 #{(latest.params_json or {}).get('action_id')}을(를) 되돌렸어요"], **base)
        target_id = latest.id
    try:
        log, back, tasks = task_status.undo(db, target_id, source=source)
    except StatusError as e:
        return AgentResult(kind="empty", title=f"되돌릴 수 없어요: {e}", **base)
    return AgentResult(kind="done", title=f"{len(tasks)}건을 되돌렸어요", targets=_targets(db, [t.id for t in tasks]),
                       action_id=back.id, notes=[f"행동 #{log.id}({log.action})를 되돌림"], **base)
