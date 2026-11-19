"""Graph 변경 알림 받는 곳 (BE-7, app/mail/graph_notify.py). Graph가 부르므로 X-User-Id가 없다 — clientState로 믿을지 정한다.

- POST /api/graph/notify?validationToken=… → 그 값을 text/plain 200으로(구독 만들 때 확인)
- POST /api/graph/notify {value: [...]} → 맞는 계정만 뒤에서 동기화, 바로 202
"""
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session

from app.core.db import SessionLocal, get_db
from app.mail import graph, graph_notify
from app.models import Account

log = logging.getLogger("app.graph")
router = APIRouter()


def _sync(account_id: int) -> None:
    from app.mail import graph_sync

    with SessionLocal() as db:
        account = db.get(Account, account_id)
        if account is None:
            return
        try:
            graph_sync.sync_account(db, account)
        except graph.GraphError as e:
            db.rollback()
            log.warning("알림 뒤 동기화 실패 account=%s status=%s", account_id, e.status)


@router.post(graph_notify.NOTIFY_PATH)
async def notify(request: Request, background: BackgroundTasks, db: Session = Depends(get_db)) -> Response:
    if (token := request.query_params.get("validationToken")) is not None:
        return PlainTextResponse(token[:1000])  # 구독 확인: 받은 값을 그대로(디코딩된 글자)
    try:
        payload = await request.json()
    except ValueError:
        return Response(status_code=400)
    items = payload.get("value") if isinstance(payload, dict) else None
    for account_id in graph_notify.accounts_to_sync(db, items if isinstance(items, list) else []):
        background.add_task(_sync, account_id)
    return Response(status_code=202)
