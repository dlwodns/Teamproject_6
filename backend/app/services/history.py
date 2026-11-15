"""기록 탭 — 에이전트가 한 일과 확인을 기다리는 일 (PL-16 5.1절).

새 표를 만들지 않는다. action_log(완료 · 되돌림)와 action_previews(확인 기다림)를 읽기만 한다.
- 되돌리기 기록(action = undo)은 따로 줄을 만들지 않고, 되돌린 원래 줄의 상태를 '되돌림'으로 보여 준다.
- 확인 기다림(미리보기를 만들고 아직 실행하지 않았고 만료 전)은 맨 위에 고정한다. 잊으면 그것이 누락이다.
- 실패 상태는 실패를 action_log에 남기는 경로가 생기면 붙인다(지금 backend에는 실패 기록이 없다).
문장은 행동 종류와 대상으로 채우는 고정 문장이다. 모델을 부르지 않는다.
"""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.models import ActionLog, ActionPreview, Task
from app.services import calendar, memory
from app.services.task_status import UNDO, _top_actions

RULE_LABEL = {"morning": "아침 요약", "overdue": "기한 지남", "due_soon": "기한 임박", "priority_sender": "상급자",
              "meeting": "일정 참석", "no_reply": "응답 대기"}
SOURCE_LABEL = {"agent_rule": "말로 시킴", "agent_model": "말로 시킴", "mcp": "MCP", "reply_auto": "자동",
                "calendar_auto": "자동", "mail_learn": "메일에서 알게 됨", "ui": "화면 버튼"}
AUTO_SOURCES = ("reply_auto", "calendar_auto", "mail_learn")
STATUS_WORD = {"done": "완료", "excluded": "목록에서 빼기", "snoozed": "미루기", "pending": "미처리로 돌리기"}


def _short(text: str, n: int = 24) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def label(via: str | None, source: str, memory_target: bool = False) -> tuple[str, str]:
    """(코드, 화면 문구). 코드는 via가 있으면 via, 기억 변경이면 memory, 그 밖에는 source."""
    if via == memory.MAIL_LEARN:
        return via, "메일에서 알게 됨"
    if via and via.startswith("suggestion:"):
        rule = via.split(":", 1)[1]
        return via, f"제안 카드({RULE_LABEL.get(rule) or _type_label(rule)})"
    if via and via.startswith("reminder:"):  # 리마인더 항목 버튼(BE-12)
        return via, f"리마인더({_type_label(via.split(':', 1)[1])})"
    if via == "history":
        return via, "기록 탭"
    if memory_target:
        return "memory", "에이전트가 아는 것" if source == "ui" else SOURCE_LABEL.get(source, source)
    return source, SOURCE_LABEL.get(source, source)


def via_of(log: ActionLog) -> tuple[str, str]:
    p = log.params_json or {}
    return label(p.get("via"), log.source, bool(p.get("target")))


def _when(dt: datetime) -> str:
    return f"{dt.month}/{dt.day} {dt:%H:%M}"


def _type_label(code: str) -> str:
    from app.reminders.types import label as type_label  # 리마인더 유형 이름(BE-12). import 줄을 다른 PR과 겹치지 않게 여기서

    return type_label(code)


def _task_text(log: ActionLog, tasks: dict[int, Task]) -> str:
    p = log.params_json or {}
    if p.get("kind") in ("due_change", "commitment"):  # 리마인더 적용(BE-12): T16 기한 바꾸기 · 약속 끝내기
        from app.reminders.actions import describe

        return describe(log, tasks) or log.action
    ids = log.affected_ids or []
    if len(ids) == 1 and ids[0] in tasks:
        who = f"'{_short(tasks[ids[0]].text)}' 업무를"
    else:
        who = f"업무 {len(ids)}건을"
    status = p.get("status")
    if status == "done":
        return f"{who} 완료했어요"
    if status == "excluded":
        return f"{who} 목록에서 뺐어요(업무 아님)"
    if status == "snoozed":
        until = p.get("snoozed_until")
        return f"{who} {_when(datetime.fromisoformat(until))}까지 미뤘어요" if until else f"{who} 미뤘어요"
    if status == "pending":
        return f"{who} 다시 미처리로 돌렸어요"
    return f"{who} 바꿨어요({log.action})"


