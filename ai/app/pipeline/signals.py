"""리마인더 신호 (AI-24 · AI-D20): 모델 판단 → 형식 확인 → 날짜 계산.

원칙(AI-D19): 무엇이 약속 · 기한 변경 · 해결 · 질문인지는 모델이 정한다. 코드는 모델 답을 다른 답으로 바꾸지 않고,
형식이 맞지 않는 신호만 버린다(버린 수는 `dropped`).
- 근거: 이 메일 본문(서명 · 인사 · 인용 아래를 뺀 문장)에 글자 그대로 있어야 한다. 공백 · 폭 없는 글자 · 전각 글자 · 풀어 쓴 한글만
  느슨하게 맞추고, 화면이 칠할 수 있게 본문 문장 그대로 돌려준다(AI-D14 형식: 문장 여러 개면 줄바꿈으로 이음, 떨어진 문장도 줄마다
  찾는다). 못 찾으면 그 신호를 버린다(지어낸 근거 방지)
- 인용: 답장 · 전달로 붙은 앞 메일('보낸 사람: · From: · ~님이 작성: · > ' 줄, 밑줄 · 대시 구분선 아래)은 이 메일이 쓴 글이 아니다.
  이 메일이 쓴 문장이 하나도 없으면(서명 · 인용뿐) 모델을 부르지 않고 empty_body
- 방향: 보낸 메일의 약속은 me, 받은 메일의 약속은 them만 받는다. 다르면 버린다(누가 약속했는지 틀린 신호)
- task_id: 받은 open_tasks 안의 것만. 같은 업무에 같은 종류 신호가 둘이면 처음 것만
- 기한 문구: 메일에 근거가 없으면(지어낸 기한) 약속은 기한 없이 남기고, 기한 변경은 버린다. 날짜는 sent_at 기준으로
  `pipeline/dates.py`가 계산하고, 못 정하면 due_at은 null(문구는 남긴다, AI-D11)
- 실패: 모델을 부르지 못하면 신호 없이 fallback에 이유를 적는다. 규칙으로 신호를 만들지 않는다(AI-D19)
"""
import re
import time
import unicodedata

from app.llm.client import LLMClient, LLMError, LLMQuotaError
from app.pipeline.classify import _grounded
from app.pipeline.dates import DueParse, parse_deadline, parse_due_plain
from app.pipeline.evidence import body_sentences
from app.prompts import signals_v1 as prompt
from app.schemas.signals import Commitment, DueChange, Resolved, SignalsRequest, SignalsResponse

MAX_ITEMS = 5  # 종류마다 최대 개수. 메일 한 통에서 그 이상은 모델이 문장을 쪼갠 것이다
MAX_TEXT = 60
MIN_EVIDENCE = 4  # '네.' 같은 조각은 근거가 아니다
EMPTY = ("", "없음", "null", "None", "none", "-")


# 답장 · 전달로 붙은 앞 메일이 시작하는 줄: 구분선(밑줄 · 대시 · 별표 5개 이상, '-----Original Message-----' 포함),
# Outlook 머리글('보낸 사람: · From:'), Gmail 머리글('~님이 작성: · ~ wrote:'), '>'로 시작하는 인용 줄
QUOTE_START = re.compile(r"^[ \t]*(?:[-_*]{5,}|(?:보낸\s*사람|From)\s*:|>|.*(?:님이\s*작성|wrote)\s*:[ \t]*$)", re.M | re.I)
_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"))  # 폭 없는 공백 · BOM · 보이지 않는 하이픈


def own_text(body: str) -> str:
    """이 메일이 쓴 부분: 인용(앞 메일) 시작 줄 위만."""
    m = QUOTE_START.search(body)
    return body[:m.start()] if m else body


def _plain(s: str) -> str:
    """비교용: 보이지 않는 글자를 지우고 전각 글자 · 풀어 쓴 한글(NFD)을 보통 글자로 맞춘다."""
    return unicodedata.normalize("NFKC", s.translate(_INVISIBLE))


def _ws(s: str) -> str:
    return re.sub(r"\s+", "", _plain(s))


def _span(evidence: str, sents: list[str]) -> list[int] | None:
    """근거가 걸친 문장 번호. 한 문장 안이면 그 문장, 이어진 여러 문장에 걸치면 걸친 문장들. 없으면 None."""
    ev = _ws(evidence)
    if len(ev) < MIN_EVIDENCE:
        return None
    flat = [_ws(s) for s in sents]
    for i, s in enumerate(flat):
        if ev in s:
            return [i]
    joined = "".join(flat)
    if ev not in joined:
        return None
    # 여러 문장에 걸친 근거: 근거 글자 범위와 겹치는 문장만
    start = joined.index(ev)
    end, pos, out = start + len(ev), 0, []
    for i, s in enumerate(flat):
        if pos < end and pos + len(s) > start:
            out.append(i)
        pos += len(s)
    return out or None


def ground_evidence(evidence: str, sents: list[str]) -> str | None:
    """모델 근거 → 본문 문장(들)을 줄바꿈으로. 통째로 못 찾으면 줄마다 찾는다(떨어진 두 문장을 줄바꿈으로 이은 근거).
    줄 하나라도 본문에 없으면 None."""
    idx = _span(evidence, sents)
    if idx is None and "\n" in evidence.strip():
        parts = [_span(p, sents) for p in evidence.split("\n") if p.strip()]
        if parts and all(p is not None for p in parts):
            idx = sorted({i for p in parts for i in p})
    return "\n".join(sents[i] for i in idx) if idx else None


def due_of(raw: str, base) -> DueParse | None:
    """기한 문구의 날짜. 마감 표지가 붙은 문구('금요일까지')는 parse_deadline, 표지 없이 날짜만('11/20 · 내일 오전')은 그 날짜."""
    return parse_deadline(raw, base) or parse_due_plain(raw, base)


