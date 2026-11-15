from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import llm_dep, settings_dep
from app.core.config import Settings
from app.llm.client import LLMAuthError, LLMClient, LLMError, LLMQuotaError
from app.pipeline.classify import ModelOutputError, classify
from app.schemas.classify import ClassifyRequest, ClassifyResponse

router = APIRouter()


@router.post("/classify", response_model=ClassifyResponse)
def classify_mail(req: ClassifyRequest, llm: LLMClient = Depends(llm_dep), settings: Settings = Depends(settings_dep)):
    """엑사원 호출이 길다(메일 1통 약 27초). backend는 백그라운드 작업에서 부른다(BE-9).
    모델이 판단하지 못하면 규칙으로 메우지 않고 실패를 알린다(AI-D19). backend는 kind를 보고 다시 부른다.
    - quota(503): 하루 호출 한도 소진. 시도 횟수에 세지 않고 한도가 풀린 뒤 다시
    - auth(503): 키가 없거나 거절됨(설정 문제). 시도 횟수에 세지 않고 키를 고친 뒤 다시(#67 리뷰)
    - model_failed(503): 호출 실패(혼잡 · 제한 시간 · 연결). 시도 횟수에 세며 다시
    - bad_output(502): 모델 답이 맞지 않음. 시도 횟수에 세며 다시
    메시지에는 메일 본문 · 키를 넣지 않는다(LLMError 메시지 규칙)."""
    try:
        return classify(req, llm, settings)
    except LLMQuotaError as e:
        raise HTTPException(503, detail={"kind": "quota", "message": str(e)}) from e
    except LLMAuthError as e:
        raise HTTPException(503, detail={"kind": "auth", "message": str(e)}) from e
    except ModelOutputError as e:
        raise HTTPException(502, detail={"kind": "bad_output", "message": str(e)}) from e
    except LLMError as e:
        raise HTTPException(503, detail={"kind": "model_failed", "message": str(e)}) from e
