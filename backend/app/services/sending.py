"""메일 보내기 한 곳 (BE-5 답장 · BE-7 Outlook · T14 재촉). 사용자가 확인한 발송만 부른다(D37 · D48).

- dummy(시연) 계정: 실제로 보내지 않고 보낸 메일(direction=sent)로 같은 대화에 기록한다.
- outlook_graph 계정: Graph로 초안을 만들고(createReply · createReplyAll · createForward · POST /me/messages) 바로 보낸다(/send).
  보내기 응답(202)에는 id가 없어서 초안을 거친다 — 초안 id(바뀌지 않는 id)가 보낸 편지함에서도 같아,
  그 id로 보낸 메일을 저장하면 동기화(app/mail/graph_sync.py)가 같은 메일을 두 번 넣지 않는다.
  보내기가 확실히 거절되면(4xx) 만든 초안을 지운다. 응답이 없거나 5xx면 실제로 나갔을 수 있어 지우지 않는다(SendUnknown).
- 본문은 저장하지 않는다(구조도 10절). 글은 로그에 남기지 않는다.
"""
import html
import re
import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Mail
from app.services.html_clean import clean_html

SENDABLE = ("dummy", "outlook_graph")
CANNOT_SEND = "이 계정은 서비스 안에서 보낼 수 없습니다"
Kind = Literal["reply", "replyAll", "forward", "new"]
_CREATE = {"reply": "createReply", "replyAll": "createReplyAll", "forward": "createForward"}


def can_send(account: Account) -> bool:
    if account.provider == "outlook_graph":
        return account.refresh_token_enc is not None  # 연결을 끊은 계정은 보낼 수 없다
    return account.provider in SENDABLE


class SendUnknown(Exception):
    """보내기 요청에 답이 없거나 서버 오류(5xx)였다. 실제로 나갔는지 모른다 — 다시 보내라고 하지 않고 보낸 편지함을 보라고 한다."""


def record_sent(db: Session, account: Account, *, recipients: list[str], subject: str, conversation_id: str | None,
                category: str, at: datetime, source_id: str | None = None, cc: list[str] | None = None,
                importance: str | None = None) -> Mail:
    """보낸 메일 한 통을 남긴다. category: 답장은 '기타'(요청 아님), 재촉 · 새 메일은 '요청'(응답 대기를 다시 센다).
    같은 원본 id가 이미 있으면(보낸 편지함 동기화가 먼저 넣음) 그 행에 분류 · 대화만 맞춘다."""
    if source_id and (old := db.scalar(select(Mail).where(Mail.account_id == account.id, Mail.source_id == source_id))):
        old.category, old.conversation_id = category, conversation_id or old.conversation_id
        old.importance = importance or old.importance
        return old
    sent = Mail(account_id=account.id, source_id=source_id or f"sent-{uuid.uuid4().hex}", direction="sent",
                sender=account.email, recipients=list(recipients), cc=list(cc or []) or None, subject=subject, sent_at=at,
                conversation_id=conversation_id, category=category, folder="sentitems" if source_id else None, read_at=at,
                importance=importance)
    db.add(sent)
    db.flush()
    return sent


def _recips(addrs: list[str]) -> list[dict]:
    return [{"emailAddress": {"address": a}} for a in addrs]


def _html(text: str) -> str:
    """보이는 그대로(줄바꿈 포함) 보내려고 HTML로 바꾼다. 받는 사람 프로그램이 글을 태그로 읽지 않게 이스케이프한다."""
    return html.escape(text).replace("\n", "<br>")


# 편집기에 넣은 · 붙여넣은 그림(data: 주소). 보낼 때 메일 안 첨부(cid)로 바꾼다(AI-39)
_DATA_IMG = re.compile(r"""(<img\b[^>]*?\bsrc\s*=\s*)(["'])data:(image/(?:png|jpeg|gif|webp));base64,([A-Za-z0-9+/=\s]+)\2""", re.I)


def inline_images(body: str) -> tuple[str, list[dict]]:
    """본문의 data: 그림을 'cid:' 주소로 바꾸고 붙일 첨부 목록을 준다 — Graph 인라인 첨부(isInline · contentId).
    아웃룩도 본문 그림을 이렇게 보낸다(받는 쪽은 cid로 본문 안에 그린다)."""
    found: list[dict] = []

    def sub(m: re.Match) -> str:
        n = len(found) + 1
        cid = f"image{n}.{uuid.uuid4().hex[:12]}@cne"
        ext = m[3].split("/")[1].replace("jpeg", "jpg")
        found.append({"name": f"image{n}.{ext}", "content_type": m[3].lower(), "content_b64": re.sub(r"\s", "", m[4]),
                      "content_id": cid})
        return f"{m[1]}{m[2]}cid:{cid}{m[2]}"

    return _DATA_IMG.sub(sub, body), found


