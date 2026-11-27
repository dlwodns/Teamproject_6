"""업무 근거 문장(AI-15 · T08, 화면 UX-D16 형광펜). 할 일마다 그 할 일이 나온 본문 문장을 붙인다.

형식: `TaskOut.evidence` = 본문에 **글자 그대로 있는 문장**을 줄바꿈(\\n)으로 이은 것. 못 찾으면 None.
화면은 줄마다 본문에서 찾아 칠하고, 못 찾은 줄은 칠하지 않는다(틀린 곳을 칠하지 않는 것이 먼저다).

원칙(11-22 사용자 결정, AI-D33): **근거는 모델이 고르고 코드는 검증만 한다.**
0. 모델이 옮겨 적은 근거(나에게 맡긴 문장 · 표의 내 행)가 본문에 이어서 그대로 있으면 그 자리의 문장(`_quoted`).
   이 메일이 쓴 부분(인용 위)을 먼저 보고, 없을 때만 인용된 앞 메일을 본다. 리마인더 신호와 같은 검증(`ground_evidence`).
   모델 근거가 없거나 본문에서 못 찾으면(바꿔 쓴 인용 · 지어낸 문장) None — 코드가 닮은 문장을 대신 고르지 않는다.
   (11/7 ~ 11/22에는 할 일 문구와 닮은 문장 · 기한 글자 든 문장으로 메웠다. 한글 조각 닮음이 영문 메일에서 비고(AI-T12)
   엉뚱한 문장을 고를 수 있어 뺐다)
1. 기한 글자가 근거 바로 옆 문장에만 있으면 그 문장도 붙인다('~ 부탁드립니다. 수요일까지 필요합니다.') — 고른 근거를 넓힐 뿐 새로 고르지 않는다.
"""
import re
import unicodedata

from app.llm.client import LLMClient, LLMError
from app.pipeline.conditions import sentences, strip_body
from app.prompts import evidence_v1
from app.schemas.classify import ClassifyRequest, TaskOut

MIN_QUOTE = 4  # '네.' 같은 조각은 근거가 아니다(공백을 뺀 글자 수)

# 답장 · 전달로 붙은 앞 메일이 시작하는 줄: 구분선(밑줄 · 대시 · 별표 5개 이상, '-----Original Message-----' 포함),
# Outlook 머리글('보낸 사람: · From:'), Gmail 머리글('~님이 작성: · ~ wrote:'), '>'로 시작하는 인용 줄.
# 리마인더 신호(signals)와 업무 근거가 같은 경계를 쓴다 — 예전에는 업무 근거만 '-----' · '*****'에서만 끊어서
# Outlook 회신(밑줄 + '보낸 사람:')의 인용된 앞 메일 문장을 근거로 칠했다(troubleshooting 52).
QUOTE_START = re.compile(r"^[ \t]*(?:[-_*]{5,}|(?:보낸\s*사람|From)\s*:|>|.*(?:님이\s*작성|wrote)\s*:[ \t]*$)", re.M | re.I)
_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"))  # 폭 없는 공백 · BOM · 보이지 않는 하이픈
_ELLIPSIS = re.compile(r"\s*(?:…|\.{3,})\s*")  # 모델이 긴 문장을 줄여 옮긴 자리('… before our Friday sync')
_WRAP = "\"'“”‘’「」『』<>()[] "  # 모델이 근거를 감싸 붙이는 따옴표 · 괄호


def own_text(body: str) -> str:
    """이 메일이 쓴 부분: 인용(앞 메일) 시작 줄 위만."""
    m = QUOTE_START.search(body)
    return body[:m.start()] if m else body


def _plain(s: str) -> str:
    """비교용: 보이지 않는 글자를 지우고 전각 글자 · 풀어 쓴 한글(NFD)을 보통 글자로 맞춘다."""
    return unicodedata.normalize("NFKC", s.translate(_INVISIBLE))


def _ws(s: str) -> str:
    return re.sub(r"\s+", "", _plain(s))


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def body_sentences(body: str) -> list[str]:
    """서명 · 인사를 뺀 본문 문장(규칙이 요청을 찾는 단위와 같다). 모두 본문에 글자 그대로 있다."""
    out: list[str] = []
    for _, s in sentences(strip_body(body)):
        if s not in out:
            out.append(s)
    return out


