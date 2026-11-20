"""메일 한 통 보기 (GET /api/mails/{id}, #55 리뷰 — 대시보드에서 업무를 눌러 메일 본문으로 가는 장면) ·
읽음 · 고정 (PATCH /api/mails/{id}, FE-5d) · 메일함 옮기기 (POST /api/mails/{id}/move, BE-7) ·
보관 · 지운 메일 목록 (GET /api/mails/hidden, BE-7) · Outlook 검색 (GET /api/mails/search, BE-7) ·
첨부 목록 · 내려받기 (GET /api/mails/{id}/attachments[/{att_id}], BE-7).

- 본문은 DB에 저장하지 않으므로(구조도 10절) 요청 때 원본에서 가져온다(app/mail/body.py, 더미 계정은 더미 메일 파일).
- 다른 사용자의 메일 · 없는 메일은 404. 원본에서 본문을 가져오지 못하면 503(빈 본문을 보여 주지 않는다).
- 이 메일의 업무를 상태와 상관없이 모두 함께 준다(화면이 근거 문장을 본문에 칠한다).
- 읽음 · 옮기기는 Outlook 계정이면 Graph에 먼저 쓰고(실패하면 우리 DB도 바꾸지 않는다), 더미 계정은 우리 DB에만 쓴다.
  고정은 우리 앱만의 표시라 Outlook에 쓰지 않는다. 삭제는 지운 편지함으로 옮기기(deleteditems)다 — 영구 삭제는 하지 않는다.
"""
import threading
from collections import OrderedDict
from typing import Literal
from urllib.parse import quote

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dashboard import mail_view
from app.core.clock import as_kst, now
from app.core.db import get_db
from app.core.user import Id, current_user_id
from app.mail.body import fetch_body, fetch_html
from app.services.html_clean import clean_html
from app.models import Account, Mail, Task
from app.models.mail import HIDDEN_FOLDERS
from app.schemas.dashboard import DashboardMail
from app.schemas.mail_detail import MailDetail, MailDetailTask

router = APIRouter(prefix="/api")


Folder = Literal["inbox", "archive", "deleteditems"]


class MailPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    read: bool | None = None  # 참 = 읽음(이미 읽었으면 시각 그대로), 거짓 = 안 읽음
    pinned: bool | None = None  # 참 = 목록 맨 위 고정, 거짓 = 해제


class MoveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    folder: Folder


def _own(db: Session, mail_id: int, user_id: int) -> tuple[Mail, Account]:
    row = db.execute(select(Mail, Account).join(Account, Mail.account_id == Account.id)
                     .where(Mail.id == mail_id, Account.user_id == user_id)).first()
    if row is None:
        raise HTTPException(404, "없는 메일입니다")
    return row[0], row[1]


def _graph_write(db: Session, account: Account, method: str, path: str, json: dict) -> bool:
    """Outlook에 썼으면 True. 더미 계정 · 연결이 끊긴 Outlook 계정이면 False — 우리 앱에서만 바꾼다(11-19 사용자 결정:
    끊긴 계정 메일도 치울 수 있게). Outlook이 거절하면 502(우리 DB도 바꾸지 않는다)."""
    if account.provider != "outlook_graph" or account.refresh_token_enc is None:
        return False
    from app.mail import graph

    try:
        graph.call(db, account, method, path, json=json)
    except graph.GraphAuthError:
        return False  # 갱신 토큰 만료 · 동의 취소 = 끊긴 것과 같다
    except graph.GraphError as e:
        raise HTTPException(502, f"Outlook이 바꾸기를 거절했습니다({e.status})") from None
    return True


@router.patch("/mails/{mail_id}", response_model=DashboardMail)
def patch_mail(mail_id: Id, body: MailPatch, user_id: int = Depends(current_user_id),
               db: Session = Depends(get_db)) -> DashboardMail:
    mail, account = _own(db, mail_id, user_id)
    if body.read is not None and body.read != (mail.read_at is not None):
        _graph_write(db, account, "PATCH", f"/me/messages/{mail.source_id}", {"isRead": body.read})
        mail.read_at = now() if body.read else None
    if body.pinned is not None and body.pinned != (mail.pinned_at is not None):
        mail.pinned_at = now() if body.pinned else None
    db.commit()
    return mail_view(mail, account.email)


