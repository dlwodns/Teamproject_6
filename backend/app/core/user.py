"""요청한 사용자 찾기 (PL-16). 로그인이 아직 없어 한곳에 모아 둔다.

- `X-User-Id` 헤더가 있으면 그 사용자다.
- 헤더가 없으면 개발 모드에서만 시연 사용자(1번)로 본다. 운영 모드에서는 401.
- 그 사용자가 DB에 없으면 401.
로그인(BE-6 이후)을 붙일 때는 이 함수 하나만 바꾸면 된다.
"""
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Path
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.models import User

DEV_USER_ID = 1
MAX_ID = 2**63 - 1  # SQLite INTEGER · Java long 범위. 넘으면 422(500이 아니라)
Id = Annotated[int, Path(ge=1, le=MAX_ID)]


def current_user_id(x_user_id: int | None = Header(default=None, ge=1, le=MAX_ID),
                    db: Session = Depends(get_db)) -> int:
    if x_user_id is None:
        if get_settings().app_mode != "dev":
            raise HTTPException(401, "X-User-Id 헤더가 필요합니다")
        x_user_id = DEV_USER_ID
    if db.get(User, x_user_id) is None:
        raise HTTPException(401, "없는 사용자입니다")
    return x_user_id