def _str(v) -> str:
    return "" if v is None else str(v).strip()


def _raw(v) -> str | None:
    s = _str(v)
    return None if s in EMPTY else s


class _Cleaner:
    def __init__(self, req: SignalsRequest):
        self.req = req
        self.sents = body_sentences(own_text(req.mail.body))
        # 기한 문구도 근거 문장처럼 이 메일이 쓴 부분(인용 · 서명 아래 제외)에서만 찾는다. 앞 메일에만 있는 기한이 붙지 않게(#83 리뷰)
        self.mail_text = _ws(f"{req.mail.subject} {own_text(req.mail.body)}").replace("(", "").replace(")", "")
        self.tasks = {t.task_id: t for t in req.open_tasks}
        self.dropped = 0

    def _drop(self) -> None:
        self.dropped += 1

    def _items(self, raw) -> list[dict]:
        if not isinstance(raw, list):
            return []
        out = []
        for x in raw:
            if isinstance(x, dict):
                out.append(x)
            else:
                self._drop()
        return out

    def _grounded(self, raw: str) -> bool:
        return _grounded(_plain(raw), self.mail_text)  # 메일 글자와 같은 방식으로 맞춘 뒤 비교

    def commitments(self, raw) -> list[Commitment]:
        want = "me" if self.req.mail.direction == "sent" else "them"
        out: list[Commitment] = []
        seen: set[tuple[str, str]] = set()
        for c in self._items(raw):
            text, ev = _str(c.get("text"))[:MAX_TEXT], ground_evidence(_str(c.get("evidence")), self.sents)
            if c.get("who") != want or not text or ev is None or len(out) >= MAX_ITEMS or (text, ev) in seen:
                self._drop()
                continue
            seen.add((text, ev))
            due_raw = _raw(c.get("due_raw"))
            if due_raw and not self._grounded(due_raw):
                due_raw = None  # 메일에 없는 기한은 모델이 지어낸 것이다. 약속은 남긴다
            due = due_of(due_raw, self.req.mail.sent_at) if due_raw else None
            out.append(Commitment(who=want, text=text, due_raw=due_raw, due_at=due.due_at if due else None, evidence=ev))
        return out

    def due_changes(self, raw) -> list[DueChange]:
        out: dict[str, DueChange] = {}
        for c in self._items(raw):
            tid, new_raw = _str(c.get("task_id")), _raw(c.get("new_due_raw"))
            ev = ground_evidence(_str(c.get("evidence")), self.sents)
            if tid not in self.tasks or tid in out or not new_raw or not self._grounded(new_raw) or ev is None:
                self._drop()
                continue
            due = due_of(new_raw, self.req.mail.sent_at)
            new_at = due.due_at if due else None
            if new_at is not None and new_at == self.tasks[tid].due_at:
                self._drop()  # 지금 기한과 같으면 바뀐 것이 아니다
                continue
            out[tid] = DueChange(task_id=tid, new_due_raw=new_raw, new_due_at=new_at, evidence=ev)
        return list(out.values())

    def resolved(self, raw) -> list[Resolved]:
        out: dict[str, Resolved] = {}
        for c in self._items(raw):
            tid, reason = _str(c.get("task_id")), c.get("reason")
            ev = ground_evidence(_str(c.get("evidence")), self.sents)
            if tid not in self.tasks or tid in out or reason not in ("done_by_other", "cancelled", "not_needed") or ev is None:
                self._drop()
                continue
            out[tid] = Resolved(task_id=tid, reason=reason, evidence=ev)
        return list(out.values())


KEYS = ("commitments", "due_changes", "resolved", "asks_me_question")


def _shape_ok(out: dict) -> bool:
    """틀만 본다: 네 칸이 모두 있고, 목록 칸은 목록 · 질문 칸은 참 · 거짓."""
    return (all(k in out for k in KEYS) and all(isinstance(out[k], list) for k in KEYS[:3])
            and isinstance(out["asks_me_question"], bool))


def extract(req: SignalsRequest, llm: LLMClient) -> SignalsResponse:
    t0 = time.perf_counter()
    meta = {"mail_id": req.mail_id, "model": getattr(llm, "model", None), "prompt_version": prompt.VERSION}

    def none(kind: str, detail: str | None = None) -> SignalsResponse:
        return SignalsResponse(**meta, source="none", fallback=kind, detail=(detail or None) and detail[:200],
                               elapsed_ms=round((time.perf_counter() - t0) * 1000))

    c = _Cleaner(req)
    if not c.sents:  # 본문이 비었거나 서명 · 인용뿐: 근거로 삼을 문장이 없다
        return none("empty_body")
    try:
        out = llm.chat_json(prompt.SYSTEM, prompt.build_user(req), prompt.SCHEMA)
    except LLMQuotaError as e:
        return none("quota", str(e))
    except LLMError as e:
        return none("model_failed", str(e))
    if not isinstance(out, dict) or not _shape_ok(out):
        return none("bad_output", "모델 답의 틀이 맞지 않음(commitments · due_changes · resolved · asks_me_question)")
    return SignalsResponse(
        **meta, source="exaone",
        commitments=c.commitments(out["commitments"]), due_changes=c.due_changes(out["due_changes"]),
        resolved=c.resolved(out["resolved"]),
        # 보낸 메일은 내가 쓴 것이라 '나에게 온 질문'이 없다(끊긴 대화는 받은 메일로만 판정)
        asks_me_question=out["asks_me_question"] if req.mail.direction == "received" else False,
        dropped=c.dropped, elapsed_ms=round((time.perf_counter() - t0) * 1000),
    )