@router.post("/mails/{mail_id}/move", response_model=DashboardMail)
def move_mail(mail_id: Id, body: MoveRequest, user_id: int = Depends(current_user_id),
              db: Session = Depends(get_db)) -> DashboardMail:
    """메일함 옮기기: 받은 편지함 · 보관 · 지운 편지함. 바뀌지 않는 id라 옮겨도 source_id가 그대로다(app/mail/graph.py).
    Outlook에 쓰지 못하는 계정(연결 끊김)은 메일함은 그대로 두고 우리 앱에서만 숨긴다(hidden_at) — 다시 연결해 동기화해도
    숨긴 채로 남는다. 받은 편지함으로 옮기면 숨김도 푼다."""
    mail, account = _own(db, mail_id, user_id)
    if mail.direction != "received":
        raise HTTPException(422, "받은 메일만 옮길 수 있습니다")
    if body.folder == "inbox":
        mail.hidden_at = None
    if mail.folder != body.folder:
        wrote = _graph_write(db, account, "POST", f"/me/messages/{mail.source_id}/move", {"destinationId": body.folder})
        if wrote or account.provider != "outlook_graph" or body.folder == "inbox":
            mail.folder = body.folder  # 끊긴 계정에서 받은 편지함으로 되돌리기도 우리 앱에서 보이게(Outlook에서는 그대로)
        else:
            mail.hidden_at = mail.hidden_at or now()
    db.commit()
    return mail_view(mail, account.email)


