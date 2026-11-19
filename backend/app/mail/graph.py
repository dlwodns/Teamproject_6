"""Microsoft Graph 연결 (BE-7): Outlook 로그인(OAuth 2.0 인증 코드 + PKCE) · 토큰 갱신 · Graph 호출 한 곳.

- 로그인: https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow
  웹 앱(비밀 키 있음)이라 client_secret과 PKCE code_verifier를 함께 보낸다. offline_access를 받아야 갱신 토큰이 온다.
  갱신하면 새 갱신 토큰이 오므로 매번 바꿔 저장한다(이전 것은 버린다).
- 메일 id는 바뀌지 않는 id를 쓴다(요청마다 `Prefer: IdType="ImmutableId"`). 메일함을 옮겨도 id가 같아 업무 · 리마인더 연결이 끊기지 않는다.
  https://learn.microsoft.com/en-us/graph/outlook-immutable-id
- 토큰 만료 시각은 실제 시각(real_now)으로 본다. 시연 시각(CLOCK_START)과 섞지 않는다.
- 밖으로 나가는 요청은 GRAPH_HOSTS만 허용한다(app/core/egress.py, graph=True). 토큰 · 본문은 로그에 남기지 않는다.
"""
import base64
import hashlib
import logging
import os
import secrets
import threading
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlsplit

import httpx
from sqlalchemy.orm import Session

from app.core import egress
from app.core.clock import real_now
from app.core.config import get_settings
from app.mail import tokens
from app.models import Account

log = logging.getLogger("app.graph")

GRAPH = "https://graph.microsoft.com/v1.0"
LOGIN = "https://login.microsoftonline.com"
# 지금 쓰는 것만 받는다. To Do · 연락처를 붙일 때 Tasks.ReadWrite · Contacts.ReadWrite를 더한다(그때 사용자가 다시 동의한다)
SCOPES = ("offline_access", "User.Read", "Mail.ReadWrite", "Mail.Send", "Calendars.ReadWrite")
STATE_TTL = timedelta(minutes=10)
EXPIRY_MARGIN = timedelta(minutes=2)  # 만료 직전 토큰으로 부르다 401 나지 않게 미리 갱신

# 테스트는 여기에 httpx.MockTransport를 넣는다. 운영은 None(실제 네트워크)
transport: httpx.BaseTransport | None = None


class GraphError(RuntimeError):
    """Graph · 로그인 서버가 실패로 답했다. status: HTTP 상태, code: Graph 오류 코드(있으면)."""

    def __init__(self, status: int, code: str | None = None, retry_after: str | None = None):
        super().__init__(f"Graph {status} {code or ''}".strip())
        self.status, self.code, self.retry_after = status, code, retry_after


class GraphAuthError(GraphError):
    """토큰을 쓸 수 없다(갱신 토큰 만료 · 동의 취소 · 키 바뀜). 사용자가 Outlook을 다시 연결해야 한다."""


def _client() -> httpx.Client:
    return httpx.Client(transport=transport, timeout=30.0, event_hooks=egress.hooks("", graph=True))


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


# ── 로그인 ──

# ponytail: 로그인 대기는 프로세스 메모리에 둔다(운영은 단일 프로세스, BE-D10). 로그인 도중 서버를 다시 켜면 다시 연결을 누르면 된다
_pending: dict[str, tuple[int, str, str, datetime]] = {}  # state → (사용자, PKCE verifier, 브라우저 nonce, 만료)
_pending_lock = threading.Lock()

# 계정별 잠금(단일 프로세스, BE-D10): 동기화 · 보내기~기록 · 연결 끊기가 같은 계정에서 겹치지 않게(같은 메일 두 번 넣기 · 끊은 연결 되살리기 방지)
_account_locks: dict[int, threading.RLock] = {}
_account_locks_lock = threading.Lock()
_refresh_lock = threading.Lock()  # 갱신 토큰은 쓸 때마다 바뀐다 → 두 곳이 같이 갱신하지 않게


def account_lock(account_id: int) -> threading.RLock:
    with _account_locks_lock:
        return _account_locks.setdefault(account_id, threading.RLock())


def authorize_url(user_id: int, nonce: str) -> str:
    """nonce: 연결을 시작한 브라우저에 쿠키로 심은 값. 돌아올 때 같은 브라우저인지 본다(로그인 CSRF — 남이 시작한 연결 주소로
    내 메일함이 남의 사용자에 붙지 않게)."""
    verifier = secrets.token_urlsafe(64)  # 43~128자(RFC 7636)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(32)
    now = real_now()
    with _pending_lock:
        for k in [k for k, v in _pending.items() if v[3] < now]:
            del _pending[k]
        _pending[state] = (user_id, verifier, nonce, now + STATE_TTL)
    params = {"client_id": _env("MS_GRAPH_CLIENT_ID"), "response_type": "code", "redirect_uri": _env("MS_GRAPH_REDIRECT_URI"),
              "response_mode": "query", "scope": " ".join(SCOPES), "state": state, "code_challenge": challenge,
              "code_challenge_method": "S256", "prompt": "select_account"}
    return f"{LOGIN}/{get_settings().ms_graph_tenant}/oauth2/v2.0/authorize?{urlencode(params)}"


def take_state(state: str, nonce: str) -> tuple[int, str] | None:
    """로그인 대기 하나를 꺼낸다(한 번만 쓴다). 없거나 지났거나 다른 브라우저(nonce 다름)면 None."""
    with _pending_lock:
        entry = _pending.pop(state, None)
    if entry is None or entry[3] < real_now() or not secrets.compare_digest(entry[2], nonce):
        return None
    return entry[0], entry[1]


