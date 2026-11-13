"""시나리오 평가용 개발 API (PL-16 5.5절). 운영에서는 없는 것처럼 404다.

에이전트를 여러 턴으로 재는 평가(`eval/scenarios/`)가 HTTP만으로 처음 상태를 넣고, 시각을 옮기고, 최종 상태를 읽는다.
HTTP만 쓰므로 테스트(TestClient)와 실제 서버(run_scenarios.py)에 같은 시나리오를 돌린다.

켜지는 조건(둘 다): APP_MODE=dev, 그리고 DB가 메모리이거나 파일 이름이 scenario로 시작하는 .db이고 주소에 쿼리가 없을 때.
load는 테이블을 모두 지우고 다시 만들기 때문에, ax.db · demo.db 같은 실제 개발 DB에서는 켜지지 않게 막는다.
    APP_MODE=dev DATABASE_URL=sqlite:///./scenario.db uvicorn app.main:app --port 8000
"""
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, make_url, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.clock import as_kst
from app.core.config import get_settings
from app.core.db import Base, engine, get_db, init_db
from app.models import (Account, ActionLog, ActionPreview, AgentSettings, Contact, Mail, MailingList, SuggestionHide,
                        Task, Template, User, UserSettings)
from app.services import ingest as ingest_service

router = APIRouter(prefix="/api/dev/scenario")

# 넣는 순서가 곧 외래 키 순서다
TABLES = [("users", User), ("settings", UserSettings), ("agent_settings", AgentSettings),
          ("mailing_lists", MailingList), ("accounts", Account),
          ("contacts", Contact), ("mails", Mail), ("tasks", Task), ("templates", Template)]
DEFAULTS = {Account: {"provider": "dummy"}}


def enabled() -> bool:
    """load가 테이블을 모두 지우므로 실제 DB(ax.db · demo.db)에서는 절대 켜지지 않게 좁게 본다.
    쿼리 문자열(?scenario=1)이나 폴더 이름(…/scenario/ax.db)으로는 통과하지 못한다. 윈도우 경로(역슬래시)도 본다."""
    s = get_settings()
    if s.app_mode != "dev":
        return False
    try:
        url = make_url(s.database_url)
    except Exception:  # noqa: BLE001 - 주소를 못 읽으면 끈다
        return False
    if url.query:
        return False
    name = url.database or ""
    if name in ("", ":memory:"):
        return True
    base = re.split(r"[\\/]", name)[-1]
    return base.startswith("scenario") and base.endswith(".db")


def guard() -> None:
    if not enabled():
        raise HTTPException(404, "Not Found")


class Fixture(BaseModel):
    model_config = ConfigDict(extra="forbid")  # 'tasks_typo' 같은 칸을 조용히 버리지 않는다

    now: datetime | None = None
    users: list[dict] = []
    settings: list[dict] = []
    agent_settings: list[dict] = []
    mailing_lists: list[dict] = []
    accounts: list[dict] = []
    contacts: list[dict] = []
    mails: list[dict] = []
    tasks: list[dict] = []
    templates: list[dict] = []


class Ingest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mail_id: int
    body: str = ""


class ClockSet(BaseModel):
    now: datetime | None  # null이면 실제 시각으로


def _move_clock(at: datetime | None) -> None:
    """서비스 시각을 at으로 옮긴다(이후로는 실제 시간만큼 흐른다). None이면 실제 시각으로 돌아간다.
    시간 이동 장치는 clock.set_offset 하나다(#49 CLOCK_START와 같은 장치)."""
    clock.set_offset(timedelta(0) if at is None else clock.to_kst_naive(at) - clock.real_now())


def _row(model, data: dict):
    cols = model.__table__.columns
    unknown = set(data) - set(cols.keys())
    if unknown:
        raise HTTPException(422, f"{model.__tablename__}에 없는 칸: {sorted(unknown)}")
    values = {**DEFAULTS.get(model, {}), **data}
    for name, v in values.items():
        if isinstance(cols[name].type, DateTime) and isinstance(v, str):
            values[name] = clock.to_kst_naive(datetime.fromisoformat(v))
    if model is Mail:
        values.setdefault("source_id", f"M-{values.get('id', '')}")
    return model(**values)


@router.post("/load", dependencies=[Depends(guard)])
def load(fx: Fixture) -> dict:
    Base.metadata.drop_all(engine)
    init_db()
    _move_clock(fx.now)
    from app.core.db import SessionLocal

    db = SessionLocal()
    try:
        for field, model in TABLES:
            for data in getattr(fx, field):
                db.add(_row(model, data))
            db.flush()
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:  # 외래 키 · 제약 위반은 시나리오 파일 오류다
        db.rollback()
        raise HTTPException(422, f"처음 상태를 넣지 못했습니다: {e.__class__.__name__}: {e}") from None
    finally:
        db.close()
    return {"ok": True, "now": as_kst(clock.now())}


@router.post("/clock", dependencies=[Depends(guard)])
def set_clock(body: ClockSet) -> dict:
    _move_clock(body.now)
    return {"now": as_kst(clock.now())}


@router.post("/ingest", dependencies=[Depends(guard)])
def ingest(body: Ingest, db: Session = Depends(get_db)) -> dict:
    """메일 저장 경로(동기화)가 메일을 넣은 직후 부르는 훅(services/ingest.py)을 그대로 부른다."""
    mail = db.get(Mail, body.mail_id)
    if mail is None:
        raise HTTPException(404, "없는 메일")
    account = db.get(Account, mail.account_id)
    logs, job = ingest_service.after_mail_saved(db, account.user_id, mail, body.body)
    db.commit()
    return {"learned": [{"action_id": x.id, "action": x.action, "target": x.params_json.get("target")} for x in logs],
            "classify_job_id": job.id if job else None}


@router.get("/state", dependencies=[Depends(guard)])
def state(db: Session = Depends(get_db)) -> dict:
    return {
        "now": as_kst(clock.now()),
        "tasks": [{"id": t.id, "status": t.status, "snoozed_until": as_kst(t.snoozed_until)}
                  for t in db.scalars(select(Task).order_by(Task.id))],
        "action_log": [{"id": x.id, "action": x.action, "source": x.source, "via": (x.params_json or {}).get("via"),
                        "target": (x.params_json or {}).get("target"), "undone": x.undone_at is not None}
                       for x in db.scalars(select(ActionLog).order_by(ActionLog.id))],
        "previews": [{"preview_id": p.preview_id, "used": p.used_at is not None}
                     for p in db.scalars(select(ActionPreview))],
        "contacts": [{"id": c.id, "is_superior": c.is_superior, "is_favorite": c.is_favorite}
                     for c in db.scalars(select(Contact).order_by(Contact.id))],
        "mailing_lists": [{"address": r.address, "kind": r.kind}
                          for r in db.scalars(select(MailingList).order_by(MailingList.address))],
        "suggestion_hides": sorted(db.scalars(select(SuggestionHide.key))),
    }
