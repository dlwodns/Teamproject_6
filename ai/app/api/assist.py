from fastapi import APIRouter, Depends

from app.agent.assist import draft, summarize
from app.agent.polish import polish
from app.api.deps import llm_dep
from app.llm.client import LLMClient, with_timeout
from app.prompts import assist_v4
from app.schemas.assist import (DraftRequest, DraftResponse, PolishRequest, PolishResponse, SummarizeRequest,
                                SummarizeResponse)

router = APIRouter()


@router.post("/summarize", response_model=SummarizeResponse)
def summarize_endpoint(req: SummarizeRequest, llm: LLMClient = Depends(llm_dep)):
    if req.mode != "mail":  # 요약 · 회고 머리 문장은 정한 시각에 미리 만드는 백그라운드 호출: 10분 · 고정 강도(io_spec 3.5절, AI-29)
        llm = with_timeout(llm, assist_v4.SUMMARY_TIMEOUT_S, assist_v4.SUMMARY_REASONING)
    return summarize(req, llm)


@router.post("/draft", response_model=DraftResponse)
def draft_endpoint(req: DraftRequest, llm: LLMClient = Depends(llm_dep)):
    # 표시용 초안. 발송은 backend가 사용자 확인 뒤에만 한다(D37)
    return draft(req, llm)


@router.post("/polish", response_model=PolishResponse)
def polish_endpoint(req: PolishRequest, llm: LLMClient = Depends(llm_dep)):
    # 사용자가 쓴 답장을 고른 방식대로 다듬는다. 표시용 — 발송은 사용자가 한다(D37). 모델 결과가 검사에 걸리면 받은 글 그대로
    return polish(req, llm)
