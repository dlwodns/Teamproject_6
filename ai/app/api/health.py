from fastapi import APIRouter, Depends

from app.api.deps import llm_dep
from app.core import egress
from app.core.config import get_settings
from app.llm.client import LLMClient

router = APIRouter()


@router.get("/health")
def health(llm: LLMClient = Depends(llm_dep)) -> dict:
    # 모델이 없어도 서비스는 살아 있다(규칙 결과만 낸다). status는 서비스, llm은 모델 상태다.
    # egress: 외부 송신 건수 · 허용 목록(시연 ⑧ — 로컬 모드면 mode=local_only, external 0)
    return {"status": "ok", "model": llm.model, "llm": llm.health(), "egress": egress.snapshot(get_settings())}
