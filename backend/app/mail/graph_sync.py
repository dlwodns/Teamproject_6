"""Outlook 메일 동기화 (BE-7): 받은 · 보낸 편지함을 Graph 델타로 받아 mails에 넣는다.

- https://learn.microsoft.com/en-us/graph/api/message-delta — 처음엔 FIRST_SYNC_DAYS일치만(receivedDateTime ge), 그다음은 deltaLink부터 바뀐 것만.
  메일함 밖으로 옮기거나 지운 메일은 `@removed`로 온다. deltaLink가 만료되면(410) 처음부터 다시 받는다.
- 새 메일은 저장 직후 services/ingest.after_mail_saved(분류 대기열 · 문맥 기억 · 신호)를 부른다 — 더미 적재와 같은 길.
- 본문은 저장하지 않는다(구조도 10절). 델타 응답의 본문은 문맥 기억에 한 번 넘기고 버린다. 분류는 나중에 app/mail/body.py로 다시 가져온다.
- 우리 앱에서 보낸 메일은 보낼 때 그 메일 id로 이미 저장했으므로(services/sending.py) 보낸 편지함 델타로 와도 두 번 넣지 않는다.
"""
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now, real_now, to_kst_naive
from app.mail import graph
from app.models import Account, Mail, MailSync
from app.models.mail import HIDDEN_FOLDERS
from app.services.ingest import after_mail_saved

log = logging.getLogger("app.graph")

FOLDERS = {"inbox": "received", "sentitems": "sent"}  # 동기화하는 메일함 → direction
FIRST_SYNC_DAYS = 14  # ponytail: 처음 연결 때 가져오는 기간 고정. 사용자가 고르게 하려면 설정 칸으로
PAGE_SIZE = 50
SELECT = ("id,conversationId,subject,from,toRecipients,ccRecipients,receivedDateTime,sentDateTime,webLink,isRead,isDraft,"
          "body")


def _addr(r: dict | None) -> str:
    return ((r or {}).get("emailAddress") or {}).get("address") or ""


def _when(raw: str | None) -> datetime | None:
    return to_kst_naive(datetime.fromisoformat(raw)) if raw else None


def _start_url(since: datetime) -> tuple[str, dict]:
    return "/me/mailFolders/{folder}/messages/delta", {
        "$select": SELECT, "$filter": f"receivedDateTime ge {since.strftime('%Y-%m-%dT%H:%M:%SZ')}"}


def _folder_id(db: Session, account: Account, name: str, cache: dict) -> str | None:
    """잘 알려진 메일함 이름(archive · deleteditems) → 그 계정의 메일함 id. 보관 메일함이 없는 계정은 None."""
    if name not in cache:
        try:
            cache[name] = graph.call(db, account, "GET", f"/me/mailFolders/{name}", params={"$select": "id"}).json().get("id")
        except graph.GraphError as e:
            if e.status != 404:  # 잠깐 실패(429 · 5xx)를 '없음'으로 굳히지 않는다 — 이 쪽을 커밋하지 않고 다음 틱에 다시
                raise
            cache[name] = None
    return cache[name]


def _where_now(db: Session, account: Account, source_id: str, cache: dict) -> str:
    """델타의 @removed는 '이 메일함에서 빠짐'만 알려 준다(지움 · 옮김 구분 없음). 메일을 다시 찾아 지금 메일함을 본다.
    없으면(영구 삭제) 지운 것으로 본다. 그 밖의 메일함(사용자가 만든 폴더 등)은 other."""
    try:
        parent = graph.call(db, account, "GET", f"/me/messages/{source_id}", params={"$select": "parentFolderId"}).json()
    except graph.GraphError as e:
        if e.status == 404:
            return "deleteditems"
        raise
    for name in HIDDEN_FOLDERS:
        if parent.get("parentFolderId") and parent["parentFolderId"] == _folder_id(db, account, name, cache):
            return name
    return "other"


def _find(db: Session, account: Account, source_id: str) -> Mail | None:
    return db.scalar(select(Mail).where(Mail.account_id == account.id, Mail.source_id == source_id))


