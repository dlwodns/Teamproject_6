"""요청한 사용자 찾기 (PL-16). 로그인이 아직 없어 한곳에 모아 둔다.

AUTH_MODE=header(기본 · 개발 · 테스트):
- `X-User-Id` 헤더가 있으면 그 사용자다.
- 헤더가 없으면 개발 모드에서만 시연 사용자(1번)로 본다. 운영 모드에서는 401.
AUTH_MODE=session(공개 배포, INF-11 11-25):
- 헤더는 보지 않는다(값만 바꿔 남의 메일을 보는 길을 막는다). 브라우저 쿠키 세션(app/api/session.py)의 사용자다.
- 쿠키가 없거나 모르는 세션이면 401. 화면은 시작할 때 POST /api/session으로 세션을 받는다.
그 사용자가 DB에 없으면 401.
"""
import hashlib
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Path
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.models import User, WebSession

DEV_USER_ID = 1
MAX_ID = 2**63 - 1  # SQLite INTEGER · Java long 범위. 넘으면 422(500이 아니라)
Id = Annotated[int, Path(ge=1, le=MAX_ID)]
SESSION_COOKIE = "cne_session"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def session_user_id(db: Session, token: str | None) -> int | None:
    """쿠키 값 → 사용자 번호. 모르면 None."""
    if not token or len(token) > 200:
        return None
    s = db.get(WebSession, token_hash(token))
    return s.user_id if s is not None else None


def current_user_id(x_user_id: int | None = Header(default=None, ge=1, le=MAX_ID),
                    cne_session: str | None = Cookie(default=None),
                    db: Session = Depends(get_db)) -> int:
    settings = get_settings()
    if settings.auth_mode == "session":
        uid = session_user_id(db, cne_session)
        if uid is None:
            raise HTTPException(401, "세션이 없습니다. 화면을 새로 고칩니다")
    else:
        if x_user_id is None:
            if settings.app_mode != "dev":
                raise HTTPException(401, "X-User-Id 헤더가 필요합니다")
            x_user_id = DEV_USER_ID
        uid = x_user_id
    if db.get(User, uid) is None:
        raise HTTPException(401, "없는 사용자입니다")
    return uid
