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
- BE-7 단계 2: 작은 첨부(attachments, 합쳐 3MB 미만, Outlook만 실제로 붙는다) · 예약 보내기(send_at → 202, 스케줄러가 그 시각에
  deliver를 부른다. GET /api/scheduled-sends · DELETE /api/scheduled-sends/{id}로 보고 취소).
- 본문은 저장하지 않는다(구조도 10절). 예약은 보낼 때까지만 요청을 들고 있다가 보낸 뒤 비운다. 글은 로그에 남기지 않는다.
"""
import base64
import binascii
import logging
from contextlib import contextmanager
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import as_kst, now, real_now, to_kst_naive
from app.core.db import get_db
from app.core.user import Id, current_user_id
from app.models import Account, Mail, ReminderFeedback, ScheduledSend, Task
from app.reminders.rules import make_key
from app.services.sending import CANNOT_SEND, Kind, SendUnknown, can_send, draft_recipients, record_sent, send_graph

router = APIRouter(prefix="/api")
log = logging.getLogger(__name__)
SEND_LOCK_WAIT = 60  # 초. 화면 제한 시간(SLOW_REQUEST_TIMEOUT_MS 140초)보다 충분히 짧게

MAX_ATTACH_BYTES = 3 * 1024 * 1024  # Graph POST .../attachments 한도(3MB 미만). 큰 첨부(업로드 세션)는 단계 2 뒤


class Attachment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    content_type: str = Field("application/octet-stream", max_length=100)
    content_b64: str = Field(min_length=1)


class ReplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account: str | None = None  # 화면이 보여 준 보낸 계정. 받아 두기만 하고 쓰지 않는다 — 보내기는 늘 원 메일을 받은 계정으로
    subject: str = Field(min_length=1, max_length=255)  # Outlook 답장 · 전달은 Outlook이 RE: · FW: 제목을 붙인다(이 값은 기록용)
    content: str = Field(min_length=1, max_length=20000)  # 미리보기에 보인 글자 그대로. 저장하지 않는다
    template_key: str | None = Field(None, max_length=50)
    cc: list[str] = Field(default_factory=list, max_length=50)
    bcc: list[str] = Field(default_factory=list, max_length=50)
    attachments: list[Attachment] = Field(default_factory=list, max_length=10)
    send_at: datetime | None = None  # 예약 보내기(시간대 포함). 비면 지금

    @field_validator("subject", "content", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("cc", "bcc")
    @classmethod
    def _addresses(cls, v: list[str]) -> list[str]:
        return _check_addresses(v)

    @field_validator("attachments")
    @classmethod
    def _size(cls, v: list[Attachment]) -> list[Attachment]:
        total = 0
        for a in v:
            try:
                total += len(base64.b64decode(a.content_b64, validate=True))
            except (binascii.Error, ValueError):
                raise ValueError(f"첨부 {a.name}: base64가 아닙니다") from None
        if total >= MAX_ATTACH_BYTES:
            raise ValueError("첨부는 합쳐 3MB 미만이어야 합니다")
        return v

    @field_validator("send_at")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("send_at에는 시간대가 있어야 합니다")
        return v


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


class ScheduledView(BaseModel):
    scheduled_id: int
    kind: str
    mail_id: int | None
    subject: str
    to: str
    send_at: datetime  # +09:00
    status: str  # pending | sending | sent | failed | unknown | canceled
    error: str | None
    sent_mail_id: int | None


REQUESTS: dict[str, type[ReplyRequest]] = {"reply": ReplyRequest, "replyAll": ReplyRequest, "forward": ForwardRequest,
                                           "new": NewMailRequest}


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
                               subject=body.subject, attachments=[a.model_dump() for a in body.attachments])
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


def _target(db: Session, user_id: int, kind: Kind, mail_id: int | None,
            body: ReplyRequest) -> tuple[Mail | None, Account, list[str], ReplyRequest]:
    """보낼 원 메일 · 계정 · 받는 사람을 정한다. 지금 보내기와 예약(맡길 때 · 보낼 때 두 번) 모두 이 검사를 거친다."""
    if kind == "new":
        q = select(Account).where(Account.user_id == user_id).order_by(Account.id)
        if body.account_id is not None:
            q = q.where(Account.id == body.account_id)
        account = next((a for a in db.scalars(q) if can_send(a)), None)
        if account is None:
            raise HTTPException(404 if body.account_id is not None else 501, "보낼 수 있는 계정이 없습니다")
        return None, account, body.to, body
    mail, account = _received(db, mail_id, user_id)
    if kind == "forward":
        return mail, account, body.to, body
    if mail.direction != "received":
        raise HTTPException(422, "받은 메일에만 답장할 수 있습니다")
    if kind == "reply":
        return mail, account, [mail.sender], body
    me = account.email.lower()
    to = [a for a in dict.fromkeys([mail.sender, *(mail.recipients or [])]) if a.lower() != me]
    cc = [a for a in (mail.cc or []) if a.lower() != me and a not in to]
    return mail, account, to, body.model_copy(update={"cc": body.cc or cc})


def deliver(db: Session, user_id: int, kind: Kind, mail_id: int | None, body: ReplyRequest, *, keep: bool = True) -> Mail | None:
    """지금 보낸다(스케줄러 run_due도 부른다). 실패는 HTTPException. None = Outlook으로 나갔지만 기록하지 못함(다시 보내지 않는다).
    keep: 답장이면 '완료로 처리할까요?' 시트로 이미 물었다고 남긴다(D48). 예약은 시트를 건너뛰므로 False — 답장 감지 알림이 묻게."""
    mail, account, to, body = _target(db, user_id, kind, mail_id, body)
    with _locked(account):
        sent = None
        try:
            sent = _send(db, account, kind, body, mail=mail, to=to)
            if keep and kind in ("reply", "replyAll"):
                _keep_reply_confirm(db, user_id, mail, sent)
            db.commit()
        except HTTPException:
            raise
        except Exception as e:
            if not (isinstance(e, _NotRecorded) or (sent is not None and account.provider == "outlook_graph")):
                raise  # 보내기 전 실패 · 시연 계정(기록이 곧 보내기) → 500, 다시 보내도 된다
            db.rollback()
            log.exception("Outlook으로 보냈지만 기록 실패 account=%s", account.id)
            return None
    return sent


def _schedule(db: Session, user_id: int, kind: Kind, mail_id: int | None, body: ReplyRequest) -> JSONResponse:
    mail, account, to, _ = _target(db, user_id, kind, mail_id, body)  # 지금 보낼 수 없는 것은 맡지 않는다
    if not can_send(account):
        raise HTTPException(501 if account.provider != "outlook_graph" else 409, CANNOT_SEND)
    at = to_kst_naive(body.send_at)  # 실제 시각(real_now) 기준 — 시연 시각을 옮겨도 일찍 나가지 않게, 화면(Date.now())과 같은 기준
    if at <= real_now():
        raise HTTPException(422, "예약 시각은 지금보다 뒤여야 합니다")
    row = ScheduledSend(user_id=user_id, kind=kind, mail_id=mail.id if mail else None, subject=body.subject[:255],
                        to_text=", ".join(to)[:500], request_json=body.model_dump(mode="json", exclude={"send_at"}), send_at=at)
    db.add(row)
    db.commit()
    return JSONResponse(_view(row).model_dump(mode="json"), status_code=202)


def _respond(db: Session, user_id: int, kind: Kind, mail_id: int | None, body: ReplyRequest):
    if body.send_at is not None:
        return _schedule(db, user_id, kind, mail_id, body)
    sent = deliver(db, user_id, kind, mail_id, body)
    if sent is None:
        return SentReply(id=None, sent_at=as_kst(now()), recorded=False)
    return SentReply(id=sent.id, sent_at=as_kst(sent.sent_at))


def _view(r: ScheduledSend) -> ScheduledView:
    return ScheduledView(scheduled_id=r.id, kind=r.kind, mail_id=r.mail_id, subject=r.subject, to=r.to_text,
                         send_at=as_kst(r.send_at), status=r.status, error=r.error, sent_mail_id=r.sent_mail_id)


# 예약이면 202 + ScheduledView, 아니면 SentReply
RESPONSES = {202: {"model": ScheduledView, "description": "예약됨(send_at)"}}


@router.post("/mails/{mail_id}/reply", response_model=SentReply, responses=RESPONSES)
def send_reply(mail_id: Id, body: ReplyRequest, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)):
    return _respond(db, user_id, "reply", mail_id, body)


@router.post("/mails/{mail_id}/reply-all", response_model=SentReply, responses=RESPONSES)
def send_reply_all(mail_id: Id, body: ReplyRequest, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)):
    return _respond(db, user_id, "replyAll", mail_id, body)


@router.post("/mails/{mail_id}/forward", response_model=SentReply, responses=RESPONSES)
def send_forward(mail_id: Id, body: ForwardRequest, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)):
    return _respond(db, user_id, "forward", mail_id, body)


@router.post("/mails", response_model=SentReply, status_code=201, responses=RESPONSES)
def send_new(body: NewMailRequest, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)):
    return _respond(db, user_id, "new", None, body)


@router.get("/scheduled-sends", response_model=list[ScheduledView])
def list_scheduled(user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> list[ScheduledView]:
    """아직 안 나간 것과 실패 · 모름(사용자가 봐야 함)만, 보낼 시각 순."""
    rows = db.scalars(select(ScheduledSend).where(ScheduledSend.user_id == user_id,
                                                  ScheduledSend.status.in_(("pending", "sending", "failed", "unknown")))
                      .order_by(ScheduledSend.send_at, ScheduledSend.id)).all()
    return [_view(r) for r in rows]


@router.delete("/scheduled-sends/{scheduled_id}", response_model=ScheduledView)
def cancel_scheduled(scheduled_id: Id, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> ScheduledView:
    """취소: 아직 안 나간 것은 보내지 않고, 실패 · 모름은 목록에서 치운다. 보내는 중이면 409."""
    row = db.get(ScheduledSend, scheduled_id)
    if row is None or row.user_id != user_id or row.status in ("sent", "canceled"):
        raise HTTPException(404, "예약을 찾을 수 없습니다")
    # 조건부로 바꾼다 — 그사이 run_due가 '보내는 중'으로 선점했으면 취소됐다고 알리지 않는다
    done = db.query(ScheduledSend).filter(ScheduledSend.id == row.id, ScheduledSend.status.in_(("pending", "failed", "unknown"))) \
        .update({"status": "canceled", "request_json": None}, synchronize_session=False)
    db.commit()
    if done != 1:
        raise HTTPException(409, "지금 보내는 중이라 취소할 수 없습니다")
    db.refresh(row)
    return _view(row)


def run_due(db: Session, limit: int = 20) -> int:
    """보낼 시각이 된 예약을 보낸다(스케줄러 틱). 한 건씩 '보내는 중'으로 선점하고 커밋한 뒤 보낸다 — 틱이 겹쳐도 두 번 나가지 않게."""
    ids = db.scalars(select(ScheduledSend.id).where(ScheduledSend.status == "pending", ScheduledSend.send_at <= real_now())
                     .order_by(ScheduledSend.send_at).limit(limit)).all()
    done = 0
    for sid in ids:
        claimed = db.query(ScheduledSend).filter(ScheduledSend.id == sid, ScheduledSend.status == "pending") \
            .update({"status": "sending"}, synchronize_session=False)
        db.commit()
        if claimed != 1:
            continue
        row = db.get(ScheduledSend, sid)
        db.refresh(row)
        try:
            body = REQUESTS[row.kind].model_validate(row.request_json)
            sent = deliver(db, row.user_id, row.kind, row.mail_id, body, keep=False)
            row = db.get(ScheduledSend, sid)  # 기록 실패로 rollback됐을 수 있다
            row.status, row.sent_mail_id, row.error = "sent", sent.id if sent else None, None
            done += 1
        except HTTPException as e:
            db.rollback()
            row = db.get(ScheduledSend, sid)
            row.status, row.error = ("unknown" if e.status_code == 504 else "failed"), str(e.detail)[:200]
        except Exception as e:  # noqa: BLE001 - 한 건이 실패해도 다음 예약은 보낸다
            db.rollback()
            row = db.get(ScheduledSend, sid)
            row.status, row.error = "failed", e.__class__.__name__
        row.request_json = None  # 나갔든 실패했든 본문을 더 들고 있지 않는다(다시 보내기는 사용자가 새로 쓴다)
        db.commit()
    return done