def _apply(db: Session, account: Account, folder: str, item: dict, counts: dict, moved: dict[str, str]) -> None:
    mail = _find(db, account, item["id"])
    if "@removed" in item:
        # 옮겨졌거나 지워졌다(moved: 미리 알아낸 지금 메일함). 우리 앱에서 옮긴 것은 이미 알고 있으니 그대로 둔다. 업무는 지우지 않는다
        if mail is not None and item["id"] in moved:
            mail.folder = moved[item["id"]]
            counts["removed"] += 1
        return
    if item.get("isDraft"):
        return
    if mail is not None:  # 이미 있음: 읽음 · 메일함만 맞춘다(델타는 읽음 바뀜도 보낸다)
        if "isRead" in item:
            if item["isRead"] and mail.read_at is None:
                mail.read_at = now()
            elif not item["isRead"]:
                mail.read_at = None
        mail.folder = folder
        counts["updated"] += 1
        return
    direction = FOLDERS[folder]
    at = _when(item.get("receivedDateTime") if direction == "received" else item.get("sentDateTime")) \
        or _when(item.get("receivedDateTime")) or now()
    mail = Mail(account_id=account.id, source_id=item["id"], conversation_id=item.get("conversationId"), direction=direction,
                sender=(_addr(item.get("from")) or account.email)[:255],
                recipients=[a for a in map(_addr, item.get("toRecipients") or []) if a],
                cc=[a for a in map(_addr, item.get("ccRecipients") or []) if a],
                subject=(item.get("subject") or "")[:500], sent_at=at, web_link=item.get("webLink"), folder=folder,
                read_at=now() if item.get("isRead") or direction == "sent" else None)
    db.add(mail)
    db.flush()
    body = (item.get("body") or {}).get("content")
    after_mail_saved(db, account.user_id, mail, body)
    counts["added"] += 1


def _sync_folder(db: Session, account: Account, folder: str, counts: dict, cache: dict) -> None:
    state = db.get(MailSync, (account.id, folder)) or MailSync(account_id=account.id, folder=folder)
    db.add(state)
    if state.delta_link:
        url, params = state.delta_link, None
    else:
        tpl, params = _start_url(datetime.now(UTC) - timedelta(days=FIRST_SYNC_DAYS))
        url = tpl.format(folder=folder)
    while True:
        try:
            r = graph.call(db, account, "GET", url, params=params,
                           prefer=(f"odata.maxpagesize={PAGE_SIZE}", 'outlook.body-content-type="text"'))
        except graph.GraphError as e:
            if e.status == 410 and state.delta_link:  # 동기화 위치 만료 → 처음부터(이미 있는 메일은 _apply가 건너뛴다)
                log.info("델타 위치 만료 · 처음부터 account=%s folder=%s", account.id, folder)
                state.delta_link = None
                db.commit()
                return _sync_folder(db, account, folder, counts, cache)
            raise
        data = r.json()
        items = data.get("value", [])
        # 빠진 메일의 지금 메일함은 쓰기 전에 먼저 알아낸다 — DB 쓰기 잠금을 쥔 채 Graph를 기다리지 않게
        moved = {}
        for item in items:
            if "@removed" in item and (m := _find(db, account, item["id"])) is not None and m.folder == folder:
                moved[item["id"]] = _where_now(db, account, item["id"], cache)
        for item in items:
            _apply(db, account, folder, item, counts, moved)
        if next_link := data.get("@odata.nextLink"):
            url, params = next_link, None
            db.commit()  # 쪽마다 커밋: 긴 첫 동기화가 중간에 끊겨도 받은 만큼은 남긴다(다시 받으면 건너뛴다)
            continue
        state.delta_link = data.get("@odata.deltaLink")
        db.commit()
        return None


def sync_account(db: Session, account: Account) -> dict:
    """한 계정 동기화. 실패는 GraphError로 올린다(GraphAuthError면 다시 연결해야 한다).
    계정 잠금 안에서 돈다 — 틱 · [지금 받기] · 첫 동기화 · 보내기 기록 · 연결 끊기가 겹쳐 같은 메일을 두 번 넣지 않게."""
    counts = {"added": 0, "updated": 0, "removed": 0}
    cache: dict = {}  # 메일함 이름 → id(이번 동기화 동안만)
    with graph.account_lock(account.id):
        db.refresh(account)  # 기다리는 동안 연결이 끊겼을 수 있다
        if account.refresh_token_enc is None:
            raise graph.GraphAuthError(401, "not_connected")
        for folder in FOLDERS:
            _sync_folder(db, account, folder, counts, cache)
        account.last_synced_at = real_now()
        db.commit()
    return counts


def sync_all(db: Session) -> None:
    """스케줄러 틱(jobs/scheduler.py). 연결된 Outlook 계정마다 한 번. 한 계정이 실패해도 다음 계정은 한다."""
    accounts = db.scalars(select(Account).where(Account.provider == "outlook_graph",
                                                Account.refresh_token_enc.is_not(None))).all()
    for account in accounts:
        try:
            counts = sync_account(db, account)
            if counts["added"]:
                log.info("Outlook 동기화 account=%s 새 메일 %d", account.id, counts["added"])
        except graph.GraphAuthError:
            db.rollback()
            log.warning("Outlook 다시 연결 필요 account=%s", account.id)
        except graph.GraphError as e:
            db.rollback()
            log.warning("Outlook 동기화 실패 account=%s status=%s", account.id, e.status)
        except Exception:  # noqa: BLE001 - DB 오류 등. 이 계정만 건너뛰고 다음 계정은 한다
            db.rollback()
            log.exception("Outlook 동기화 오류 account=%s", account.id)
