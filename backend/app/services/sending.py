"""메일 보내기 한 곳 (BE-5 답장 · T14 재촉). 사용자가 확인한 발송만 부른다(D37 · D48).

dummy(시연) 계정은 실제로 보내지 않고 보낸 메일(direction=sent)로 같은 대화에 기록한다. Outlook(`outlook_graph`)은
Graph `Mail.Send` 연결(BE-7) 전이라 보낼 수 없다(부르는 쪽이 can_send로 먼저 막는다). 본문은 저장하지 않는다(구조도 10절).
"""
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Account, Mail

SENDABLE = ("dummy",)  # 실제로 보낼 수 있는 메일 원본. outlook_graph는 BE-7(Mail.Send) 뒤에 더한다
CANNOT_SEND = "이 계정은 아직 서비스 안에서 보낼 수 없습니다(Outlook 연결 뒤)"


def can_send(account: Account) -> bool:
    return account.provider in SENDABLE


def record_sent(db: Session, account: Account, *, recipients: list[str], subject: str, conversation_id: str | None,
                category: str, at: datetime) -> Mail:
    """보낸 메일 한 통을 남긴다. category: 답장은 '기타'(요청 아님), 재촉은 '요청'(응답 대기를 다시 센다)."""
    sent = Mail(account_id=account.id, source_id=f"sent-{uuid.uuid4().hex}", direction="sent", sender=account.email,
                recipients=list(recipients), subject=subject, sent_at=at, conversation_id=conversation_id, category=category)
    db.add(sent)
    db.flush()
    return sent
