"""메일 보내기 한 곳 (BE-5 답장 · BE-7 Outlook · T14 재촉). 사용자가 확인한 발송만 부른다(D37 · D48).

- dummy(시연) 계정: 실제로 보내지 않고 보낸 메일(direction=sent)로 같은 대화에 기록한다.
- outlook_graph 계정: Graph로 초안을 만들고(createReply · createReplyAll · createForward · POST /me/messages) 바로 보낸다(/send).
  보내기 응답(202)에는 id가 없어서 초안을 거친다 — 초안 id(바뀌지 않는 id)가 보낸 편지함에서도 같아,
  그 id로 보낸 메일을 저장하면 동기화(app/mail/graph_sync.py)가 같은 메일을 두 번 넣지 않는다.
  보내기가 확실히 거절되면(4xx) 만든 초안을 지운다. 응답이 없거나 5xx면 실제로 나갔을 수 있어 지우지 않는다(SendUnknown).
- 본문은 저장하지 않는다(구조도 10절). 글은 로그에 남기지 않는다.
"""
import html
import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Mail

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
                category: str, at: datetime, source_id: str | None = None, cc: list[str] | None = None) -> Mail:
    """보낸 메일 한 통을 남긴다. category: 답장은 '기타'(요청 아님), 재촉 · 새 메일은 '요청'(응답 대기를 다시 센다).
    같은 원본 id가 이미 있으면(보낸 편지함 동기화가 먼저 넣음) 그 행에 분류 · 대화만 맞춘다."""
    if source_id and (old := db.scalar(select(Mail).where(Mail.account_id == account.id, Mail.source_id == source_id))):
        old.category, old.conversation_id = category, conversation_id or old.conversation_id
        return old
    sent = Mail(account_id=account.id, source_id=source_id or f"sent-{uuid.uuid4().hex}", direction="sent",
                sender=account.email, recipients=list(recipients), cc=list(cc or []) or None, subject=subject, sent_at=at,
                conversation_id=conversation_id, category=category, folder="sentitems" if source_id else None, read_at=at)
    db.add(sent)
    db.flush()
    return sent


def _recips(addrs: list[str]) -> list[dict]:
    return [{"emailAddress": {"address": a}} for a in addrs]


def _html(text: str) -> str:
    """보이는 그대로(줄바꿈 포함) 보내려고 HTML로 바꾼다. 받는 사람 프로그램이 글을 태그로 읽지 않게 이스케이프한다."""
    return html.escape(text).replace("\n", "<br>")


def send_graph(db: Session, account: Account, kind: Kind, *, content: str, source_id: str | None = None,
               to: list[str] | None = None, cc: list[str] | None = None, bcc: list[str] | None = None,
               subject: str | None = None, attachments: list[dict] | None = None) -> dict:
    """Outlook으로 보낸다. 돌려주는 값은 보낸 메일(초안) — id · conversationId · subject · toRecipients.
    attachments: [{name, content_type, content_b64}] — 3MB 미만 파일 첨부(POST .../attachments). 큰 첨부(업로드 세션)는 단계 2 뒤."""
    from app.mail import graph

    if kind == "new":
        payload = {"subject": subject or "", "body": {"contentType": "HTML", "content": _html(content)},
                   "toRecipients": _recips(to or []), "ccRecipients": _recips(cc or []), "bccRecipients": _recips(bcc or [])}
        draft = graph.call(db, account, "POST", "/me/messages", json=payload).json()
    else:
        payload: dict = {"comment": _html(content)}
        if to and kind == "forward":  # 전달 받는 사람(꼭 있어야 한다). createForward는 toRecipients를 받는다
            payload["toRecipients"] = _recips(to)
        draft = graph.call(db, account, "POST", f"/me/messages/{source_id}/{_CREATE[kind]}", json=payload).json()
        # 답장 · 전체 답장은 Outlook이 원 메일에서 받는 사람을 채운다. to를 주면(재촉: 내가 보낸 메일에 전체 답장) 초안을 고쳐 바꾼다
        # 이때 참조 · 숨은 참조도 비운다 — createReplyAll이 원 메일의 참조를 채워, 미리보기에서 확인하지 않은 사람에게 나가지 않게
        patch = {"toRecipients": _recips(to), "ccRecipients": [], "bccRecipients": []} if to and kind != "forward" else {}
        if cc or bcc:
            patch |= {"ccRecipients": _recips(cc or []), "bccRecipients": _recips(bcc or [])}
        if patch:
            try:
                patched = graph.call(db, account, "PATCH", f"/me/messages/{draft['id']}", json=patch).json()
            except graph.GraphError:
                _drop_draft(db, account, draft["id"])  # 아직 보내기 전 — 초안을 남기지 않는다
                raise
            draft = {**draft, **{k: patched.get(k, v) for k, v in patch.items()}}  # 기록할 받는 사람 · 참조는 바꾼 뒤 값
    for a in attachments or []:
        try:
            graph.call(db, account, "POST", f"/me/messages/{draft['id']}/attachments",
                       json={"@odata.type": "#microsoft.graph.fileAttachment", "name": a["name"],
                             "contentType": a["content_type"], "contentBytes": a["content_b64"]})
        except graph.GraphError:
            _drop_draft(db, account, draft["id"])  # 아직 보내지 않았다 — 첨부가 빠진 메일이 나가지 않게 초안을 지운다
            raise
    try:
        graph.call(db, account, "POST", f"/me/messages/{draft['id']}/send")
    except graph.GraphError as e:
        if e.status >= 500 or e.status == 408:
            raise SendUnknown() from e  # 나갔을 수 있다 — 초안을 지우지 않는다(나갔다면 이미 보낸 편지함에 있다)
        _drop_draft(db, account, draft["id"])
        raise
    return draft


def _drop_draft(db: Session, account: Account, draft_id: str) -> None:
    from app.mail import graph

    try:
        graph.call(db, account, "DELETE", f"/me/messages/{draft_id}")
    except graph.GraphError:
        pass  # 초안이 남아도 보낸 것은 아니다. 원래 실패를 부른 쪽이 올린다


def draft_recipients(draft: dict, key: str = "toRecipients") -> list[str]:
    return [a for a in (((r or {}).get("emailAddress") or {}).get("address") for r in draft.get(key) or []) if a]