@router.get("/mails/hidden", response_model=list[DashboardMail])  # /mails/{mail_id}보다 먼저 둔다(경로가 겹친다)
def hidden_mails(user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> list[DashboardMail]:
    """보관함 · 지운 편지함 보기(BE-7): 대시보드가 빼는 내 받은 메일, 최근 받은 순. 받은 편지함으로 되돌리는 길(move)을 화면에 두려고.
    우리 앱에서만 숨긴 메일(hidden_at, 연결 끊긴 계정)도 넣는다 — 메일함 칸은 그대로라 folder가 inbox 등으로 온다."""
    rows = db.execute(select(Mail, Account.email).join(Account, Mail.account_id == Account.id)
                      .where(Account.user_id == user_id, Mail.direction == "received",
                             Mail.folder.in_(HIDDEN_FOLDERS) | Mail.hidden_at.is_not(None))
                      .order_by(Mail.sent_at.desc(), Mail.id.desc())).all()
    return [mail_view(m, email) for m, email in rows]


class SearchHit(BaseModel):
    """Outlook 검색 결과 한 통. mail_id가 있으면 우리 앱에 받아 둔 메일(그 메일을 연다), 없으면 web_link로 Outlook에서 연다."""
    mail_id: int | None
    subject: str
    sender: str
    received_at: datetime | None
    web_link: str | None


SEARCH_TOP = 25


@router.get("/mails/search", response_model=list[SearchHit])  # /mails/{mail_id}보다 먼저
def search_outlook(q: str = Query(min_length=2, max_length=100), user_id: int = Depends(current_user_id),
                   db: Session = Depends(get_db)) -> list[SearchHit]:
    """연결된 Outlook 사서함 전체에서 찾는다(Graph $search — 제목 · 본문 · 보낸 사람 등, 최근 순 최대 SEARCH_TOP통).
    받아 둔 메일 안 검색은 화면이 한다. Outlook 계정이 없으면 빈 목록, Graph가 실패한 계정은 빼고 준다.
    https://learn.microsoft.com/en-us/graph/search-query-parameter — $search 값은 큰따옴표로 감싸고 안의 큰따옴표는 뺀다."""
    from app.core.clock import to_kst_naive
    from app.mail import graph

    term = q.replace('"', " ").replace("\\", " ").strip()
    accounts = db.scalars(select(Account).where(Account.user_id == user_id, Account.provider == "outlook_graph",
                                                Account.refresh_token_enc.is_not(None))).all()
    out: list[SearchHit] = []
    for account in accounts:
        try:
            data = graph.call(db, account, "GET", "/me/messages", params={
                "$search": f'"{term}"', "$top": str(SEARCH_TOP), "$select": "id,subject,from,receivedDateTime,webLink,conversationId"}).json()
        except graph.GraphError:
            db.rollback()
            continue
        # $search는 Prefer IdType=ImmutableId를 따르지 않고 보통 id를 돌려준다(11-19 실제 계정 확인) → id 대신 (대화 id, 제목)으로
        # 받아 둔 메일을 찾는다. ponytail: 한 대화에 같은 제목이 여럿이면 첫 메일로 간다. 정확히 하려면 translateExchangeIds
        convs = {m.get("conversationId") for m in data.get("value", []) if m.get("conversationId")}
        known: dict[tuple[str, str], int] = {}
        for cid, subject, mid in db.execute(select(Mail.conversation_id, Mail.subject, Mail.id).where(
                Mail.account_id == account.id, Mail.conversation_id.in_(convs)).order_by(Mail.id)).all() if convs else []:
            known.setdefault((cid, subject), mid)
        for m in data.get("value", []):
            raw = m.get("receivedDateTime")
            out.append(SearchHit(mail_id=known.get((m.get("conversationId"), m.get("subject") or "")), subject=m.get("subject") or "(제목 없음)",
                                 sender=((m.get("from") or {}).get("emailAddress") or {}).get("address") or "",
                                 received_at=as_kst(to_kst_naive(datetime.fromisoformat(raw))) if raw else None,
                                 web_link=m.get("webLink")))
    out.sort(key=lambda h: h.received_at.timestamp() if h.received_at else 0, reverse=True)  # 여러 계정을 섞어 최근 순
    return out


class AttachmentView(BaseModel):
    id: str
    name: str
    content_type: str | None
    size: int


def _outlook_mail(db: Session, mail_id: int, user_id: int) -> tuple[Mail, Account]:
    mail, account = _own(db, mail_id, user_id)
    if account.provider != "outlook_graph" or account.refresh_token_enc is None:
        raise HTTPException(501, "첨부는 연결된 Outlook 메일만 볼 수 있습니다")
    return mail, account


@router.get("/mails/{mail_id}/attachments", response_model=list[AttachmentView])
def list_attachments(mail_id: Id, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> list[AttachmentView]:
    """첨부 목록(본문에 박힌 그림은 뺀다). 파일은 저장하지 않고 내려받을 때 Graph에서 가져온다(구조도 10절)."""
    from app.mail import graph

    mail, account = _outlook_mail(db, mail_id, user_id)
    try:
        data = graph.call(db, account, "GET", f"/me/messages/{mail.source_id}/attachments",
                          params={"$select": "id,name,contentType,size,isInline"}).json()
    except graph.GraphError:
        db.rollback()
        raise HTTPException(503, "Outlook에서 첨부를 가져오지 못했습니다") from None
    return [AttachmentView(id=a["id"], name=a.get("name") or "첨부", content_type=a.get("contentType"), size=a.get("size") or 0)
            for a in data.get("value", []) if not a.get("isInline")]


INLINE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"}
# 메일마다 본문 그림 contentId → (첨부 id, 형식). contentId는 fileAttachment에만 있어 목록에서 고를 수 없다 → 처음 한 번 후보를
# 모두 열어 짝을 만들고 기억한다(그림 N장이면 N + N번, 예전처럼 그림마다 다시 훑으면 N²). 그림 바이트는 기억하지 않는다(구조도 10절)
# ponytail: 프로세스 메모리 · 전역 잠금, 최근 INLINE_CACHE_MAX통만. 여러 프로세스면 각자 한 번씩 만든다
_inline_ids: OrderedDict[int, dict[str, tuple[str, str]]] = OrderedDict()
_inline_lock = threading.Lock()
INLINE_CACHE_MAX = 200


def _image(data: bytes, ctype: str) -> Response:
    return Response(data, media_type=ctype, headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})


@router.get("/mails/{mail_id}/inline/{content_id}")
def inline_image(mail_id: Id, content_id: str, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> Response:
    """본문에 박힌 그림(cid, 붙여넣은 캡처 등) 한 장(AI-42). 그림 형식만 그 형식으로 돌려준다(HTML 등은 우리 출처에서 열지 않는다)."""
    import base64

    from app.mail import graph

    mail, account = _outlook_mail(db, mail_id, user_id)
    base = f"/me/messages/{mail.source_id}/attachments"
    try:
        with _inline_lock:  # 한 메일의 그림 여러 장이 동시에 와도 짝 만들기는 한 번
            if (ids := _inline_ids.get(mail.id)) is not None:
                _inline_ids.move_to_end(mail.id)
            else:
                ids, found = {}, None
                for a in graph.call(db, account, "GET", base, params={"$select": "id,contentType,isInline"}).json().get("value", []):
                    ctype = (a.get("contentType") or "").lower()
                    if not a.get("isInline") or ctype not in INLINE_TYPES:
                        continue
                    full = graph.call(db, account, "GET", f"{base}/{quote(a['id'], safe='')}").json()
                    if cid := full.get("contentId"):
                        ids[cid] = (a["id"], ctype)
                        if cid == content_id and full.get("contentBytes"):
                            found = _image(base64.b64decode(full["contentBytes"]), ctype)
                _inline_ids[mail.id] = ids
                while len(_inline_ids) > INLINE_CACHE_MAX:
                    _inline_ids.popitem(last=False)
                if found is not None:
                    return found
        if (hit := ids.get(content_id)) is None:
            raise HTTPException(404, "그림을 찾을 수 없습니다")
        full = graph.call(db, account, "GET", f"{base}/{quote(hit[0], safe='')}").json()
        if not full.get("contentBytes"):
            raise HTTPException(404, "그림을 찾을 수 없습니다")
        return _image(base64.b64decode(full["contentBytes"]), hit[1])
    except graph.GraphError:
        db.rollback()
        raise HTTPException(503, "Outlook에서 그림을 가져오지 못했습니다") from None


@router.get("/mails/{mail_id}/attachments/{att_id}")
def download_attachment(mail_id: Id, att_id: str, view: bool = False, user_id: int = Depends(current_user_id),
                        db: Session = Depends(get_db)) -> Response:
    """첨부 한 개 내려받기(Graph .../attachments/{id}/$value 원본 바이트). 파일 이름은 attachment로 붙여 브라우저가 저장하게.
    view=1: 그림 첨부를 화면에 미리 보인다(AI-42, 아웃룩 첨부 카드처럼). 그림 형식만 그 형식으로, 나머지는 415."""

    from app.mail import graph

    mail, account = _outlook_mail(db, mail_id, user_id)
    try:
        meta = graph.call(db, account, "GET", f"/me/messages/{mail.source_id}/attachments/{quote(att_id, safe='')}",
                          params={"$select": "name,contentType"}).json()
        raw = graph.call(db, account, "GET", f"/me/messages/{mail.source_id}/attachments/{quote(att_id, safe='')}/$value")
    except graph.GraphError as e:
        db.rollback()
        raise HTTPException(404 if e.status == 404 else 503, "첨부를 가져오지 못했습니다") from None
    name = meta.get("name") or "attachment"
    if view:
        ctype = (meta.get("contentType") or "").lower()
        if ctype not in INLINE_TYPES:
            raise HTTPException(415, "그림 첨부만 미리 볼 수 있습니다")
        return Response(raw.content, media_type=ctype,
                        headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"})
    return Response(raw.content, media_type="application/octet-stream",  # 받은 contentType을 그대로 쓰지 않는다(HTML 등을 우리 출처에서 열지 않게)
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}",
                             "X-Content-Type-Options": "nosniff"})


@router.get("/mails/{mail_id}", response_model=MailDetail)
def get_mail(mail_id: Id, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> MailDetail:
    mail, _ = _own(db, mail_id, user_id)
    body = fetch_body(db, mail)
    if body is None:
        raise HTTPException(503, "메일 원본에서 본문을 가져오지 못했습니다")
    # ponytail: 글 · HTML을 따로 두 번 부른다(근거 형광펜 · 분류는 글 기준). 느리면 HTML 한 번에서 글을 뽑는다
    raw_html = fetch_html(db, mail)
    body_html = clean_html(raw_html, cid=lambda c: f"/api/mails/{mail.id}/inline/{quote(c, safe='')}") if raw_html else None
    tasks = db.scalars(select(Task).where(Task.mail_id == mail.id).order_by(Task.id)).all()
    return MailDetail(
        id=mail.id, source_id=mail.source_id, direction=mail.direction, sender=mail.sender, subject=mail.subject,
        received_at=as_kst(mail.sent_at), category=mail.category, lane=mail.lane,
        to=list(mail.recipients or []), cc=list(mail.cc or []), body=body, body_html=body_html,
        tasks=[MailDetailTask(id=t.id, mail_id=t.mail_id, text=t.text, due_at=as_kst(t.due_at), due_raw=t.due_raw,
                              due_source=t.due_source, status=t.status, seen_at=as_kst(t.seen_at),
                              evidence_text=t.evidence_text) for t in tasks],
        summary=mail.summary,
    )
