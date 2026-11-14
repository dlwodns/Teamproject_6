"""에이전트 제안 카드 (D50 · `docs/10_planning/suggestion_cards.md`) — 이제 리마인더 목록의 앞쪽 N건이다(BE-12 · BE-D31).

판정 규칙은 리마인더 엔진(`app/reminders/rules.py`)으로 옮겼다. 제안 카드와 리마인더가 따로 판정하면 패널과 리마인더 화면이
서로 다른 것을 띄우기 때문이다(명세 reminders.md 2절). 이 모듈은 같은 항목을 예전 카드 형식(`SuggestionList`)으로 바꿔 줄 뿐이다.
- 카드 순서는 리마인더 목록 순서(기한 이른 순, 기한 없으면 생긴 순)다. 예전 '아침 요약' 카드는 브리핑(`GET /api/briefings/morning`)으로,
  '응답 대기' 묶음 카드는 보낸 메일마다 하나인 '답 없음' 항목으로 바뀌었다.
- 업무 항목 버튼은 예전과 같다([초안 보기]/[메일 열기] · [나중에] · [완료], 메뉴 [업무 아님] · [이 제안 숨기기]).
  업무가 아닌 항목과 정리 제안은 리마인더 버튼(open_mail · T07 · apply · dismiss)을 그대로 옮긴다.
- **읽기만 한다**(PL-16 S1). 숨기기만 hide()가 쓴다. 리마인더 [숨기기]도 같은 표 · 같은 규칙을 쓴다.
"""
from datetime import datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.models import Mail, SuggestionHide, Task
from app.reminders import policy as pol
from app.reminders import rules

DRAFT_CATEGORIES = rules.DRAFT_CATEGORIES
MIN_HIDE = timedelta(hours=1)


class SuggestionError(Exception):
    pass


def next_morning(at: datetime, remind: time) -> datetime:
    """숨김이 풀리는 때: 다음 R-아침 시각. 그 시각까지 1시간도 안 남았으면 그다음 날 R-아침
    (08:29에 숨긴 카드가 1분 뒤 다시 뜨지 않게 하는 방어선, 확정: 문규남 11-11 · BE-D16)."""
    today = datetime.combine(at.date(), remind)
    until = today if at < today else today + timedelta(days=1)
    return until if until - at >= MIN_HIDE else until + timedelta(days=1)


# ---------- 카드로 바꾸기 ----------

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


def _item_buttons(item: dict) -> list[dict]:
    mail_ids = [item["mail_id"]] if item["mail_id"] else []
    out = []
    for a in item["actions"]:
        kind = "navigate" if a["action"] == "open_mail" else "action"
        params = {k: v for k, v in a["params"].items() if k != "mail_id"}
        out.append(_btn(a["label"], a["action"], task_ids=item["task_ids"], mail_ids=mail_ids, params=params,
                        primary=a["primary"], kind=kind))
    return out


def card(db: Session, item: dict) -> dict:
    """리마인더 항목 하나 → 제안 카드 하나."""
    mail_ids = [item["mail_id"]] if item["mail_id"] else []
    if item["task_id"] is not None and item["type"] not in ("due_changed", "resolved", "reply_confirm"):
        task = db.get(Task, item["task_id"])
        buttons, menu = _task_buttons(task, db.get(Mail, task.mail_id))
    else:
        buttons, menu = _item_buttons(item), [_btn("이 제안 숨기기", "hide", kind="hide")]
    detail = [rules.short(item["title"], 40)] if item["type"] == "no_reply" else []
    return {"key": item["key"], "rule": item["type"], "via": f"suggestion:{item['type']}", "created_at": item["created_at"],
            "title": item["_card_title"], "detail": detail, "task_ids": item["task_ids"], "mail_ids": mail_ids,
            "buttons": buttons, "menu": menu}


def compute(db: Session, user_id: int, at: datetime | None = None) -> list[dict]:
    """지금 띄울 카드 전체(숨긴 것 제외), 리마인더 목록 순서대로."""
    from app.reminders import engine  # 이 모듈은 reminders.actions가 부르므로 엔진은 쓸 때 부른다(순환 방지)

    return [card(db, i) for i in engine.items(db, user_id, at or now())]


def hide(db: Session, user_id: int, key: str, at: datetime | None = None) -> SuggestionHide:
    """[이 제안 숨기기] · 리마인더 [숨기기]. 다음 R-아침까지. 커밋은 부르는 쪽이 한다."""
    if rules.parse_key(key) is None:
        raise SuggestionError(f"카드 키 형식이 아닙니다: {key}")
    at = at or now()
    until = next_morning(at, pol.load(db, user_id).remind)
    row = db.scalar(select(SuggestionHide).where(SuggestionHide.user_id == user_id, SuggestionHide.key == key))
    if row is None:
        row = SuggestionHide(user_id=user_id, key=key, until=until, created_at=at, mail_ids=[])
        db.add(row)
    else:
        row.until, row.created_at, row.mail_ids = until, at, []
    db.flush()
    return row
