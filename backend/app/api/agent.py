"""에이전트 패널 API — 제안 카드(D50) · 기록 탭 · 에이전트가 아는 것(PL-16).

- 제안 카드 버튼은 새 실행 경로를 만들지 않는다. T03 · T05 · T10은 `PATCH /api/tasks/{id}`에 카드의 via를 실어 부른다.
- 조회(GET)는 어떤 행도 쓰지 않는다(PL-16 S1). 숨기기와 기억 변경만 쓴다.
- 기억 변경의 되돌리기는 업무와 같은 `POST /api/actions/{id}/undo`다. 기억은 구조화된 값만 둔다(services/memory.py 머리말).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.clock import as_kst, now
from app.core.db import get_db
from app.core.user import Id, current_user_id
from app.schemas.agent_panel import (AgentSettingsUpdate, AgentSettingsView, HideResult, HistoryList, MemoryChange,
                               MemoryView, MeUpdate, PersonUpdate, SuggestionList)
from app.services import history as history_service
from app.services import learn, memory, suggestions
from app.services.task_status import StatusError

router = APIRouter(prefix="/api")
HTTP = {"not_found": 404, "conflict": 409, "invalid": 422}


def _kst(d: dict, *keys: str) -> dict:
    return {**d, **{k: as_kst(d[k]) for k in keys}}


def _origin(o: dict) -> dict:
    return {**o, "at": as_kst(o["at"])}


def _memory_view(db: Session, user_id: int) -> dict:
    v = memory.view(db, user_id)
    v["me"]["origin"] = _origin(v["me"]["origin"])
    for item in v["people"]:
        item["origin"] = _origin(item["origin"])
    return v


def _write(db: Session, fn, *args, **kwargs):
    try:
        out = fn(db, *args, **kwargs)
    except StatusError as e:
        db.rollback()
        raise HTTPException(HTTP[e.kind], str(e)) from None
    db.commit()
    return out


# ---------- 제안 카드 ----------

@router.get("/suggestions", response_model=SuggestionList)
def list_suggestions(limit: int = Query(3, ge=1, le=50), user_id: int = Depends(current_user_id),
                     db: Session = Depends(get_db)) -> SuggestionList:
    at = now()
    cards = [_kst(c, "created_at") for c in suggestions.compute(db, user_id, at)]
    return SuggestionList(suggestions=cards[:limit], more=max(0, len(cards) - limit), total=len(cards),
                          generated_at=as_kst(at))


@router.post("/suggestions/{key}/hide", response_model=HideResult)
def hide_suggestion(key: str, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> HideResult:
    try:
        row = suggestions.hide(db, user_id, key)
    except suggestions.SuggestionError as e:
        db.rollback()
        raise HTTPException(422, str(e)) from None
    db.commit()
    return HideResult(key=row.key, hidden_until=as_kst(row.until))


# ---------- 기록 탭 ----------

@router.get("/actions/history", response_model=HistoryList)
def action_history(days: int = Query(7, ge=1, le=30), user_id: int = Depends(current_user_id),
                   db: Session = Depends(get_db)) -> HistoryList:
    items = [_kst(i, "at", "expires_at") for i in history_service.history(db, user_id, days)]
    return HistoryList(items=items, days=days)


# ---------- 에이전트가 아는 것 ----------

@router.get("/agent/memory", response_model=MemoryView)
def get_memory(user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> MemoryView:
    try:
        return MemoryView(**_memory_view(db, user_id))
    except StatusError as e:
        raise HTTPException(HTTP[e.kind], str(e)) from None


def _changed(db: Session, user_id: int, log) -> MemoryChange:
    return MemoryChange(action_id=log.id if log else None, memory=MemoryView(**_memory_view(db, user_id)))


@router.patch("/agent/memory/me", response_model=MemoryChange)
def patch_me(body: MeUpdate, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> MemoryChange:
    fields = {k: getattr(body, k) for k in body.model_fields_set}
    if fields.get("mailing_lists") is None and "mailing_lists" in fields:
        fields["mailing_lists"] = []  # null은 '목록 비우기'로 본다
    log = _write(db, memory.update_me, user_id, **fields)
    return _changed(db, user_id, log)


@router.patch("/agent/memory/people/{contact_id}", response_model=MemoryChange)
def patch_person(contact_id: Id, body: PersonUpdate, user_id: int = Depends(current_user_id),
                 db: Session = Depends(get_db)) -> MemoryChange:
    fields = {k: getattr(body, k) for k in body.model_fields_set}
    if any(fields.get(k, False) is None for k in ("is_superior", "is_favorite")) or fields.get("facts", {}) is None:
        raise HTTPException(422, "is_superior · is_favorite는 true 또는 false, facts는 객체만 받습니다")
    if "facts" in fields:  # 사용자가 고친 값은 근거 문장 없이 저장한다(화면에서 고침)
        fields["facts"] = {k: (None if v is None else {"value": v.strip()}) for k, v in fields["facts"].items()}
    log = _write(db, memory.update_person, user_id, contact_id, **fields)
    return _changed(db, user_id, log)


# ---------- 에이전트 설정 ----------

@router.get("/agent/settings", response_model=AgentSettingsView)
def get_agent_settings(user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> AgentSettingsView:
    return AgentSettingsView(learn_from_mail=learn.enabled(db, user_id))


@router.patch("/agent/settings", response_model=AgentSettingsView)
def patch_agent_settings(body: AgentSettingsUpdate, user_id: int = Depends(current_user_id),
                         db: Session = Depends(get_db)) -> AgentSettingsView:
    """메일 기억하기 켬 · 끔. 켠 뒤 새로 저장되는 사내 메일부터 배운다(이미 받은 메일은 본문을 저장하지 않아 다시 보지 않는다)."""
    learn.set_enabled(db, user_id, body.learn_from_mail)
    db.commit()
    return AgentSettingsView(learn_from_mail=learn.enabled(db, user_id))
