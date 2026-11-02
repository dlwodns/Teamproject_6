from fastapi import APIRouter, Depends

from app.api.deps import llm_dep, settings_dep
from app.core.config import Settings
from app.llm.client import LLMClient
from app.pipeline.classify import classify
from app.schemas.classify import ClassifyRequest, ClassifyResponse

router = APIRouter()


@router.post("/classify", response_model=ClassifyResponse)
def classify_mail(req: ClassifyRequest, llm: LLMClient = Depends(llm_dep), settings: Settings = Depends(settings_dep)):
    # 엑사원 호출이 길다(메일 1통 약 25초). backend는 백그라운드 작업에서 부른다(BE-9).
    return classify(req, llm, settings)
