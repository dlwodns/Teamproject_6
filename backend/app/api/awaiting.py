"""응답 대기 GET /api/awaiting (BE-13 · 기획 detail 5절). 메일 화면 '응답 대기' 칸 · 대시보드가 쓴다."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.user import current_user_id
from app.schemas.awaiting import AwaitingView
from app.services.awaiting import MAX_DAYS, MIN_DAYS, list_awaiting

router = APIRouter(prefix="/api")


@router.get("/awaiting", response_model=list[AwaitingView])
def get_awaiting(min_days: int | None = Query(None, ge=MIN_DAYS, le=MAX_DAYS), user_id: int = Depends(current_user_id),
                 db: Session = Depends(get_db)) -> list[AwaitingView]:
    """min_days가 없으면 설정의 무응답 기준일(기본 3일). 오래 기다린 것부터."""
    return list_awaiting(db, user_id, min_days=min_days)
