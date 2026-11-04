"""backend ↔ ai 공통 값 형식 (PR #4 리뷰 반영, 구조도 8절 '시각 · ID').

- 시각: ai 안에서는 '시간대 없는 KST'만 쓴다. 입구에서 맞춘다.
  시간대가 붙은 값(`+09:00` · `Z` 등)은 KST로 바꾼 뒤 시간대를 떼고, 시간대 없는 값은 KST로 본다.
  backend `clock.now()`(시간대 붙은 KST)를 그대로 보내도 된다. 응답 시각(`due_at` · `params.until`)은 시간대 없는 KST다.
- ID: backend DB id(정수)를 그대로 보내도 된다. ai는 문자열로 바꿔 쓰고 응답에도 문자열로 돌려준다.
"""
from datetime import datetime, timedelta, timezone
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator

KST = timezone(timedelta(hours=9), "KST")


def to_kst_naive(v: datetime) -> datetime:
    return v.astimezone(KST).replace(tzinfo=None) if v.tzinfo is not None else v


def _id_to_str(v):
    return str(v) if isinstance(v, int) and not isinstance(v, bool) else v


KstDateTime = Annotated[datetime, AfterValidator(to_kst_naive)]
Id = Annotated[str, BeforeValidator(_id_to_str)]
