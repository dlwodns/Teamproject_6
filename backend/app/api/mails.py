"""메일 한 통 보기 (GET /api/mails/{id}, #55 리뷰 — 대시보드에서 업무를 눌러 메일 본문으로 가는 장면) ·
읽음 · 고정 (PATCH /api/mails/{id}, FE-5d) · 메일함 옮기기 (POST /api/mails/{id}/move, BE-7) ·
보관 · 지운 메일 목록 (GET /api/mails/hidden, BE-7).

- 본문은 DB에 저장하지 않으므로(구조도 10절) 요청 때 원본에서 가져온다(app/mail/body.py, 더미 계정은 더미 메일 파일).
- 다른 사용자의 메일 · 없는 메일은 404. 원본에서 본문을 가져오지 못하면 503(빈 본문을 보여 주지 않는다).
- 이 메일의 업무를 상태와 상관없이 모두 함께 준다(화면이 근거 문장을 본문에 칠한다).
- 읽음 · 옮기기는 Outlook 계정이면 Graph에 먼저 쓰고(실패하면 우리 DB도 바꾸지 않는다), 더미 계정은 우리 DB에만 쓴다.
  고정은 우리 앱만의 표시라 Outlook에 쓰지 않는다. 삭제는 지운 편지함으로 옮기기(deleteditems)다 — 영구 삭제는 하지 않는다.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dashboard import mail_view
from app.core.clock import as_kst, now
from app.core.db import get_db
from app.core.user import Id, current_user_id
from app.mail.body import fetch_body
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


@router.get("/mails/{mail_id}", response_model=MailDetail)
def get_mail(mail_id: Id, user_id: int = Depends(current_user_id), db: Session = Depends(get_db)) -> MailDetail:
    mail, _ = _own(db, mail_id, user_id)
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
