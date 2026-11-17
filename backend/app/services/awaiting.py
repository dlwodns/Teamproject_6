"""응답 대기 목록(BE-13). 판정은 reminders/rules.awaiting_requests 한 곳 — 리마인더 '회신 미수신'과 같은 메일이 나온다."""
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.clock import as_kst, now
from app.reminders import rules
from app.schemas.awaiting import AwaitingView

MIN_DAYS, MAX_DAYS = 1, 30  # 설정(awaiting_reply_days)과 같은 범위


def list_awaiting(db: Session, user_id: int, at: datetime | None = None, *, min_days: int | None = None) -> list[AwaitingView]:
    """min_days가 없으면 사용자 설정 기준일(기본 3일). 오래 기다린 것부터."""
    ctx = rules.Context(db, user_id, at or now())
    mails = rules.awaiting_requests(ctx, min_days)
    return [AwaitingView(mail_id=m.id, subject=m.subject or "(제목 없음)", to=rules.recipients_label(ctx, m),
                         sent_at=as_kst(m.sent_at), days=(ctx.at - m.sent_at).days) for m in mails]
