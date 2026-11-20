"""메일 보내기 API (BE-5 · BE-7 · D48 (가) · 기획 detail 4.4절).

- `POST /api/mails/{id}/reply` 답장 · `POST /api/mails/{id}/reply-all` 전체 답장 · `POST /api/mails/{id}/forward` 전달 ·
  `POST /api/mails` 새 메일.
- 보내기는 사용자가 [보내기]를 누를 때만(자동 발송 없음, D37 · D48). 답장 뒤 '완료로 처리할까요?' 시트는 화면이 한다.
- 메일 원본별: dummy(시연) 계정은 실제로 보내지 않고 보낸 메일로만 기록한다. Outlook(`outlook_graph`)은 Graph로 보낸다
  (services/sending.send_graph). 연결이 끊겼으면 409(다시 연결), Graph 실패는 502 — 화면은 보내지 못했다고 알린다.
- 응답은 셋으로 나눈다: 보내기 전 실패(409 · 422 · 502 · 503) / 보냈는지 모름(504) / 보냈는데 기록만 실패(200, recorded=false —
  다시 보내라고 하지 않는다. 다음 동기화가 보낸 편지함에서 넣는다).
- 동기화가 계정 잠금을 오래 쥐면 SEND_LOCK_WAIT초까지만 기다리고 보내지 않은 채 503 — 화면 제한 시간(140초)이 지난 뒤 늦게 나가지 않게.
- 답장 · 전체 답장은 그 메일의 미처리 업무마다 '그대로 두기(keep)'를 남겨 (나) 답장 감지 알림으로 다시 묻지 않는다(D48).
  전달 · 새 메일은 이 메일에 대한 답이 아니라 남기지 않는다.
- 본문은 저장하지 않는다(구조도 10절). 글은 로그에 남기지 않는다.
"""
import logging
from contextlib import contextmanager
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import as_kst, now
from app.core.db import get_db
from app.core.user import Id, current_user_id
from app.models import Account, Mail, ReminderFeedback, Task
from app.reminders.rules import make_key
from app.services.sending import CANNOT_SEND, Kind, SendUnknown, can_send, draft_recipients, record_sent, send_graph

router = APIRouter(prefix="/api")
log = logging.getLogger(__name__)
SEND_LOCK_WAIT = 60  # 초. 화면 제한 시간(SLOW_REQUEST_TIMEOUT_MS 140초)보다 충분히 짧게


class ReplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account: str | None = None  # 화면이 보여 준 보낸 계정. 받아 두기만 하고 쓰지 않는다 — 보내기는 늘 원 메일을 받은 계정으로
    subject: str = Field(min_length=1, max_length=255)  # Outlook 답장 · 전달은 Outlook이 RE: · FW: 제목을 붙인다(이 값은 기록용)
    content: str = Field(min_length=1, max_length=20000)  # 미리보기에 보인 글자 그대로. 저장하지 않는다
    template_key: str | None = Field(None, max_length=50)
    cc: list[str] = Field(default_factory=list, max_length=50)
    bcc: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("subject", "content", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("cc", "bcc")
    @classmethod
    def _addresses(cls, v: list[str]) -> list[str]:
        return _check_addresses(v)


class ForwardRequest(ReplyRequest):
    to: list[str] = Field(min_length=1, max_length=50)

    @field_validator("to")
    @classmethod
    def _to(cls, v: list[str]) -> list[str]:
        return _check_addresses(v)


class NewMailRequest(ForwardRequest):
    account_id: int | None = Field(None, ge=1)  # 보낼 계정. 비면 보낼 수 있는 내 첫 계정


class SentReply(BaseModel):
    id: int | None  # 보낸 메일(direction = sent). None = 나갔지만 기록하지 못함(recorded=false)
    sent_at: datetime  # +09:00
    recorded: bool = True


class _NotRecorded(Exception):
    """Outlook으로는 나갔는데 앱 기록이 실패했다 — 다시 보내면 두 번 나간다."""


def _check_addresses(v: list[str]) -> list[str]:
    out = []
    for a in v:
        a = a.strip()
        # 꺾쇠 · 따옴표: 화면이 '이름 <주소>'에서 주소만 꺼내 보낸다 — 남아 있으면 형식 오류
        if not a or len(a) > 255 or a.count("@") != 1 or any(c.isspace() or c in '<>"' for c in a) \
                or a.startswith("@") or a.endswith("@"):
            raise ValueError("메일 주소 형식이 아닙니다")
        out.append(a)
    return list(dict.fromkeys(out))


def _send(db: Session, account: Account, kind: Kind, body: ReplyRequest, *, mail: Mail | None, to: list[str]) -> Mail:
    """보내고 보낸 메일을 기록한다. Outlook은 Graph 결과(받는 사람 · 대화)를 기록한다."""
    from app.mail import graph

    if not can_send(account):
        raise HTTPException(501 if account.provider != "outlook_graph" else 409, CANNOT_SEND)
    at = now()
    category = "기타" if kind in ("reply", "replyAll") else "요청"  # 내 답장은 요청이 아니다 — 응답 대기(BE-13)에 넣지 않는다
    if account.provider == "outlook_graph":
        try:
            draft = send_graph(db, account, kind, content=body.content, source_id=mail.source_id if mail else None,
                               to=to if kind in ("forward", "new") else None, cc=body.cc, bcc=body.bcc,
                               subject=body.subject)
        except graph.GraphAuthError:
            db.rollback()
            raise HTTPException(409, "Outlook 연결이 끊겼습니다. 설정에서 다시 연결해 주세요") from None
        except SendUnknown:
            db.rollback()
            raise HTTPException(504, "Outlook이 답하지 않아 보내졌는지 모릅니다. 보낸 편지함을 확인한 뒤 다시 보내 주세요") from None
        except graph.GraphError as e:
            db.rollback()
            raise HTTPException(502, f"Outlook이 보내기를 거절했습니다({e.status})") from None
        try:
            return record_sent(db, account, recipients=draft_recipients(draft) or to,
                               cc=draft_recipients(draft, "ccRecipients") or body.cc,
                               subject=draft.get("subject") or body.subject, at=at, category=category, source_id=draft["id"],
                               conversation_id=draft.get("conversationId") or (mail.conversation_id if mail else None))
        except Exception as e:
            raise _NotRecorded() from e
    conv = mail.conversation_id if mail and kind != "forward" else None
    return record_sent(db, account, recipients=to, cc=body.cc, subject=body.subject, conversation_id=conv,
                       category=category, at=at)


@contextmanager
def _locked(account: Account):
    """보내기 ~ 기록 커밋을 계정 잠금 안에서 — 그사이 보낸 편지함 동기화가 같은 메일을 먼저 넣지 않게(app/mail/graph.py).
    SEND_LOCK_WAIT초 안에 못 얻으면 보내지 않고 503(다시 보내도 안전)."""
    from app.mail import graph

    lock = graph.account_lock(account.id)
    if not lock.acquire(timeout=SEND_LOCK_WAIT):
        raise HTTPException(503, "메일을 받는 중이라 보내지 않았습니다. 잠시 뒤 다시 보내 주세요")
    try:
        yield
    finally:
        lock.release()


def _deliver(db: Session, user_id: int, account: Account, kind: Kind, body: ReplyRequest, *, mail: Mail | None,
             to: list[str]) -> SentReply:
    with _locked(account):
        sent = None
        try:
            sent = _send(db, account, kind, body, mail=mail, to=to)
            if kind in ("reply", "replyAll"):
                _keep_reply_confirm(db, user_id, mail, sent)
            db.commit()
        except HTTPException:
            raise
        except Exception as e:
            if not (isinstance(e, _NotRecorded) or (sent is not None and account.provider == "outlook_graph")):
                raise  # 보내기 전 실패 · 시연 계정(기록이 곧 보내기) → 500, 다시 보내도 된다
            db.rollback()
            log.exception("Outlook으로 보냈지만 기록 실패 account=%s", account.id)
            return SentReply(id=None, sent_at=as_kst(now()), recorded=False)
    return SentReply(id=sent.id, sent_at=as_kst(sent.sent_at))


def _received(db: Session, mail_id: int, user_id: int) -> tuple[Mail, Account]:
    mail = db.get(Mail, mail_id)
    account = db.get(Account, mail.account_id) if mail else None
    if account is None or account.user_id != user_id:
        raise HTTPException(404, "메일을 찾을 수 없습니다")
    return mail, account


def _keep_reply_confirm(db: Session, user_id: int, mail: Mail, sent: Mail) -> None:
    # D48: 화면 시트로 이미 물었다 → 이 답장으로는 알림 센터에서 다시 묻지 않는다. reminders.actions.dismiss를 쓰지 않고
    # 직접 남기는 이유: dismiss는 지금 보이는 항목(_find)만 받는데, 업무 항목이 다른 유형(기한 임박 등)이면 reply_confirm 키를 못 찾는다
    open_ids = db.scalars(select(Task.id).where(Task.mail_id == mail.id, Task.status.in_(("pending", "snoozed")))).all()
    for tid in open_ids:
        db.add(ReminderFeedback(user_id=user_id, key=make_key("reply_confirm", "task", tid), type="reply_confirm",
                                reason="keep", ref_id=sent.id, created_at=sent.sent_at))


@router.post("/mails/{mail_id}/reply", response_model=SentReply)
def send_reply(mail_id: Id, body: ReplyRequest, user_id: int = Depends(current_user_id),
               db: Session = Depends(get_db)) -> SentReply:
    mail, account = _received(db, mail_id, user_id)
    if mail.direction != "received":
        raise HTTPException(422, "받은 메일에만 답장할 수 있습니다")
    return _deliver(db, user_id, account, "reply", body, mail=mail, to=[mail.sender])


@router.post("/mails/{mail_id}/reply-all", response_model=SentReply)
def send_reply_all(mail_id: Id, body: ReplyRequest, user_id: int = Depends(current_user_id),
                   db: Session = Depends(get_db)) -> SentReply:
    mail, account = _received(db, mail_id, user_id)
    if mail.direction != "received":
        raise HTTPException(422, "받은 메일에만 답장할 수 있습니다")
    me = account.email.lower()
    to = [a for a in dict.fromkeys([mail.sender, *(mail.recipients or [])]) if a.lower() != me]
    cc = [a for a in (mail.cc or []) if a.lower() != me and a not in to]
    body = body.model_copy(update={"cc": body.cc or cc})
    return _deliver(db, user_id, account, "replyAll", body, mail=mail, to=to)


@router.post("/mails/{mail_id}/forward", response_model=SentReply)
def send_forward(mail_id: Id, body: ForwardRequest, user_id: int = Depends(current_user_id),
                 db: Session = Depends(get_db)) -> SentReply:
    mail, account = _received(db, mail_id, user_id)
    return _deliver(db, user_id, account, "forward", body, mail=mail, to=body.to)


@router.post("/mails", response_model=SentReply, status_code=201)
def send_new(body: NewMailRequest, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> SentReply:
    q = select(Account).where(Account.user_id == user_id).order_by(Account.id)
    if body.account_id is not None:
        q = q.where(Account.id == body.account_id)
    account = next((a for a in db.scalars(q) if can_send(a)), None)
    if account is None:
        raise HTTPException(404 if body.account_id is not None else 501, "보낼 수 있는 계정이 없습니다")
    return _deliver(db, user_id, account, "new", body, mail=None, to=body.to)
