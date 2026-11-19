"""업무 근거 문장(AI-15 · T08, 화면 UX-D16 형광펜). 할 일마다 그 할 일이 나온 본문 문장을 붙인다.

형식: `TaskOut.evidence` = 본문에 **글자 그대로 있는 문장**을 줄바꿈(\\n)으로 이은 것. 못 찾으면 None.
화면은 줄마다 본문에서 찾아 칠하고, 못 찾은 줄은 칠하지 않는다(틀린 곳을 칠하지 않는 것이 먼저다).

붙이는 순서 (11/7 개발 세트 7종 점검 · AI-D15에서 규칙 근거 단계를 뺐다 — 규칙은 요청 문장을 찾지 않는다):
0. (11/20, classify_v8.2) 모델이 옮겨 적은 근거(나에게 맡긴 문장 · 표의 내 행)가 본문 문장과 글자로 겹치면 그 문장.
   모델 근거가 없거나 본문에서 못 찾으면(바꿔 쓴 인용) 아래 1 · 2 — 바꿔 쓴 인용을 닮음으로 맞추면 짧은 인용(제목)이 엉뚱한 문장을 골랐다
1. 본문 문장 중 할 일 문구와 가장 닮은 문장 하나(MIN_SHARE 이상). 기한 글자가 든 문장 · 내 이름이 든 문장(나를 지목한 행)이면
   조금 더 쳐 준다. 그것도 없으면 기한 글자가 든 문장(본문에 하나뿐일 때만).
2. 기한 글자가 근거 바로 옆 문장에만 있으면 그 문장도 붙인다('~ 부탁드립니다. 수요일까지 필요합니다.').
닮음은 한글 bigram + 영문 낱말(3글자 이상)로 잰다 — 영문 메일은 한글 bigram만으로 근거가 비었다(dev9 M-0011).
"""
import re

from app.pipeline.conditions import sentences, strip_body
from app.schemas.classify import ClassifyRequest, TaskOut

MIN_SHARE = 0.35  # 할 일 문구 한글 bigram 중 이 비율 이상이 문장에 있어야 근거로 본다
DUE_BONUS = 0.15


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _kbigrams(text: str) -> set[str]:
    """낱말 안 한글 bigram. 띄어쓰기를 지우고 이으면 '참석자 성함'에서 '자성' 같은 없는 조각이 생겨 닮음이 낮게 나왔다(dev2 M-0022)."""
    return {w[i:i + 2] for w in re.findall(r"[가-힣]+", text) for i in range(len(w) - 1)} | \
        {w.lower() for w in re.findall(r"[A-Za-z]{3,}", text)}


def _share(source: str, task_text: str) -> float:
    kt = _kbigrams(task_text)
    return len(_kbigrams(source) & kt) / max(len(kt), 1)


def body_sentences(body: str) -> list[str]:
    """서명 · 인사를 뺀 본문 문장(규칙이 요청을 찾는 단위와 같다). 모두 본문에 글자 그대로 있다."""
    out: list[str] = []
    for _, s in sentences(strip_body(body)):
        if s not in out:
            out.append(s)
    return out


def _best_sentence(source: str, task: TaskOut, sents: list[str], me: str) -> list[int]:
    due = _squash(task.due_raw or "")
    scored = [(_share(s, source) + (DUE_BONUS if due and due in _squash(s) else 0) + (DUE_BONUS if me and me in s else 0), i)
              for i, s in enumerate(sents)]
    if not scored:
        return []
    score, i = max(scored)
    return [i] if _share(sents[i], source) >= MIN_SHARE else []


def _quoted(quote: str, sents: list[str]) -> list[int]:
    """모델이 옮겨 적은 근거와 글자로 겹치는 본문 문장(근거가 문장 일부거나, 문장 여럿을 이었거나)."""
    q = _squash(quote)
    if len(q) < 8:
        return []
    return [i for i, s in enumerate(sents) if len(_squash(s)) >= 8 and (_squash(s) in q or q in _squash(s))]


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
    me = req.owner.name or ""
    for t in tasks:
        idx = _quoted(t.evidence or "", sents)
        if not idx and sents:
            idx = _best_sentence(t.text, t, sents, me)
        if not idx and t.due_raw:  # 기한 글자가 든 문장 하나뿐이면 그 문장(회의 '일시: 10/30(금) 16:00~17:30' 줄 · 기한만 따로 말한 줄)
            hits = [i for i, s in enumerate(sents) if _squash(t.due_raw) in _squash(s)]
            idx = hits if len(hits) == 1 else []
        idx = _with_due(idx, t, sents)
        t.evidence = "\n".join(sents[i] for i in idx) or None
