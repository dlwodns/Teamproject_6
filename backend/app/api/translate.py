"""메일 번역 `POST /api/mails/{mail_id}/translate` (AI-32, 아웃룩 메시지 머리 […] → 번역 · 원본 보기).

- 누를 때만 ai `/translate`를 한 번 부르고 결과를 mails.translation에 저장한다. 다시 누르면 저장한 것을 준다(엑사원 하루 100회).
- 40자 미만 · 이미 한국어 · 모델 실패면 저장하지 않고 이유(fallback)만 준다(다음에 다시 시도할 수 있게). ai에 닿지 못하면 503.
- 본문 읽기가 꺼져 있으면 번역하지 않는다(구조도 10절). 본문 · 번역문은 로그에 남기지 않는다.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import privacy
from app.ai_client.client import AIClient, AIError, get_ai_client
from app.core.db import get_db
from app.core.user import Id, current_user_id
from app.mail.body import fetch_body
from app.models import Account, Mail
from app.services.learn import reads_body

router = APIRouter(prefix="/api")


class TranslationView(BaseModel):
    text: str  # 한국어 번역문. 번역하지 않았으면 ''
    lang: str | None = None  # 원문 언어
    source: Literal["exaone", "saved", "none"]  # saved: 저장한 번역(모델을 부르지 않음)
    fallback: str | None = None


@router.post("/mails/{mail_id}/translate", response_model=TranslationView)
def translate_mail(mail_id: Id, user_id: int = Depends(current_user_id), db: Session = Depends(get_db),
                   ai: AIClient = Depends(get_ai_client)) -> TranslationView:
    mail = db.get(Mail, mail_id)
    account = db.get(Account, mail.account_id) if mail else None
    if account is None or account.user_id != user_id:
        raise HTTPException(404, "메일을 찾을 수 없습니다")
    if mail.translation:
        return TranslationView(text=mail.translation["text"], lang=mail.translation.get("lang"), source="saved")
    if not reads_body(db, user_id):
        return TranslationView(text="", source="none", fallback="본문 읽기가 꺼져 있음")
    body = fetch_body(db, mail)
    if body is None:
        raise HTTPException(503, "메일 원본에서 본문을 가져오지 못했습니다")
    masker = privacy.masker_for(db, user_id)
    payload = masker.mask_obj({"text": body})
    db.commit()  # ai를 부르는 동안 DB를 잡지 않는다
    try:
        result = masker.unmask_model(ai.translate(payload))
    except AIError as e:
        raise HTTPException(503, "AI 서비스에 연결할 수 없어 번역하지 못했어요. 잠시 뒤 다시 시도해 주세요.") from e
    if result.source != "exaone" or not result.text:
        return TranslationView(text="", lang=result.lang, source="none", fallback=result.fallback)
    mail = db.get(Mail, mail_id)
    mail.translation = {"text": result.text, "lang": result.lang, "prompt_version": result.prompt_version}
    db.commit()
    return TranslationView(text=result.text, lang=result.lang, source="exaone")
