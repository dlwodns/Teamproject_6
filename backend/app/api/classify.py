"""분류 상태 · 개발용 분류 실행 (PL-16, 구조도 12절 #17).

- `GET /api/classify/status`: 분류 대기 · 진행 · 완료 · 실패 수와, 완료 중 규칙 결과만 저장된 수(rule_only, 엑사원 재분류 대상).
  화면 '분류 대기 N건'(누락 0: 숨기지 않는다).
- `POST /api/classify/retry`: 화면 [다시 시도]. 실패를 대기열로 되돌린다. rule_only=true면 규칙 결과만 저장된 메일도 다시 분류한다.
- `POST /api/dev/classify/enqueue` · `POST /api/dev/classify/run`: 개발 모드에서만. 작업자(CLASSIFY_WORKER)를 켜지 않고
  한 번에 몇 건을 직접 돌려 볼 때 쓴다. 운영 모드에서는 404.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_client.client import AIClient, get_ai_client
from app.core.config import get_settings
from app.core.db import get_db
from app.core.user import current_user_id
from app.jobs import classify
from app.models import Account, Mail

router = APIRouter()


class ClassifyStatus(BaseModel):
    queued: int
    running: int
    done: int
    failed: int
    rule_only: int  # done 중 모델 실패로 규칙 결과만 저장된 것(엑사원 재분류 대상)


class RetryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_only: bool = False


@router.post("/api/classify/retry")
def retry(body: RetryBody, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> dict:
    n = classify.retry(db, user_id, rule_only=body.rule_only)
    db.commit()
    return {"requeued": n}


@router.get("/api/classify/status", response_model=ClassifyStatus)
def status(user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> ClassifyStatus:
    return ClassifyStatus(**classify.counts(db, user_id))


def _dev_only() -> None:
    if get_settings().app_mode != "dev":
        raise HTTPException(404, "Not Found")


class EnqueueBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mail_ids: list[int] | None = Field(default=None, max_length=500)  # 없으면 이 사용자의 받은 메일 중 작업이 없는 것 전부


@router.post("/api/dev/classify/enqueue", dependencies=[Depends(_dev_only)])
def dev_enqueue(body: EnqueueBody, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> dict:
    q = select(Mail).join(Account, Mail.account_id == Account.id).where(Account.user_id == user_id)
    if body.mail_ids is not None:
        q = q.where(Mail.id.in_(body.mail_ids))
    jobs = [j for m in db.scalars(q.order_by(Mail.sent_at, Mail.id)) if (j := classify.enqueue(db, m))]
    db.commit()
    return {"enqueued": len(jobs)}


@router.post("/api/dev/classify/run", dependencies=[Depends(_dev_only)])
def dev_run(limit: int = Query(1, ge=1, le=20), db: Session = Depends(get_db),
            ai: AIClient = Depends(get_ai_client)) -> dict:
    """대기 작업을 limit건까지 지금 처리한다(엑사원 한 통이 수십 초라 limit을 작게)."""
    results = []
    for _ in range(limit):
        out = classify.run_next(db, ai)
        if out is None:
            break
        results.append(out)
    return {"results": results}
