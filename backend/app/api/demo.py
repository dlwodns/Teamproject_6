"""시연 도구 — 시간 이동 (BE-14 · BE-D23). `DEMO_TOOLS=true`일 때만 등록한다.

APP_MODE와 관계없다(dev여도 DEMO_TOOLS가 꺼져 있으면 경로 자체가 없어 404). 공개 배포(Railway)에서는
켜지 않는다: 기본 인증을 뺀 뒤(#310 · D58) 켜면 주소를 아는 누구나 모든 사용자의 서비스 시각을 옮길 수 있다. 서비스 시각은 모든 사용자가 함께 쓰므로 바꿀 때마다 로그를 남긴다.

시각 장치는 clock.set_offset 하나다(#49 CLOCK_START와 같다). 단일 worker를 전제로 한다:
offset은 프로세스 메모리 값이라 worker가 여럿이면 이 요청을 받은 worker만 바뀐다.
리마인더 강제 실행 POST /api/dev/reminders/run(BE-12 엔진)도 여기 있다. 서비스 시각은 옮기지 않고 그 시각으로 엔진만 한 번 돌린다.
"""
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from sqlalchemy.orm import Session

from app.core import clock
from app.core.clock import as_kst
from app.core.config import get_settings
from app.core.db import get_db
from app.reminders import engine
from app.schemas.reminders import RunResult

router = APIRouter(prefix="/api/dev/clock", tags=["demo"])
reminders_router = APIRouter(prefix="/api/dev/reminders", tags=["demo"])
log = logging.getLogger(__name__)

MAX_FORWARD_MIN = 60 * 24 * 30  # 한 번에 30일까지. 오타(분 대신 초)로 몇 년씩 건너뛰지 않게
# 옮길 수 있는 범위. 9999-12-31처럼 끝에 붙이면 시간이 흐르다 날짜가 넘쳐(OverflowError) 모든 요청이 500이 된다
AT_MIN, AT_MAX = datetime(2000, 1, 1), datetime(2099, 12, 31, 23, 59, 59)


class ClockView(BaseModel):
    now: datetime  # 서비스 시각(+09:00)
    offset_seconds: int  # 서비스 시각 - 실제 시각
    clock_start: str | None  # 되돌리기(reset) 기준. CLOCK_START가 비면 null(실제 시각)


class ClockMove(BaseModel):
    """둘 중 하나만. at은 그 시각으로(앞 · 뒤 모두), forward_minutes는 지금에서 앞으로만."""
    model_config = ConfigDict(extra="forbid")

    at: datetime | None = None  # 시간대 없으면 KST
    forward_minutes: StrictInt | None = Field(default=None, ge=1, le=MAX_FORWARD_MIN)  # true · "60"은 422

    @field_validator("at")
    @classmethod
    def _in_range(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return v
        try:
            ok = AT_MIN <= clock.to_kst_naive(v) <= AT_MAX
        except OverflowError:  # 9999-12-31T23:59-12:00처럼 KST로 바꾸다 넘침
            ok = False
        if not ok:
            raise ValueError("2000-01-01 ~ 2099-12-31 사이 시각이어야 한다")
        return v


def _view() -> ClockView:
    return ClockView(now=as_kst(clock.now()), offset_seconds=int(clock.get_offset().total_seconds()),
                     clock_start=get_settings().clock_start or None)


@router.get("", response_model=ClockView)
def get_clock() -> ClockView:
    return _view()


@router.post("", response_model=ClockView)
def move_clock(body: ClockMove) -> ClockView:
    if (body.at is None) == (body.forward_minutes is None):
        raise HTTPException(422, "at과 forward_minutes 중 하나만 보낸다")
    before = clock.now()
    if body.at is not None:
        clock.set_offset(clock.to_kst_naive(body.at) - clock.real_now())
    else:
        if clock.now() + timedelta(minutes=body.forward_minutes) > AT_MAX:
            raise HTTPException(422, "2099-12-31을 넘겨 옮길 수 없다")
        clock.set_offset(clock.get_offset() + timedelta(minutes=body.forward_minutes))
    log.warning("시연 시간 이동: %s → %s", before.replace(microsecond=0), clock.now().replace(microsecond=0))
    return _view()


@router.post("/reset", response_model=ClockView)
def reset_clock() -> ClockView:
    """서버를 막 띄웠을 때처럼 CLOCK_START(비면 실제 시각)로 돌린다."""
    clock.init_clock(get_settings().clock_start)
    log.warning("시연 시간 되돌림: %s", clock.now().replace(microsecond=0))
    return _view()


@reminders_router.post("/run", response_model=RunResult)
def run_reminders(at: datetime | None = None, db: Session = Depends(get_db)) -> RunResult:
    """그 시각(없으면 서비스 시각)으로 리마인더 엔진을 모든 사용자에 한 번 돌린다(BE-12). 서비스 시각은 옮기지 않는다.
    시각까지 옮기려면 먼저 POST /api/dev/clock."""
    when = clock.to_kst_naive(at) if at else clock.now()
    return RunResult(at=as_kst(when.replace(second=0, microsecond=0)), results=engine.run_all(db, when))


def install(app: FastAPI) -> bool:
    """DEMO_TOOLS=true일 때만 라우터를 단다. 달았으면 True."""
    if not get_settings().demo_tools:
        return False
    app.include_router(router)
    app.include_router(reminders_router)
    log.warning("시연 도구 켜짐(DEMO_TOOLS): /api/dev/clock · /api/dev/reminders/run — 누구나 서비스 시각을 바꾸고 알림을 만들 수 있다. "
                "공개 서버면 프록시 인증으로 막는다")
    return True
