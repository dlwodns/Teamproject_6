"""브라우저 세션 (AUTH_MODE=session, INF-11 11-25). 비밀번호 없이 브라우저마다 사용자 하나를 만든다.

- POST /api/session: 화면이 시작할 때 부른다. 쿠키 세션이 있으면 그 사용자, 없으면 새 사용자 + 새 세션(httpOnly 쿠키).
  각자 설정 → 메일에서 자기 Outlook을 연결하면 그 사용자의 계정이 된다(accounts.py는 이미 사용자별).
  AUTH_MODE=header면 아무것도 만들지 않는다(개발 · 테스트는 X-User-Id 그대로).
- GET /api/session/demo: DEMO_SHARE_USER_ID가 있을 때만. 이 브라우저를 시연 사용자(더미 메일)에 붙이고 화면으로 보낸다.
  주소를 아는 사람은 모두 그 사용자로 들어오므로 시연 사용자에 실제 메일을 연결하지 않는다.
쿠키를 지우거나 다른 브라우저로 들어오면 새 사용자다(메일을 다시 연결한다). 계정 로그인은 BE-6 이후.
"""
import secrets

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.user import SESSION_COOKIE, session_user_id, token_hash
from app.models import User, WebSession

router = APIRouter(prefix="/api")
MAX_AGE = 60 * 60 * 24 * 180  # 180일. 지나면 새 사용자(메일 다시 연결)


class SessionView(BaseModel):
    mode: str  # header | session
    user_id: int | None
    created: bool


def _set_cookie(response: Response, db: Session, user_id: int) -> None:
    token = secrets.token_urlsafe(32)
    db.add(WebSession(token_hash=token_hash(token), user_id=user_id))
    db.commit()
    response.set_cookie(SESSION_COOKIE, token, max_age=MAX_AGE, path="/", httponly=True, samesite="lax",
                        secure=get_settings().app_mode == "prod")


@router.post("/session", response_model=SessionView)
def start_session(response: Response, cne_session: str | None = Cookie(default=None),
                  db: Session = Depends(get_db)) -> SessionView:
    if get_settings().auth_mode != "session":
        return SessionView(mode="header", user_id=None, created=False)
    uid = session_user_id(db, cne_session)
    if uid is not None and db.get(User, uid) is not None:
        return SessionView(mode="session", user_id=uid, created=False)
    user = User(name="사용자")
    db.add(user)
    db.flush()
    _set_cookie(response, db, user.id)
    return SessionView(mode="session", user_id=user.id, created=True)


@router.get("/session/demo", include_in_schema=False)
def demo_session(db: Session = Depends(get_db)) -> RedirectResponse:
    s = get_settings()
    if s.auth_mode != "session" or s.demo_share_user_id <= 0 or db.get(User, s.demo_share_user_id) is None:
        raise HTTPException(404)
    back = RedirectResponse(f"{s.app_url}/", status_code=303)
    _set_cookie(back, db, s.demo_share_user_id)
    return back