def history(db: Session, user_id: int, days: int = 7, at: datetime | None = None) -> list[dict]:
    at = at or now()
    since = at - timedelta(days=days)
    logs = db.scalars(select(ActionLog).where(ActionLog.user_id == user_id, ActionLog.created_at >= since,
                                              ActionLog.action != UNDO).order_by(ActionLog.id.desc())).all()
    task_ids = sorted({i for x in logs for i in (x.affected_ids or [])})
    tasks = {t.id: t for t in db.scalars(select(Task).where(Task.id.in_(task_ids)))} if task_ids else {}
    task_top = _top_actions(db, user_id, task_ids) if task_ids else {}
    mem_top = memory.top_actions(db, user_id)
    # 되돌린 줄의 '다시 하기'는 그 줄을 되돌린 기록(살아 있는 것)을 다시 되돌리는 것이다
    undo_of = {(u.params_json or {}).get("action_id"): u.id for u in db.scalars(
        select(ActionLog).where(ActionLog.user_id == user_id, ActionLog.action == UNDO, ActionLog.undone_at.is_(None),
                                ActionLog.created_at >= since).order_by(ActionLog.id))}

    items = []
    previews = db.scalars(select(ActionPreview).where(ActionPreview.user_id == user_id,
                                                      ActionPreview.used_at.is_(None), ActionPreview.expires_at >= at)
                          .order_by(ActionPreview.created_at.desc())).all()
    for p in previews:
        params = p.params_json or {}
        word = STATUS_WORD.get(params.get("status"), p.action)
        # 에이전트가 만든 미리보기는 source(agent_rule · agent_model)를 params에 남긴다. 화면 버튼 미리보기는 None이라 ui
        via, via_label = label(params.get("via"), params.get("source") or "ui")
        items.append({"id": f"preview:{p.preview_id}", "state": "waiting", "action": p.action, "action_id": None,
                      "preview_id": p.preview_id, "text": f"업무 {len(p.target_ids or [])}건 {word} — 확인을 기다려요",
                      "via": via, "via_label": via_label, "auto": False, "at": p.created_at,
                      "expires_at": p.expires_at, "can_undo": False, "redo_action_id": None})
    for x in logs:
        target = (x.params_json or {}).get("target")
        if calendar.is_calendar(x):
            text = calendar.describe(x)
            live_top = calendar.can_undo(db, x)
        elif (x.params_json or {}).get("kind") == "commitment":  # 약속 끝내기(BE-12): 업무가 없어 affected_ids가 비어 있다
            from app.reminders.actions import _commitment_top  # 리마인더 쪽 import는 다른 PR과 겹치지 않게 여기서
            text = _task_text(x, tasks)
            live_top = _commitment_top(db, user_id, x.params_json["commitment_id"]) == x.id
        elif target:
            text = memory.describe(x)
            live_top = mem_top.get(target) == x.id
        else:
            text = _task_text(x, tasks)
            ids = x.affected_ids or []
            live_top = bool(ids) and all(task_top.get(i) == x.id for i in ids)
        state = "undone" if x.undone_at is not None else "done"
        via, via_label = via_of(x)
        items.append({"id": f"log:{x.id}", "state": state, "action": x.action, "action_id": x.id, "preview_id": None,
                      "text": text, "via": via, "via_label": via_label, "auto": x.source in AUTO_SOURCES or via == memory.MAIL_LEARN,
                      "at": x.created_at, "expires_at": None,
                      "can_undo": state == "done" and bool(x.before_json) and live_top,
                      "redo_action_id": undo_of.get(x.id) if state == "undone" else None})
    return items