def _span(evidence: str, sents: list[str]) -> list[int] | None:
    """근거가 걸친 문장 번호. 한 문장 안이면 그 문장, 이어진 여러 문장에 걸치면 걸친 문장들. 없으면 None.
    근거 글자가 본문에 **이어서 그대로** 있어야 한다 — 바꿔 쓴 인용 안에 짧은 본문 문장('확인 부탁드립니다.')이
    글자로 들어 있다고 그 문장을 고르지 않는다(예전 `k in q` 규칙이 엉뚱한 문장을 칠한 원인)."""
    ev = _ws(evidence)
    if len(ev) < MIN_QUOTE:
        return None
    flat = [_ws(s) for s in sents]
    for i, s in enumerate(flat):
        if ev in s:
            return [i]
    joined = "".join(flat)
    if ev not in joined:
        return None
    start = joined.index(ev)
    end, pos, out = start + len(ev), 0, []
    for i, s in enumerate(flat):
        if pos < end and pos + len(s) > start:
            out.append(i)
        pos += len(s)
    return out or None


def ground_evidence_idx(evidence: str, sents: list[str]) -> list[int] | None:
    """모델 근거 → 본문 문장 번호. 통째로 못 찾으면 줄 · 말줄임(…)마다 찾는다(떨어진 문장을 이은 근거 · 줄여 옮긴 근거).
    조각 하나라도 본문에 없으면 None(지어낸 · 바꿔 쓴 근거는 칠하지 않는다)."""
    evidence = (evidence or "").strip().strip(_WRAP)
    idx = _span(evidence, sents)
    if idx is None:
        parts = [p.strip().strip(_WRAP) for p in re.split(r"\n|" + _ELLIPSIS.pattern, evidence)]
        parts = [p for p in parts if len(_ws(p)) >= MIN_QUOTE]
        found = [_span(p, sents) for p in parts]
        if len(parts) > 1 and all(f is not None for f in found):
            idx = sorted({i for f in found for i in f})  # type: ignore[union-attr]
    return idx


def ground_evidence(evidence: str, sents: list[str]) -> str | None:
    """모델 근거 → 본문 문장(들)을 줄바꿈으로(AI-D14 형식). 못 찾으면 None."""
    idx = ground_evidence_idx(evidence, sents)
    return "\n".join(sents[i] for i in idx) if idx else None


def _own_count(body: str, sents: list[str]) -> int:
    """sents(본문 전체 문장) 중 앞에서 몇 개가 이 메일이 쓴 부분(인용 위)인가."""
    own = body_sentences(own_text(body))
    return len(own) if sents[:len(own)] == own else len(sents)


def _quoted(quote: str, sents: list[str], n_own: int | None = None) -> list[int]:
    """모델이 옮겨 적은 근거가 본문에 이어서 그대로 있는 자리의 문장들. 이 메일이 쓴 부분(앞 n_own 문장)에서 먼저 찾고,
    없을 때만 인용된 앞 메일까지 본다(전달 메일은 할 일이 인용 안에 있다). 같은 문장이 양쪽에 있으면 이 메일 쪽이다."""
    n_own = len(sents) if n_own is None else n_own
    idx = ground_evidence_idx(quote, sents[:n_own]) if n_own else None
    if idx is None and n_own < len(sents):
        idx = ground_evidence_idx(quote, sents)
    return idx or []


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
    n_own = _own_count(req.body, sents)
    for t in tasks:
        idx = _with_due(_quoted(t.evidence or "", sents, n_own), t, sents)
        t.evidence = "\n".join(sents[i] for i in idx) or None


def quote_with_model(tasks: list[TaskOut], body: str, me: str, llm: LLMClient) -> list[str | None]:
    """근거만 다시 고르기(AI-46): 모델이 할 일마다 근거 문장을 옮겨 적고, 코드는 본문 문장과 글자로 맞는지만 검증한다.
    맞지 않으면(바꿔 쓴 인용 · 지어낸 문장) None — 닮음 규칙으로 대신 고르지 않는다. 모델이 실패하면 LLMError를 그대로 올린다."""
    sents = body_sentences(body)
    if not sents or not tasks:
        return [None] * len(tasks)
    n_own = _own_count(body, sents)
    listing = "\n".join(f"{i}. {t.text}" + (f" (기한: {t.due_raw})" if t.due_raw else "") for i, t in enumerate(tasks, 1))
    out = llm.chat_json(evidence_v1.SYSTEM, f"내 이름: {me or '모름'}\n할 일:\n{listing}\n\n본문:\n{strip_body(body)}",
                        evidence_v1.SCHEMA)
    quotes = out.get("evidence") if isinstance(out, dict) else None
    if not isinstance(quotes, list):
        raise LLMError("evidence: 형식이 맞지 않음")
    found: list[str | None] = []
    for i, t in enumerate(tasks):
        q = quotes[i] if i < len(quotes) and isinstance(quotes[i], str) else ""
        idx = _with_due(_quoted(q, sents, n_own), t, sents)
        found.append("\n".join(sents[j] for j in idx) or None)
    return found
