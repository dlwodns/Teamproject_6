"""설정 GET · PATCH /api/settings (FE 제안 계약 contract.ts Settings, 11-14 캐치봇 알림 시각).

하루 요약(아침 브리핑) remind_time · 퇴근 회고 evening_time을 사용자가 바꾼다. 리마인더 엔진은 매 틱 DB에서 정책을 다시 읽으므로
(app/reminders/policy.load) 바꾼 시각은 다음 틱부터 반영된다. 템플릿은 아직 서버에 없어 보내지 않는다(FE는 칸이 없으면 메뉴를 숨김).
"""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy.orm import Session

from app.core.clock import as_kst, to_kst_naive
from app.core.db import get_db
from app.core.user import current_user_id
from app.models import UserSettings

router = APIRouter(prefix="/api")

HHMM = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


class SettingsView(BaseModel):
    remind_time: str
    evening_time: str
    awaiting_reply_days: int
    quiet_start: str | None
    quiet_end: str | None
    reduce_motion: bool
    stt_mode: str
    reply_confirm_skip_until: datetime | None


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    remind_time: HHMM | None = None
    evening_time: HHMM | None = None
    awaiting_reply_days: int | None = Field(None, ge=1, le=30)
    quiet_start: HHMM | None = None
    quiet_end: HHMM | None = None
    reduce_motion: StrictBool | None = None
    stt_mode: str | None = Field(None, max_length=10)
    reply_confirm_skip_until: datetime | None = None  # '오늘 다시 보지 않음'(D48). 조회에만 있고 저장에 없어 422였다(#190 리뷰 1). null이면 해제


NOT_NULL = {"remind_time", "evening_time", "awaiting_reply_days", "reduce_motion", "stt_mode"}


def _row(db: Session, user_id: int) -> UserSettings:
    s = db.get(UserSettings, user_id)
    if s is None:
        s = UserSettings(user_id=user_id)
        db.add(s)
        db.flush()  # 기본값을 채운다
    return s


def _view(s: UserSettings) -> SettingsView:
    return SettingsView(remind_time=s.remind_time, evening_time=s.evening_time, awaiting_reply_days=s.awaiting_reply_days,
                        quiet_start=s.quiet_start, quiet_end=s.quiet_end, reduce_motion=s.reduce_motion,
                        stt_mode=s.stt_mode, reply_confirm_skip_until=as_kst(s.reply_confirm_skip_until))


@router.get("/settings", response_model=SettingsView)
def get_settings(user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> SettingsView:
    s = _row(db, user_id)
    db.commit()
    return _view(s)


@router.patch("/settings", response_model=SettingsView)
def patch_settings(body: SettingsPatch, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> SettingsView:
    """보낸 칸만 바꾼다. null은 조용한 시간(quiet_*) · 오늘 다시 보지 않음(reply_confirm_skip_until)만 '없음'(해제)으로 받는다. 다른 칸의 null은 무시한다."""
    s = _row(db, user_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is None and k in NOT_NULL:
            continue
        setattr(s, k, to_kst_naive(v) if isinstance(v, datetime) else v)  # 시각은 naive KST로 저장(D47)
    db.commit()
    return _view(s)
