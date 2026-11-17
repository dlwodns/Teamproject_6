"""서비스 안 답장 보내기 `POST /api/mails/{mail_id}/reply` (BE-5 · D48 (가) · 기획 detail 4.4절).

- 보내기는 사용자가 [보내기]를 누를 때만(자동 발송 없음, D37). 답장 뒤 '완료로 처리할까요?' 시트 · '오늘 다시 보지 않음' 바로 완료는
  화면이 한다(features/mail/replyConfirm.ts). 이 API는 보내고, 보낸 메일을 같은 대화에 남긴다.
- 메일 원본별: dummy(시연) 계정은 실제로 보내지 않고 보낸 메일로만 기록한다. Outlook(`outlook_graph`)은 Graph `Mail.Send`
  연결(BE-7) 전이라 501 — 화면은 501이면 보내기를 숨긴다(R6 · FE NOT_AVAILABLE).
- (가)로 이미 물은 업무는 (나) 답장 감지 알림(reply_confirm)으로 다시 묻지 않는다(D48): 그 메일의 미처리 업무마다
  이 답장에 대한 '그대로 두기(keep)'를 남긴다. 다음에 다른 답장을 보내면 그 답장으로는 다시 묻는다(BE-12 규칙 그대로).
- 본문은 저장하지 않는다(구조도 10절). 받는 사람은 원 메일 보낸 사람. 글은 로그에 남기지 않는다.
"""
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
from app.services.sending import CANNOT_SEND, can_send, record_sent

router = APIRouter(prefix="/api")


class ReplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account: str | None = None  # 화면이 보여 준 보낸 계정. 받아 두기만 하고 쓰지 않는다 — 보내기는 늘 원 메일을 받은 계정으로
    subject: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=20000)  # 미리보기에 보인 글자 그대로. 저장하지 않는다
    template_key: str | None = Field(None, max_length=50)

    @field_validator("subject", "content", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v


class SentReply(BaseModel):
    id: int  # 보낸 메일(direction = sent)
    sent_at: datetime  # +09:00


@router.post("/mails/{mail_id}/reply", response_model=SentReply)
def send_reply(mail_id: Id, body: ReplyRequest, user_id: int = Depends(current_user_id),
               db: Session = Depends(get_db)) -> SentReply:
    mail = db.get(Mail, mail_id)
    account = db.get(Account, mail.account_id) if mail else None
    if account is None or account.user_id != user_id:
        raise HTTPException(404, "메일을 찾을 수 없습니다")
    if mail.direction != "received":
        raise HTTPException(422, "받은 메일에만 답장할 수 있습니다")
    if not can_send(account):
        raise HTTPException(501, CANNOT_SEND)
    at = now()
    # 내가 보낸 답장은 요청이 아니다(기타) — 제목에 RE:가 없어도 응답 대기(BE-13)에 넣지 않는다
    sent = record_sent(db, account, recipients=[mail.sender], subject=body.subject,
                       conversation_id=mail.conversation_id, category="기타", at=at)
    open_ids = db.scalars(select(Task.id).where(Task.mail_id == mail.id, Task.status.in_(("pending", "snoozed")))).all()
    # D48: 화면 시트로 이미 물었다 → 이 답장으로는 알림 센터에서 다시 묻지 않는다. reminders.actions.dismiss를 쓰지 않고
    # 직접 남기는 이유: dismiss는 지금 보이는 항목(_find)만 받는데, 업무 항목이 다른 유형(기한 임박 등)이면 reply_confirm 키를 못 찾는다
    for tid in open_ids:
        db.add(ReminderFeedback(user_id=user_id, key=make_key("reply_confirm", "task", tid), type="reply_confirm",
                                reason="keep", ref_id=sent.id, created_at=at))
    db.commit()
    return SentReply(id=sent.id, sent_at=as_kst(at))
