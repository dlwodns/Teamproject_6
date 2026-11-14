"""대시보드 원자료 API (BE-3, 구조도 v3.1 8절 ②).

GET /api/dashboard → {as_of, contacts, mails, tasks}. 형식은 FE 임시 계약(frontend/src/api/provisional.ts)이고,
구조도 8절 [제안](요약 + 칸별 count · task_ids) 대신 이 형식을 쓴다. 숫자 · 칸 집계는 FE aggregate.ts 한 곳에서 한다.
업무 상태를 바꾼 뒤(버튼 · 에이전트) FE는 이 API를 다시 불러 화면을 갱신한다.

- 사용자 범위: 인증이 아직 없어 DB 전체를 돌려준다(단일 사용자 전제).
- mails: 받은 메일(direction = received)만. tasks: 그 메일들의 업무 전체(pending · done · excluded · snoozed 모두).
- 정렬: id 순.
- 응답에 넣지 않은 항목(값이 없는 것을 0으로 보이지 않게 아예 뺀다):
  응답 대기 · 보낸 메일(BE-13), 새 알림(BE-12 리마인더 · BE-5 완료 확인), 분류 대기(BE-9), 최근 행동(BE-11).
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.clock import as_kst
from app.core.db import get_db
from app.models import Contact, Mail, Task
from app.schemas.dashboard import DashboardContact, DashboardMail, DashboardResponse, DashboardTask

router = APIRouter(prefix="/api")


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(db: Session = Depends(get_db)) -> DashboardResponse:
    as_of = clock.now()  # 모듈 속성으로 불러 테스트 · 시간 이동(BE-14)에서 바꿀 수 있게 한다
    mails = db.scalars(select(Mail).where(Mail.direction == "received").order_by(Mail.id)).all()
    tasks = db.scalars(
        select(Task).join(Mail, Task.mail_id == Mail.id).where(Mail.direction == "received").order_by(Task.id)
    ).all()
    contacts = db.scalars(select(Contact).order_by(Contact.id)).all()
    return DashboardResponse(
        as_of=as_kst(as_of),
        contacts=[DashboardContact(email=c.email, name=c.name, position=c.position, is_superior=c.is_superior,
                                   is_favorite=c.is_favorite) for c in contacts],
        mails=[DashboardMail(id=m.id, source_id=m.source_id, direction=m.direction, sender=m.sender, subject=m.subject,
                             received_at=as_kst(m.sent_at), category=m.category) for m in mails],
        tasks=[DashboardTask(id=t.id, mail_id=t.mail_id, text=t.text, due_at=as_kst(t.due_at), due_raw=t.due_raw,
                             due_source=t.due_source, status=t.status, seen_at=as_kst(t.seen_at)) for t in tasks],
    )
