from fastapi import APIRouter, Depends, HTTPException

from app.agent.plan import plan
from app.api.deps import llm_dep
from app.llm.client import LLMClient, LLMError, LLMQuotaError
from app.schemas.agent import PlanRequest, PlanResponse

router = APIRouter()


@router.post("/agent/plan", response_model=PlanResponse)
def agent_plan(req: PlanRequest, llm: LLMClient = Depends(llm_dep)):
    """모델이 행동을 고르지 못하면(호출 실패 · 한도 소진) 규칙으로 메우지 않고 503으로 알린다(AI-D19).
    backend는 '지금은 명령을 처리할 수 없습니다'로 안내한다."""
    try:
        return plan(req, llm)
    except LLMQuotaError as e:
        raise HTTPException(503, detail={"kind": "quota", "message": str(e)}) from e
    except LLMError as e:
        raise HTTPException(503, detail={"kind": "model_failed", "message": str(e)}) from e
