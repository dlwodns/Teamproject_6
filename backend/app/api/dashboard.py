"""대시보드 원자료 API (BE-3, 구조도 v3.1 8절 ②).

GET /api/dashboard → {as_of, contacts, mails, tasks}. 형식은 FE 임시 계약(frontend/src/api/provisional.ts)이고,
구조도 8절 [제안](요약 + 칸별 count · task_ids) 대신 이 형식을 쓴다. 숫자 · 칸 집계는 FE aggregate.ts 한 곳에서 한다.
업무 상태를 바꾼 뒤(버튼 · 에이전트) FE는 이 API를 다시 불러 화면을 갱신한다.

- 사용자 범위: 인증이 아직 없어 DB 전체를 돌려준다(단일 사용자 전제).
- mails: 받은 메일(direction = received)만. tasks: 그 메일들의 업무 전체(pending · done · excluded · snoozed 모두).
  보관 · 지운 편지함으로 옮긴 메일 · 우리 앱에서 숨긴 메일과 그 업무는 뺀다(models/mail.visible_mail, 11-19 사용자 결정).
- 정렬: id 순.
- awaiting: 응답 대기(BE-13, services/awaiting). X-User-Id(없으면 dev 1번)의 사용자가 있을 때만 넣는다.
- 응답에 넣지 않은 항목(값이 없는 것을 0으로 보이지 않게 아예 뺀다):
  보낸 메일 목록, 새 알림(BE-12 리마인더 · BE-5 완료 확인), 분류 대기(BE-9), 최근 행동(BE-11).
"""
from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.clock import as_kst
from app.core.config import get_settings
from app.core.db import get_db
from app.core.user import DEV_USER_ID, MAX_ID
from app.models import Account, Contact, Mail, Task, User
from app.models.mail import visible_mail
from app.schemas.dashboard import DashboardContact, DashboardMail, DashboardResponse, DashboardTask
from app.services.awaiting import list_awaiting

router = APIRouter(prefix="/api")


def mail_view(m: Mail, account: str | None) -> DashboardMail:
    """목록 칸 메일 한 통(대시보드 · PATCH /api/mails/{id} 응답이 같은 모양)."""
    return DashboardMail(id=m.id, source_id=m.source_id, direction=m.direction, sender=m.sender, subject=m.subject,
                         received_at=as_kst(m.sent_at), category=m.category, to=list(m.recipients or []), account=account,
                         folder=m.folder, read_at=as_kst(m.read_at), pinned_at=as_kst(m.pinned_at),
                         importance=m.importance)


def _awaiting_user(db: Session, x_user_id: int | None) -> int | None:
    """응답 대기를 셀 사용자. 대시보드는 사용자 없이도 열리므로(단일 사용자 전제) 모르면 None — 401로 막지 않는다."""
    uid = x_user_id if x_user_id is not None else (DEV_USER_ID if get_settings().app_mode == "dev" else None)
    return uid if uid is not None and db.get(User, uid) is not None else None


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(db: Session = Depends(get_db),
                  x_user_id: int | None = Header(default=None, ge=1, le=MAX_ID)) -> DashboardResponse:
    as_of = clock.now()  # 모듈 속성으로 불러 테스트 · 시간 이동(BE-14)에서 바꿀 수 있게 한다
    shown = (Mail.direction == "received") & visible_mail()
    mails = db.scalars(select(Mail).where(shown).order_by(Mail.id)).all()
    tasks = db.scalars(select(Task).join(Mail, Task.mail_id == Mail.id).where(shown).order_by(Task.id)).all()
    contacts = db.scalars(select(Contact).order_by(Contact.id)).all()
    accounts = {a.id: a.email for a in db.scalars(select(Account))}
    uid = _awaiting_user(db, x_user_id)
    return DashboardResponse(
        awaiting=list_awaiting(db, uid, as_of) if uid is not None else None,
        as_of=as_kst(as_of),
        contacts=[DashboardContact(email=c.email, name=c.name, position=c.position, is_superior=c.is_superior,
                                   is_favorite=c.is_favorite) for c in contacts],
        mails=[mail_view(m, accounts.get(m.account_id)) for m in mails],
        tasks=[DashboardTask(id=t.id, mail_id=t.mail_id, text=t.text, due_at=as_kst(t.due_at), due_raw=t.due_raw,
                             due_time_stated=t.due_time_stated, due_source=t.due_source, status=t.status, seen_at=as_kst(t.seen_at), type=t.type,
                             evidence_text=t.evidence_text) for t in tasks],
    )
