from fastapi import APIRouter, Depends

from app.agent.plan import plan
from app.api.deps import llm_dep
from app.llm.client import LLMClient
from app.schemas.agent import PlanRequest, PlanResponse

router = APIRouter()


@router.post("/agent/plan", response_model=PlanResponse)
def agent_plan(req: PlanRequest, llm: LLMClient = Depends(llm_dep)):
    return plan(req, llm)
