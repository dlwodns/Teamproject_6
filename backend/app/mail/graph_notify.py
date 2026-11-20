"""Graph 변경 알림 (BE-7): 받은 편지함에 메일이 오거나 바뀌면 Graph가 우리 주소로 알려 주고, 그 계정만 바로 동기화한다.

- https://learn.microsoft.com/en-us/graph/change-notifications-delivery-webhooks
  구독: POST /subscriptions {changeType, notificationUrl, resource, expirationDateTime, clientState}. 만들 때 Graph가
  notificationUrl?validationToken=…으로 확인하고, 우리는 10초 안에 그 값을 text/plain으로 돌려줘야 한다.
  알림 본문의 clientState가 우리가 준 값과 같을 때만 믿는다(누구나 이 주소를 부를 수 있다). 알림에는 3초 안에 답한다(동기화는 뒤에서).
- 메일 구독은 최대 10080분(7일)까지 산다. 여기서는 SUBSCRIPTION_LIFETIME으로 만들고, RENEW_BEFORE 안에 끝나면 늘린다(동기화 틱).
- GRAPH_NOTIFY_URL(공개 HTTPS 주소, 예: https://cne.example.com)이 있을 때만 켠다. 로컬 개발(localhost)은 Graph가 닿지 못해 쓰지 않는다 —
  그때는 1분 폴링(jobs/scheduler)만 돈다. 알림을 놓쳐도 폴링이 메운다.
"""
import logging
import os
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import real_now
from app.mail import graph
from app.models import Account

log = logging.getLogger("app.graph")

RESOURCE = "me/mailFolders('inbox')/messages"
SUBSCRIPTION_LIFETIME = timedelta(days=3)
RENEW_BEFORE = timedelta(days=1)
NOTIFY_PATH = "/api/graph/notify"


def notify_url() -> str | None:
    """알림 받을 주소. 공개 HTTPS가 아니면 None(Graph는 https만 받는다)."""
    base = os.environ.get("GRAPH_NOTIFY_URL", "").strip().rstrip("/")
    return base + NOTIFY_PATH if base.startswith("https://") else None


def _expiry() -> tuple[datetime, str]:
    """(우리 저장용 naive 실제 시각, Graph용 UTC ISO)."""
    local = real_now() + SUBSCRIPTION_LIFETIME
    utc = datetime.now(UTC) + SUBSCRIPTION_LIFETIME
    return local, utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure(db: Session, account: Account, url: str) -> None:
    """구독이 없으면 만들고, 곧 끝나면 늘린다. 늘리기가 404면(Graph가 지움) 새로 만든다."""
    if account.subscription_id and account.subscription_expires_at and account.subscription_expires_at - RENEW_BEFORE > real_now():
        return
    local, utc = _expiry()
    if account.subscription_id:
        try:
            graph.call(db, account, "PATCH", f"/subscriptions/{account.subscription_id}", json={"expirationDateTime": utc})
            account.subscription_expires_at = local
            db.commit()
            return
        except graph.GraphError as e:
            if e.status != 404:
                raise
    state = secrets.token_urlsafe(32)
    sub = graph.call(db, account, "POST", "/subscriptions", json={
        "changeType": "created,updated,deleted", "notificationUrl": url, "resource": RESOURCE,
        "expirationDateTime": utc, "clientState": state}).json()
    account.subscription_id, account.subscription_expires_at, account.notify_state = sub["id"], local, state
    db.commit()


def ensure_all(db: Session) -> None:
    """동기화 틱마다. GRAPH_NOTIFY_URL이 없으면 아무것도 하지 않는다. 한 계정이 실패해도 다음 계정은 한다."""
    url = notify_url()
    if url is None:
        return
    for account in db.scalars(select(Account).where(Account.provider == "outlook_graph", Account.refresh_token_enc.is_not(None))).all():
        try:
            ensure(db, account, url)
        except graph.GraphError as e:
            db.rollback()
            log.warning("Outlook 변경 알림 구독 실패 account=%s status=%s", account.id, e.status)


def drop(db: Session, account: Account) -> None:
    """연결을 끊을 때. Graph 쪽 구독은 지워 보고(실패해도 만료되면 없어진다) 우리 칸은 비운다."""
    if account.subscription_id and account.refresh_token_enc:
        try:
            graph.call(db, account, "DELETE", f"/subscriptions/{account.subscription_id}")
        except graph.GraphError:
            pass
    account.subscription_id = account.subscription_expires_at = account.notify_state = None


def accounts_to_sync(db: Session, notifications: list[dict]) -> set[int]:
    """알림 묶음 → 동기화할 계정 id. 구독 id와 clientState가 둘 다 맞는 것만(위조 알림은 버린다)."""
    out = set()
    for n in notifications:
        sub_id, state = n.get("subscriptionId"), n.get("clientState")
        if not sub_id or not state:
            continue
        account = db.scalar(select(Account).where(Account.subscription_id == sub_id))
        if account is not None and account.notify_state and secrets.compare_digest(account.notify_state, state):
            out.add(account.id)
    return out
