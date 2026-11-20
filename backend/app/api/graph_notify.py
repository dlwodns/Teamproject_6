"""Graph 변경 알림 받는 곳 (BE-7, app/mail/graph_notify.py). Graph가 부르므로 X-User-Id가 없다 — clientState로 믿을지 정한다.

- POST /api/graph/notify?validationToken=… → 그 값을 text/plain 200으로(구독 만들 때 확인)
- POST /api/graph/notify {value: [...]} → 맞는 계정만 뒤에서 동기화, 바로 202
"""
import logging
import threading

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session

from app.core.db import SessionLocal, get_db
from app.mail import graph_notify
from app.models import Account

log = logging.getLogger("app.graph")
router = APIRouter()


# 알림이 몰려도 계정마다 기다리는 동기화는 하나만 — 시작하면 빼서, 도는 동안 온 알림은 한 번 더 받게 한다
_waiting: set[int] = set()
_waiting_lock = threading.Lock()


def _sync(account_id: int) -> None:
    from app.mail import graph_sync

    with _waiting_lock:
        _waiting.discard(account_id)
    with SessionLocal() as db:
        account = db.get(Account, account_id)
        if account is not None:
            graph_sync.sync_one(db, account)  # 429 쉬기(_resume_at) · 실패 처리는 틱과 같다


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
        with _waiting_lock:
            if account_id in _waiting:
                continue
            _waiting.add(account_id)
        background.add_task(_sync, account_id)
    return Response(status_code=202)
