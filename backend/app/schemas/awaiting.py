"""응답 대기(BE-13) 한 줄. GET /api/awaiting · 대시보드 awaiting · 에이전트 T06이 같은 모양을 쓴다(FE provisional.ts ProvisionalAwaiting)."""
from datetime import datetime

from pydantic import BaseModel


class AwaitingView(BaseModel):
    mail_id: int  # 내가 보낸 요청 메일
    subject: str
    to: str  # 받는 사람 표시('박지호 매니저', 여럿이면 '… 외 N명')
    sent_at: datetime  # +09:00
    days: int  # 보낸 뒤 지난 날 수(내림)
