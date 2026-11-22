"""업무 근거 문장(AI-15 · T08, 화면 UX-D16 형광펜). 할 일마다 그 할 일이 나온 본문 문장을 붙인다.

형식: `TaskOut.evidence` = 본문에 **글자 그대로 있는 문장**을 줄바꿈(\\n)으로 이은 것. 못 찾으면 None.
화면은 줄마다 본문에서 찾아 칠하고, 못 찾은 줄은 칠하지 않는다(틀린 곳을 칠하지 않는 것이 먼저다).

원칙(11-22 사용자 결정, AI-D33): **근거는 모델이 고르고 코드는 검증만 한다.**
0. 모델이 옮겨 적은 근거(나에게 맡긴 문장 · 표의 내 행)가 본문 문장과 글자로 겹치면 그 문장(`_quoted`).
   모델 근거가 없거나 본문에서 못 찾으면(바꿔 쓴 인용 · 지어낸 문장) None — 코드가 닮은 문장을 대신 고르지 않는다.
   (11/7 ~ 11/22에는 할 일 문구와 닮은 문장 · 기한 글자 든 문장으로 메웠다. 한글 조각 닮음이 영문 메일에서 비고(AI-T12)
   엉뚱한 문장을 고를 수 있어 뺐다)
1. 기한 글자가 근거 바로 옆 문장에만 있으면 그 문장도 붙인다('~ 부탁드립니다. 수요일까지 필요합니다.') — 고른 근거를 넓힐 뿐 새로 고르지 않는다.
"""
import re

from app.llm.client import LLMClient, LLMError
from app.pipeline.conditions import sentences, strip_body
from app.prompts import evidence_v1
from app.schemas.classify import ClassifyRequest, TaskOut

def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def body_sentences(body: str) -> list[str]:
    """서명 · 인사를 뺀 본문 문장(규칙이 요청을 찾는 단위와 같다). 모두 본문에 글자 그대로 있다."""
    out: list[str] = []
    for _, s in sentences(strip_body(body)):
        if s not in out:
            out.append(s)
    return out


def _quoted(quote: str, sents: list[str]) -> list[int]:
    """모델이 옮겨 적은 근거와 글자로 겹치는 본문 문장(근거가 문장 일부거나, 문장 여럿을 이었거나)."""
    q = _squash(quote)
    if len(q) < 8:
        return []
    seen: set[str] = set()  # 같은 문장이 본문에 여러 번 있으면 첫 곳만 칠한다
    out = []
    for i, s in enumerate(sents):
        k = _squash(s)
        if len(k) >= 8 and (k in q or q in k) and k not in seen:
            seen.add(k)
            out.append(i)
    return out


def _with_due(idx: list[int], task: TaskOut, sents: list[str]) -> list[int]:
    due = _squash(task.due_raw or "")
    if not idx or not due or any(due in _squash(sents[i]) for i in idx):
        return idx
    for j in (idx[-1] + 1, idx[0] - 1):  # 바로 뒤 · 앞 문장만
        if 0 <= j < len(sents) and due in _squash(sents[j]):
            return sorted({*idx, j})
    return idx


def attach(tasks: list[TaskOut], req: ClassifyRequest) -> None:
    """tasks의 evidence를 본문 문장으로 맞춘다(제자리 수정). 들어올 때 t.evidence는 모델이 옮겨 적은 근거(없으면 None)다.
    본문이 없으면(본문 읽기 꺼짐) 모두 None."""
    sents = body_sentences(req.body)
    for t in tasks:
        idx = _with_due(_quoted(t.evidence or "", sents), t, sents)
        t.evidence = "\n".join(sents[i] for i in idx) or None


def quote_with_model(tasks: list[TaskOut], body: str, me: str, llm: LLMClient) -> list[str | None]:
    """근거만 다시 고르기(AI-46): 모델이 할 일마다 근거 문장을 옮겨 적고, 코드는 본문 문장과 글자로 맞는지만 검증한다.
    맞지 않으면(바꿔 쓴 인용 · 지어낸 문장) None — 닮음 규칙으로 대신 고르지 않는다. 모델이 실패하면 LLMError를 그대로 올린다."""
    sents = body_sentences(body)
    if not sents or not tasks:
        return [None] * len(tasks)
    listing = "\n".join(f"{i}. {t.text}" + (f" (기한: {t.due_raw})" if t.due_raw else "") for i, t in enumerate(tasks, 1))
    out = llm.chat_json(evidence_v1.SYSTEM, f"내 이름: {me or '모름'}\n할 일:\n{listing}\n\n본문:\n{strip_body(body)}",
                        evidence_v1.SCHEMA)
    quotes = out.get("evidence") if isinstance(out, dict) else None
    if not isinstance(quotes, list):
        raise LLMError("evidence: 형식이 맞지 않음")
    found: list[str | None] = []
    for i, t in enumerate(tasks):
        q = quotes[i] if i < len(quotes) and isinstance(quotes[i], str) else ""
        idx = _with_due(_quoted(q, sents), t, sents)
        found.append("\n".join(sents[j] for j in idx) or None)
    return found
