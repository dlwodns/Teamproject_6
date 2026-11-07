from fastapi import APIRouter, Depends

from app.agent.assist import draft, summarize
from app.api.deps import llm_dep
from app.llm.client import LLMClient
from app.schemas.assist import DraftRequest, DraftResponse, SummarizeRequest, SummarizeResponse

router = APIRouter()


@router.post("/summarize", response_model=SummarizeResponse)
def summarize_endpoint(req: SummarizeRequest, llm: LLMClient = Depends(llm_dep)):
    return summarize(req, llm)


@router.post("/draft", response_model=DraftResponse)
def draft_endpoint(req: DraftRequest, llm: LLMClient = Depends(llm_dep)):
    # 표시용 초안. 발송은 backend가 사용자 확인 뒤에만 한다(D37)
    return draft(req, llm)
