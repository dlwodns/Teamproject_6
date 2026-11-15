from fastapi import APIRouter, Depends

from app.api.deps import llm_dep
from app.llm.client import LLMClient
from app.pipeline.signals import extract
from app.schemas.signals import SignalsRequest, SignalsResponse

router = APIRouter()


@router.post("/signals", response_model=SignalsResponse)
def signals(req: SignalsRequest, llm: LLMClient = Depends(llm_dep)):
    """리마인더 신호(AI-24 · AI-D20): 약속 · 기한 변경 · 해결 · 나에게 온 질문. 분류(/classify)와 따로 부른다 —
    분류 프롬프트를 흔들지 않고, 보낸 메일에도 부를 수 있다. 모델이 판단하지 못해도 200으로 신호 없이 돌려주고
    fallback(quota · model_failed · bad_output)에 이유를 적는다. backend는 그것을 보고 다시 부른다(AI-D19)."""
    return extract(req, llm)