def _token(data: dict) -> dict:
    data = {"client_id": _env("MS_GRAPH_CLIENT_ID"), "client_secret": _env("MS_GRAPH_CLIENT_SECRET"),
            "scope": " ".join(SCOPES), **data}
    url = f"{LOGIN}/{get_settings().ms_graph_tenant}/oauth2/v2.0/token"
    with _client() as c:
        r = _send(c, "POST", url, data=data)
    if r.status_code >= 400:
        code = _error_code(r, key="error")
        # invalid_grant = 코드 · 갱신 토큰을 더는 쓸 수 없음 → 다시 연결. 그 밖(서버 오류 등)은 잠시 뒤 다시
        raise (GraphAuthError if r.status_code in (400, 401) else GraphError)(r.status_code, code)
    return r.json()


def exchange_code(code: str, verifier: str) -> dict:
    return _token({"grant_type": "authorization_code", "code": code, "redirect_uri": _env("MS_GRAPH_REDIRECT_URI"),
                   "code_verifier": verifier})


def save_tokens(account: Account, tok: dict) -> None:
    account.access_token_enc = tokens.encrypt(tok["access_token"])
    if tok.get("refresh_token"):  # 갱신 응답에 없으면 이전 것을 그대로 쓴다
        account.refresh_token_enc = tokens.encrypt(tok["refresh_token"])
    account.expires_at = real_now() + timedelta(seconds=int(tok.get("expires_in", 3600)))


def access_token(db: Session, account: Account, *, force: bool = False) -> str:
    """쓸 수 있는 접근 토큰. 만료가 가까우면 갱신하고 바로 커밋한다 — 갱신 토큰이 바뀌므로 호출이 실패해도 새 것을 잃지 않게."""
    def fresh() -> bool:
        return bool(account.access_token_enc and account.expires_at and account.expires_at - EXPIRY_MARGIN > real_now())

    try:
        if not force and fresh():
            return tokens.decrypt(account.access_token_enc)
        with _refresh_lock:
            seen = account.access_token_enc
            db.refresh(account)  # 다른 세션이 막 갱신했거나 연결을 끊었으면 그 상태를 본다
            if not account.refresh_token_enc:
                raise GraphAuthError(401, "not_connected")  # 끊은 연결을 갱신으로 되살리지 않는다
            if fresh() and (not force or account.access_token_enc != seen):
                return tokens.decrypt(account.access_token_enc)
            tok = _token({"grant_type": "refresh_token", "refresh_token": tokens.decrypt(account.refresh_token_enc)})
            save_tokens(account, tok)
            db.commit()
    except tokens.TokenKeyError as e:
        raise GraphAuthError(401, "token_key") from e
    return tok["access_token"]


# ── Graph 호출 ──

def _send(c: httpx.Client, method: str, url: str, **kw) -> httpx.Response:
    """연결 실패 · 시간 초과 · 허용 목록 밖(EgressBlocked)도 GraphError(503)로 — 부르는 쪽은 GraphError 하나만 잡는다."""
    try:
        return c.request(method, url, **kw)
    except httpx.HTTPError as e:
        log.warning("Graph 연결 실패 %s %s: %s", method, urlsplit(url).hostname, e.__class__.__name__)
        raise GraphError(503, "network") from e


def _error_code(r: httpx.Response, key: str = "code") -> str | None:
    try:
        body = r.json()
    except ValueError:
        return None
    err = body.get("error") if isinstance(body, dict) else None
    if key == "error":  # 로그인 서버: {"error": "invalid_grant", ...}
        return err if isinstance(err, str) else None
    return err.get("code") if isinstance(err, dict) else None


def call(db: Session, account: Account, method: str, path: str, *, params: dict | None = None, json: dict | None = None,
         prefer: tuple[str, ...] = ()) -> httpx.Response:
    """Graph 한 번 부르기. path는 /me/... 또는 nextLink · deltaLink 전체 주소. 401이면 토큰을 갱신해 한 번 더 부른다.
    실패는 GraphError(429 · 5xx는 retry_after를 담는다 — 부르는 쪽이 다음 틱에 다시 한다).
    틱 동기화는 retry_after만큼 그 계정을 쉰다(graph_sync.sync_all). 화면 요청(보내기 등)은 기다리지 않고 바로 실패를 돌려준다."""
    url = path if path.startswith("https://") else GRAPH + path
    headers = {"Prefer": ", ".join(('IdType="ImmutableId"', *prefer))}
    with _client() as c:
        for attempt in (0, 1):
            headers["Authorization"] = f"Bearer {access_token(db, account, force=attempt == 1)}"
            r = _send(c, method, url, params=params, json=json, headers=headers)
            if r.status_code != 401:
                break
    if r.status_code == 401:
        raise GraphAuthError(401, _error_code(r))
    if r.status_code >= 400:
        log.warning("Graph 실패 %s %s → %s", method, url.split("?")[0].replace(GRAPH, ""), r.status_code)
        raise GraphError(r.status_code, _error_code(r), r.headers.get("Retry-After"))
    return r


def me(access: str) -> dict:
    """로그인 직후 계정 주소 확인(계정이 아직 DB에 없어 call을 쓰지 않는다)."""
    with _client() as c:
        r = _send(c, "GET", f"{GRAPH}/me", params={"$select": "mail,userPrincipalName,displayName"},
                  headers={"Authorization": f"Bearer {access}"})
    if r.status_code >= 400:
        raise GraphError(r.status_code, _error_code(r))
    return r.json()
