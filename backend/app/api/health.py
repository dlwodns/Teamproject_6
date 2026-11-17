from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core import egress
from app.core.config import get_settings
from app.core.db import get_db

router = APIRouter()


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    # DB가 안 돼도 응답은 한다. status는 서비스, db는 DB 연결 상태다.
    try:
        db.execute(text("SELECT 1"))
        db_state = "ok"
    except SQLAlchemyError:
        db_state = "error"
    s = get_settings()
    # egress: backend의 외부 송신 건수 · 허용 목록(ai 서비스 주소만). 모델 호출 송신은 ai /health egress에 있다(시연 ⑧)
    return {"status": "ok", "app_mode": s.app_mode, "db": db_state, "egress": egress.snapshot(s.ai_service_url)}
