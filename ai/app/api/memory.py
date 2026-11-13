from fastapi import APIRouter, Depends

from app.api.deps import llm_dep
from app.llm.client import LLMClient
from app.pipeline.memory import extract
from app.schemas.memory import MemoryExtractRequest, MemoryExtractResponse

router = APIRouter()


@router.post("/memory/extract", response_model=MemoryExtractResponse, response_model_by_alias=True)
def memory_extract(req: MemoryExtractRequest, llm: LLMClient = Depends(llm_dep)):
    """문맥 기억 추출(PL-16, BE-D21). 분류(/classify)와 따로 부른다 — 분류 프롬프트 · 측정에 영향이 없다."""
    return extract(req, llm)
