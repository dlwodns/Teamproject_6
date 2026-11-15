"""답장 AI 다듬기 `POST /api/mails/{mail_id}/polish` — 답장 칸에 쓴 글을 고른 방식대로 고친다(프런트 답장 화면 다듬기 버튼).

흐름: 내 메일인지 확인 → 원 메일(맥락) + 내가 쓴 글을 개인정보 가리기(BE-6) → ai `/polish` → 가린 값을 되돌려 응답.
- 표시용이다. 저장 · 발송하지 않는다(발송은 사용자가 보내기를 누를 때, D37 · D48). 그래서 action_log도 남기지 않는다.
- 본문 읽기가 꺼져 있으면 원 메일 본문은 보내지 않는다(제목만, 구조도 10절). 내가 쓴 글은 사용자가 다듬어 달라고 준 것이라 보낸다.
- ai가 다듬지 못하면(모델 실패 · 지어낸 숫자 등) 200으로 보낸 글 그대로와 이유(fallback)를 준다. ai 서비스에 닿지 못하면 503.
- 글 · 결과는 로그에 남기지 않는다.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app import privacy
from app.ai_client.client import AIClient, AIError, get_ai_client
from app.core.db import get_db
from app.core.user import Id, current_user_id
from app.mail.body import fetch_body
from app.models import Account, Mail
from app.schemas.ai import PolishStyle
from app.services.learn import reads_body

router = APIRouter(prefix="/api")
UNAVAILABLE = "AI 서비스에 연결할 수 없어 다듬지 못했어요. 잠시 뒤 다시 시도해 주세요."


class PolishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4000)  # 앞뒤 공백을 지운 뒤의 길이
    style: PolishStyle

    @field_validator("text", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v


class PolishView(BaseModel):
    text: str  # 다듬은 글(다듬지 못했으면 보낸 글 그대로)
    style: PolishStyle
    changed: bool  # 보낸 글과 다른가. false면 화면은 '바꿀 곳이 없어요' 또는 fallback 안내
    source: Literal["exaone", "none"]
    fallback: str | None = None  # 다듬지 못한 이유(화면 안내용)


@router.post("/mails/{mail_id}/polish", response_model=PolishView)
def polish_reply(mail_id: Id, body: PolishRequest, user_id: int = Depends(current_user_id),
                 db: Session = Depends(get_db), ai: AIClient = Depends(get_ai_client)) -> PolishView:
    mail = db.get(Mail, mail_id)
    account = db.get(Account, mail.account_id) if mail else None
    if account is None or account.user_id != user_id:
        raise HTTPException(404, "메일을 찾을 수 없습니다")
    original = (fetch_body(db, mail) or "") if reads_body(db, user_id) else ""
    masker = privacy.masker_for(db, user_id)
    payload = masker.mask_obj({"text": body.text, "style": body.style,
                               "mail": {"subject": mail.subject or "", "body": original, "sender": mail.sender}})
    db.rollback()  # ai를 부르는 동안 DB를 잡지 않는다(읽기만 했다)
    try:
        result = masker.unmask_model(ai.polish(payload))
    except AIError as e:
        raise HTTPException(503, UNAVAILABLE) from e
    return PolishView(text=result.text, style=result.style, changed=result.text != body.text, source=result.source,
                      fallback=result.fallback)
