"""메일 계정 연결 (BE-7, 구조도 8절 ①): Outlook 연결 · 목록 · 지금 동기화 · 연결 끊기.

흐름: 화면 [Outlook 연결] → `POST /api/accounts/outlook/connect` → {url} → 브라우저가 Microsoft 로그인으로 이동 →
Microsoft가 `GET /api/accounts/outlook/callback?code&state`로 돌려보냄 → 토큰 저장 · 첫 동기화 → 화면 `#/settings/accounts?outlook=...`(설정 > 메일 계정)로 이동.
- MS_GRAPH_REDIRECT_URI는 이 callback 주소다(Entra 앱 등록의 리디렉션 URI와 같아야 한다). 화면 프록시(5173)를 거치면
  돌아갈 화면도 같은 출처라 APP_URL을 비워 둔다.
- callback은 브라우저 이동이라 X-User-Id가 없다. 사용자는 connect 때 만든 state로 찾는다(한 번만 쓰고 10분 뒤 버림).
  connect는 브라우저에 nonce 쿠키(HttpOnly · SameSite=Lax)를 심고 callback이 대조한다 — 남이 시작한 연결 주소로 내 메일함이
  남의 사용자에 붙는 것(로그인 CSRF)을 막는다.
- 연결 끊기는 토큰 · 동기화 위치만 지운다. 이미 받은 메일 · 업무는 남긴다(되돌릴 수 없는 삭제를 하지 않는다).
"""
import logging
import secrets
from datetime import datetime
from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.clock import as_kst
from app.core.config import get_settings
from app.core.db import get_db
from app.core.user import Id, current_user_id
from app.mail import profile
from app.models import Account, MailSync

log = logging.getLogger("app.graph")
router = APIRouter(prefix="/api")
NONCE_COOKIE = "cne_outlook_login"
NONCE_PATH = "/api/accounts/outlook"


class AccountView(BaseModel):
    id: int
    provider: str  # dummy | outlook_graph
    email: str
    aliases: list[str] = []  # 이 계정으로 받는 다른 주소(별칭). 분류가 나에게 온 메일로 본다
    connected: bool  # Outlook: 토큰이 있음. 더미는 늘 참
    last_synced_at: datetime | None


class AccountList(BaseModel):
    outlook_enabled: bool  # 서버가 Outlook 연결을 켰나(MAIL_SOURCE=outlook_graph). 거짓이면 화면은 연결 버튼 대신 안내
    items: list[AccountView]


class ConnectStart(BaseModel):
    url: str


class SyncResult(BaseModel):
    added: int
    updated: int
    removed: int
    last_synced_at: datetime | None


def _view(a: Account) -> AccountView:
    return AccountView(id=a.id, provider=a.provider, email=a.email, aliases=list(a.aliases or []), last_synced_at=as_kst(a.last_synced_at),
                       connected=a.provider != "outlook_graph" or a.refresh_token_enc is not None)


def _graph_on() -> None:
    if get_settings().mail_source != "outlook_graph":
        raise HTTPException(501, "Outlook 연결이 켜져 있지 않습니다(MAIL_SOURCE=outlook_graph)")


def _back(result: Literal["connected", "error"], reason: str | None = None) -> RedirectResponse:
    q = urlencode({"outlook": result, **({"reason": reason} if reason else {})})
    return RedirectResponse(f"{get_settings().app_url}/#/settings/accounts?{q}", status_code=303)


