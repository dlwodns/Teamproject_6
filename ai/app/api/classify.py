from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import llm_classify_dep, llm_dep, settings_dep
from app.core.config import Settings
from app.llm.client import LLMAuthError, LLMClient, LLMError, LLMQuotaError, with_timeout
from app.pipeline import evidence
from app.pipeline.classify import ModelOutputError, classify
from app.prompts import evidence_v1
from app.schemas.classify import ClassifyRequest, ClassifyResponse, EvidenceRequest, EvidenceResponse, TaskOut

router = APIRouter()


@router.post("/classify", response_model=ClassifyResponse)
def classify_mail(req: ClassifyRequest, llm: LLMClient = Depends(llm_classify_dep), settings: Settings = Depends(settings_dep)):
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



@router.post("/evidence", response_model=EvidenceResponse)
def requote_evidence(req: EvidenceRequest, llm: LLMClient = Depends(llm_dep)):
    """근거만 다시 고르기(AI-46): 모델이 옮겨 적고 코드가 검증한다. 엑사원 1회(업무 여럿을 한 번에). backend는 메일을 연 뒤 백그라운드로 부른다.
    모델이 실패하면 근거를 비운 채 이유만 준다(닮음 규칙으로 메우지 않는다)."""
    tasks = [TaskOut(text=t.text, due_raw=t.due_raw) for t in req.tasks]
    base = EvidenceResponse(evidence=[None] * len(tasks), source="none", prompt_version=evidence_v1.PROMPT_VERSION)
    try:
        found = evidence.quote_with_model(tasks, req.body, req.owner_name or "",
                                          with_timeout(llm, evidence_v1.TIMEOUT_S, evidence_v1.REASONING))
    except LLMError as e:
        return base.model_copy(update={"fallback": f"모델 호출 실패: {e}"})
    return base.model_copy(update={"evidence": found, "source": "exaone"})