def send_graph(db: Session, account: Account, kind: Kind, *, content: str, source_id: str | None = None,
               to: list[str] | None = None, cc: list[str] | None = None, bcc: list[str] | None = None,
               subject: str | None = None, attachments: list[dict] | None = None, content_html: str | None = None,
               importance: str = "normal", large: list[tuple] | None = None,
               read_receipt: bool = False, delivery_receipt: bool = False) -> dict:
    """Outlook으로 보낸다. 돌려주는 값은 보낸 메일(초안) — id · conversationId · subject · toRecipients.
    attachments: [{name, content_type, content_b64}] — 3MB 미만 파일 첨부(POST .../attachments).
    large: [(경로, {name, content_type, size})] — 3~150MB 첨부. 초안에 업로드 세션을 만들어 나눠 올린다(AI-32).
    content_html: 서식 있는 편집기의 HTML(거른 뒤 그대로 보낸다, AI-32). 없으면 글을 HTML로 바꿔 보낸다.
    importance: low · normal · high(Graph message.importance, 아웃룩 중요도 높음 · 낮음).
    read_receipt · delivery_receipt: 읽음 · 배달 확인 요청(Graph isReadReceiptRequested · isDeliveryReceiptRequested, AI-38).
    기본값이면 칸을 보내지 않는다."""
    from app.mail import graph

    options = {k: v for k, v in (("importance", importance), ("isReadReceiptRequested", read_receipt),
                                 ("isDeliveryReceiptRequested", delivery_receipt)) if v not in ("normal", False)}

    inline: list[dict] = []
    if content_html:
        content_html, inline = inline_images(content_html)
        ids = {a["content_id"] for a in inline}
        body_html = clean_html(content_html, cid=lambda c: f"cid:{c}" if c in ids else "")
    else:
        body_html = _html(content)
    if kind == "new":
        payload = {"subject": subject or "", "body": {"contentType": "HTML", "content": body_html},
                   "toRecipients": _recips(to or []), "ccRecipients": _recips(cc or []), "bccRecipients": _recips(bcc or [])}
        payload |= options
        draft = graph.call(db, account, "POST", "/me/messages", json=payload).json()
    else:
        payload: dict = {"comment": body_html}
        if to and kind == "forward":  # 전달 받는 사람(꼭 있어야 한다). createForward는 toRecipients를 받는다
            payload["toRecipients"] = _recips(to)
        draft = graph.call(db, account, "POST", f"/me/messages/{source_id}/{_CREATE[kind]}", json=payload).json()
        # 답장 · 전체 답장은 Outlook이 원 메일에서 받는 사람을 채운다. to를 주면(재촉: 내가 보낸 메일에 전체 답장) 초안을 고쳐 바꾼다
        # 이때 참조 · 숨은 참조도 비운다 — createReplyAll이 원 메일의 참조를 채워, 미리보기에서 확인하지 않은 사람에게 나가지 않게
        patch = {"toRecipients": _recips(to), "ccRecipients": [], "bccRecipients": []} if to and kind != "forward" else {}
        if cc or bcc or kind == "replyAll":  # 전체 답장은 Outlook이 원 참조를 채운다 — 빈 참조도 그대로 맞춘다
            patch |= {"ccRecipients": _recips(cc or []), "bccRecipients": _recips(bcc or [])}
        patch |= options
        if patch:
            try:
                patched = graph.call(db, account, "PATCH", f"/me/messages/{draft['id']}", json=patch).json()
            except graph.GraphError:
                _drop_draft(db, account, draft["id"])  # 아직 보내기 전 — 초안을 남기지 않는다
                raise
            draft = {**draft, **{k: patched.get(k, v) for k, v in patch.items()}}  # 기록할 받는 사람 · 참조는 바꾼 뒤 값
    for a in [*(attachments or []), *inline]:
        item = {"@odata.type": "#microsoft.graph.fileAttachment", "name": a["name"], "contentType": a["content_type"],
                "contentBytes": a["content_b64"]}
        if a.get("content_id"):  # 본문 그림(AI-39): 첨부 목록에 따로 보이지 않고 본문 cid 자리에 그려진다
            item |= {"isInline": True, "contentId": a["content_id"]}
        try:
            graph.call(db, account, "POST", f"/me/messages/{draft['id']}/attachments", json=item)
        except graph.GraphError:
            _drop_draft(db, account, draft["id"])  # 아직 보내지 않았다 — 첨부가 빠진 메일이 나가지 않게 초안을 지운다
            raise
    for path, meta in large or []:
        try:
            session = graph.call(db, account, "POST", f"/me/messages/{draft['id']}/attachments/createUploadSession",
                                 json={"AttachmentItem": {"attachmentType": "file", "name": meta["name"], "size": meta["size"],
                                                          "contentType": meta["content_type"]}}).json()
            graph.upload_file(session["uploadUrl"], path, meta["size"])
        except (graph.GraphError, KeyError, OSError) as e:
            _drop_draft(db, account, draft["id"])  # 첨부가 빠진 메일이 나가지 않게
            if isinstance(e, graph.GraphError):
                raise
            if isinstance(e, OSError):  # 보내는 사이 [빼기] · 정리로 올린 파일이 지워졌다
                raise AttachmentMissing() from e
            raise graph.GraphError(502, "upload_session") from None
    try:
        graph.call(db, account, "POST", f"/me/messages/{draft['id']}/send")
    except graph.GraphError as e:
        if e.status >= 500 or e.status == 408:
            raise SendUnknown() from e  # 나갔을 수 있다 — 초안을 지우지 않는다(나갔다면 이미 보낸 편지함에 있다)
        _drop_draft(db, account, draft["id"])
        raise
    return draft


class AttachmentMissing(Exception):
    """올려 둔 큰 첨부 파일이 보내는 사이 없어졌다. 초안은 지웠고 보내지 않았다."""


def _drop_draft(db: Session, account: Account, draft_id: str) -> None:
    from app.mail import graph

    try:
        graph.call(db, account, "DELETE", f"/me/messages/{draft_id}")
    except graph.GraphError:
        pass  # 초안이 남아도 보낸 것은 아니다. 원래 실패를 부른 쪽이 올린다


def draft_recipients(draft: dict, key: str = "toRecipients") -> list[str]:
    return [a for a in (((r or {}).get("emailAddress") or {}).get("address") for r in draft.get(key) or []) if a]