@router.get("/accounts", response_model=AccountList)
def list_accounts(user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> AccountList:
    items = [_view(a) for a in db.scalars(select(Account).where(Account.user_id == user_id).order_by(Account.id))]
    return AccountList(outlook_enabled=get_settings().mail_source == "outlook_graph", items=items)


@router.post("/accounts/outlook/connect", response_model=ConnectStart)
def connect_outlook(response: Response, user_id: int = Depends(current_user_id)) -> ConnectStart:
    _graph_on()
    from app.mail import graph

    nonce = secrets.token_urlsafe(24)
    response.set_cookie(NONCE_COOKIE, nonce, max_age=int(graph.STATE_TTL.total_seconds()), path=NONCE_PATH, httponly=True,
                        samesite="lax", secure=get_settings().app_mode == "prod")
    return ConnectStart(url=graph.authorize_url(user_id, nonce))


@router.get("/accounts/outlook/callback", include_in_schema=False)
def outlook_callback(state: str = "", code: str = "", error: str = "", db: Session = Depends(get_db),
                     nonce: str = Cookie(default="", alias=NONCE_COOKIE)) -> RedirectResponse:
    _graph_on()
    from app.mail import graph, graph_sync

    pending = graph.take_state(state, nonce) if state and nonce else None
    if pending is None:
        return _back("error", "expired")  # 지났거나 · 다른 탭에서 이미 썼거나 · 연결을 시작한 브라우저가 아니다 → 다시 연결
    if error or not code:
        return _back("error", "denied" if error == "access_denied" else "failed")  # 사용자가 동의를 취소했거나 로그인 실패
    user_id, verifier = pending
    try:
        tok = graph.exchange_code(code, verifier)
        me = graph.me(tok["access_token"])
    except graph.GraphError as e:
        log.warning("Outlook 로그인 토큰 교환 실패 status=%s code=%s", e.status, e.code)
        return _back("error", "failed")
    email = (me.get("mail") or me.get("userPrincipalName") or "").strip().lower()
    if not email:
        return _back("error", "failed")
    account = db.scalar(select(Account).where(Account.user_id == user_id, Account.provider == "outlook_graph",
                                              Account.email == email))
    if account is None:
        account = Account(user_id=user_id, provider="outlook_graph", email=email)
        db.add(account)
    graph.save_tokens(account, tok)
    account.aliases = []  # 다시 연결하면 잘못 배운 별칭을 지우고 처음부터 배운다(mail/profile.py)
    profile.apply_me(db, account, me)  # 내 정보(이름 · 회사 계정이면 부서 · 직함) · 내 주소를 Outlook 계정으로
    profile.learn_recent(db, account)
    db.commit()
    try:  # 첫 동기화. 실패해도 연결은 된 것이다 — 스케줄러가 다음 틱에 다시 받는다
        graph_sync.sync_account(db, account)
    except Exception as e:  # noqa: BLE001 - 연결은 끝났다. 동기화 오류로 오류 화면을 띄우지 않는다
        db.rollback()
        log.warning("Outlook 첫 동기화 실패 account=%s %s", account.id, getattr(e, "status", e.__class__.__name__))
    resp = _back("connected")
    resp.delete_cookie(NONCE_COOKIE, path=NONCE_PATH)
    return resp


def refresh_profile(db: Session, account: Account) -> None:
    """[지금 받기] 때 내 정보 · 내 주소를 Outlook에서 다시 맞춘다(Outlook에서 이름 · 별칭을 바꾼 경우)."""
    from app.mail import graph

    profile.apply_me(db, account, graph.call(db, account, "GET", "/me", params={"$select": graph.ME_SELECT}).json())
    profile.learn_recent(db, account)
    db.commit()


def _mine(db: Session, account_id: int, user_id: int) -> Account:
    a = db.get(Account, account_id)
    if a is None or a.user_id != user_id:
        raise HTTPException(404, "없는 계정입니다")
    return a


@router.post("/accounts/{account_id}/sync", response_model=SyncResult)
def sync_now(account_id: Id, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> SyncResult:
    account = _mine(db, account_id, user_id)
    if account.provider != "outlook_graph":
        raise HTTPException(422, "Outlook 계정만 동기화합니다")
    from app.mail import graph, graph_sync

    try:
        refresh_profile(db, account)
        counts = graph_sync.sync_account(db, account)
    except graph.GraphAuthError:
        db.rollback()
        raise HTTPException(409, "Outlook 연결이 끊겼습니다. 설정에서 다시 연결해 주세요") from None
    except graph.GraphError as e:
        db.rollback()
        raise HTTPException(502, f"Outlook에서 메일을 받지 못했습니다({e.status})") from None
    return SyncResult(**counts, last_synced_at=as_kst(account.last_synced_at))


@router.post("/accounts/{account_id}/disconnect", response_model=AccountView)
def disconnect(account_id: Id, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> AccountView:
    account = _mine(db, account_id, user_id)
    if account.provider != "outlook_graph":
        raise HTTPException(422, "Outlook 계정만 연결을 끊습니다")
    from app.mail import graph

    with graph.account_lock(account.id):  # 도는 동기화가 끝난 뒤 끊는다(끊은 뒤 그 동기화가 토큰 · 위치를 되살리지 않게)
        db.refresh(account)
        from app.mail import graph_notify

        graph_notify.drop(db, account)  # 토큰을 지우기 전에(구독 지우기에 토큰이 든다)
        account.access_token_enc = account.refresh_token_enc = account.expires_at = None
        db.execute(delete(MailSync).where(MailSync.account_id == account.id))
        db.commit()
    return _view(account)
