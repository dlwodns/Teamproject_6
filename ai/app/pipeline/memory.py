"""문맥 기억 추출 (PL-16, BE-D21). 모델 출력은 그대로 믿지 않고 여기서 거른다.

- 종류는 works_on · org만. 값은 1~40자 한 줄.
- 근거 문장이 본문에 글자 그대로 있어야 한다(공백만 느슨하게 맞춘다). 없으면 버린다.
- 같은 종류는 처음 것 하나만.
- 모델을 부르지 못하면 facts 없이 fallback에 이유를 남긴다(backend는 기억을 바꾸지 않는다).
"""
import re

from app.llm.client import LLMClient, LLMError
from app.prompts import memory_v1 as prompt
from app.schemas.memory import Fact, MemoryExtractRequest, MemoryExtractResponse

MAX_VALUE = 40
KINDS = ("works_on", "org")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _clean(raw: list, body: str) -> list[Fact]:
    text = _norm(body)
    out: dict[str, Fact] = {}
    for f in raw if isinstance(raw, list) else []:
        if not isinstance(f, dict):
            continue
        kind, value, evidence = f.get("kind"), _norm(str(f.get("value", ""))), _norm(str(f.get("evidence", "")))
        if kind not in KINDS or kind in out or not (1 <= len(value) <= MAX_VALUE):
            continue
        if not evidence or evidence not in text:
            continue  # 근거가 본문에 없으면 지어낸 것일 수 있다
        out[kind] = Fact(kind=kind, value=value, evidence=evidence)
    return list(out.values())


def extract(req: MemoryExtractRequest, llm: LLMClient) -> MemoryExtractResponse:
    model = getattr(llm, "model", None)
    if not req.body.strip():
        return MemoryExtractResponse(mail_id=req.mail_id, source="none", model=model, prompt_version=prompt.VERSION,
                                     fallback="empty_body")
    try:
        out = llm.chat_json(prompt.SYSTEM, prompt.build_user(req), prompt.SCHEMA)
    except LLMError as e:
        return MemoryExtractResponse(mail_id=req.mail_id, source="none", model=model, prompt_version=prompt.VERSION,
                                     fallback=f"llm_unavailable: {e}"[:200])
    return MemoryExtractResponse(mail_id=req.mail_id, facts=_clean(out.get("facts", []), req.body), source="exaone",
                                 model=model, prompt_version=prompt.VERSION)
