"""메일 한 통 보기 (GET /api/mails/{id}, #55 리뷰 — 대시보드에서 업무를 눌러 메일 본문으로 가는 장면).

- 본문은 DB에 저장하지 않으므로(구조도 10절) 요청 때 원본에서 가져온다(app/mail/body.py, 더미 계정은 더미 메일 파일).
- 다른 사용자의 메일 · 없는 메일은 404. 원본에서 본문을 가져오지 못하면 503(빈 본문을 보여 주지 않는다).
- 이 메일의 업무를 상태와 상관없이 모두 함께 준다(화면이 근거 문장을 본문에 칠한다).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import as_kst
from app.core.db import get_db
from app.core.user import Id, current_user_id
from app.mail.body import fetch_body
from app.models import Account, Mail, Task
from app.schemas.mail_detail import MailDetail, MailDetailTask

router = APIRouter(prefix="/api")


@router.get("/mails/{mail_id}", response_model=MailDetail)
def get_mail(mail_id: Id, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> MailDetail:
    mail = db.scalar(select(Mail).join(Account, Mail.account_id == Account.id)
                     .where(Mail.id == mail_id, Account.user_id == user_id))
    if mail is None:
        raise HTTPException(404, "없는 메일입니다")
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
