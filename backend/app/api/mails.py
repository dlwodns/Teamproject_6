"""메일 한 통 보기 (GET /api/mails/{id}, #55 리뷰 — 대시보드에서 업무를 눌러 메일 본문으로 가는 장면).

- 본문은 DB에 저장하지 않으므로(구조도 10절) 요청 때 원본에서 가져온다(app/mail/body.py, 더미 계정은 더미 메일 파일).
- 다른 사용자의 메일 · 없는 메일은 404. 원본에서 본문을 가져오지 못하면 503(빈 본문을 보여 주지 않는다).
- 이 메일의 업무를 상태와 상관없이 모두 함께 준다(화면이 근거 문장을 본문에 칠한다).
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_client.client import AIClient, AIError, get_ai_client

from app.core.clock import as_kst
from app.core.db import get_db
from app.core.user import Id, current_user_id
from app.mail.body import fetch_body
from app.models import Account, Mail, Task, User
from app.schemas.mail_detail import MailDetail, MailDetailTask

router = APIRouter(prefix="/api")


def _own_mail(db: Session, user_id: int, mail_id: int) -> Mail:
    mail = db.scalar(select(Mail).join(Account, Mail.account_id == Account.id)
                     .where(Mail.id == mail_id, Account.user_id == user_id))
    if mail is None:
        raise HTTPException(404, "없는 메일입니다")
    return mail


@router.get("/mails/{mail_id}", response_model=MailDetail)
def get_mail(mail_id: Id, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> MailDetail:
    mail = _own_mail(db, user_id, mail_id)
    body = fetch_body(db, mail)
    if body is None:
        raise HTTPException(503, "메일 원본에서 본문을 가져오지 못했습니다")
    tasks = db.scalars(select(Task).where(Task.mail_id == mail.id).order_by(Task.id)).all()
    return MailDetail(
        id=mail.id, source_id=mail.source_id, direction=mail.direction, sender=mail.sender, subject=mail.subject,
        received_at=as_kst(mail.sent_at), category=mail.category, lane=mail.lane,
        to=list(mail.recipients or []), cc=list(mail.cc or []), body=body,
        tasks=[MailDetailTask(id=t.id, mail_id=t.mail_id, text=t.text, due_at=as_kst(t.due_at), due_raw=t.due_raw,
                              due_source=t.due_source, status=t.status, seen_at=as_kst(t.seen_at),
                              evidence_text=t.evidence_text) for t in tasks],
    )


class PolishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: str = Field(min_length=1, max_length=2000)  # 사용자가 답장 칸에 쓰거나 말한 글
    tone: Literal["polite", "short"] = "polite"


class PolishResult(BaseModel):
    body: str  # 다듬은 본문(인사말 · 맺음말 · 서명 없이). 보내지 않는다 — 사용자가 고친 뒤 직접 보낸다
    source: Literal["template", "exaone"]  # template = 모델을 못 써서 쓴 글을 그대로 돌려줌
    fallback: str | None = None


@router.post("/mails/{mail_id}/reply-polish", response_model=PolishResult)
def polish_reply(body: PolishRequest, mail_id: Id, user_id: int = Depends(current_user_id), db: Session = Depends(get_db),
                 ai: AIClient = Depends(get_ai_client)) -> PolishResult:
    """11-15 메일 답장 칸의 [업무 문체로 다듬기]: 사용자가 쓴(또는 음성으로 말한) 글을 격식 있는 업무 문장으로 다듬는다.
    원 메일 본문을 함께 보내 맥락을 맞춘다. 새 사실은 더하지 않는다(ai assist.draft 작성자 메모 규칙)."""
    mail = _own_mail(db, user_id, mail_id)
    original = fetch_body(db, mail) or ""
    me = db.get(User, user_id)
    payload = {"kind": "reply", "mail": {"subject": mail.subject or "", "body": original, "sender": mail.sender},
               "topic": body.notes.strip(), "tone": body.tone, "signer": me.name if me else None}
    try:
        r = ai.draft(payload)
    except AIError as e:
        raise HTTPException(503, "문장 다듬기를 지금 사용할 수 없습니다") from e
    return PolishResult(body=r.body, source=r.source, fallback=r.fallback)
