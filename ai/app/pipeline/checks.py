"""확인 칸(checks, 사용자 항목 2 · 11/3). 할 일은 아니지만 내가 읽고 확인할 메일을 할 일 목록과 따로 둔다.

엑사원은 할 일 없는 회신 · 완료 보고 · 안내에 '~ 확인' 할 일을 만들었다(AI-T5). 버리면 정보를 잃고, 할 일로 두면 Task 정밀도가 떨어진다
→ 할 일 대신 확인 칸으로 보낸다. 할 일이 남은 메일에는 확인 항목을 만들지 않는다(같은 메일이 두 칸에 뜨지 않게).

확인 칸에 넣는 것 (dev · dev2 · dev3 할 일 없음 메일 87통으로 범위를 정했다. 넓으면 칸이 의미 없다):
- 완료 보고: 나에게(받는사람) 온 완료 · 반영 · 처리 알림. 회신 제목이 아니어도(dev3 '[보고] ~ 반영 완료')
- 결과 회신: 나에게 온 회신 메일. 내 요청에 대한 답이라 결과를 확인한다(참조로 받은 회신은 넣지 않는다)
- 해당 여부 확인: 단체 메일의 '미이수자 · 해당자 · 전 직원' 당부. 내가 해당하는지 확인한다(규칙 v1.4 '확인할 공지')
- 읽고 확인: 엑사원이 만든 할 일 중 규칙 근거가 없어 옮긴 것. 받는 방식과 상관없이 버리지 않는다
넣지 않는 것: 일반 공지(점검 · 행사 · 제도 안내), 참조 수신, 사외 홍보 · 뉴스레터 — 참고만 하면 된다.

엑사원 할 일을 옮기는 조건(`read_only` · classify._from_model). 누락 방지(D15)가 먼저다:
- 규칙이 나를 향한 요청 문장을 못 찾았고, 모델이 낸 기한이 없고, 할 일 문구의 동사가 모두 읽기(확인 · 참고 · 숙지)뿐일 때만.
  '확인 및 회신' · '검토' · '준비'처럼 다른 동사가 하나라도 있으면 할 일로 둔다. 할 일 여러 개 중 일부만 읽기면 옮기지 않는다.
"""
import re

from app.pipeline.rules.mail_rules_v1 import ANSWER, GENERAL_AUDIENCE, REQUEST, RuleResult, strip_body
from app.schemas.classify import CheckOut, ClassifyRequest, TaskOut

COMPLETION = re.compile(r"완료(?:되었|됐|했|하였)|마쳤|끝났|끝냈|반영(?:되었|됐|했|하였)|처리(?:되었|됐|했|하였)|조치(?:되었|됐|했|하였)")
SUBJECT_PREFIX = re.compile(r"^\s*(?:(?:RE|Re|re|FW|Fw|FWD|Fwd|회신|전달)\s*:\s*|\[[^\]]*\]\s*)+")
# 할 일 문구를 '및 · 후 · 하고 · 쉼표'로 나눈 각 조각의 끝 동사가 읽기 동사인지 본다('반영 결과 확인' → 확인, '확인 및 회신' → 확인 · 회신)
JOINER = re.compile(r"\s+(?:및|후|뒤|그리고|또는)\s+|(?:하고|한\s*뒤|한\s*후|후에)\s+|\s*[,·/]\s*")
READ_HEAD = re.compile(r"(?:확인|참고|숙지|열람|인지|파악)(?:하기|함|할\s*것|\s*필요)?$")


def read_only(t: TaskOut) -> bool:
    """기한이 없고 동사가 모두 읽기뿐인 할 일('공지 내용 확인' · '반영 결과 확인')."""
    if t.due_raw or t.due_at:
        return False
    parts = [p.strip(" .") for p in JOINER.split(t.text) if p and p.strip(" .")]
    return bool(parts) and all(READ_HEAD.search(p) for p in parts)


def _sentences(req: ClassifyRequest) -> list[str]:
    return [s.strip() for ln in strip_body(req.body) for s in re.split(r"(?<=[.?!])\s+", ln) if s.strip()]


def gist(subject: str, sents: list[str]) -> str:
    """제목 요지: 회신 · 전달 표시와 머리말([공지] 등) · 끝 괄호를 뺀 제목. 비면 본문 첫 문장."""
    g = re.sub(r"\s*\([^)]*\)\s*$", "", SUBJECT_PREFIX.sub("", subject)).strip()
    return (g or (sents[0] if sents else ""))[:80]


KIND_REASON = {"K12": "완료 보고", "K13": "결과 회신", "K18": "해당 여부 확인", "K21": "시스템 알림"}  # kinds.py에서 칸이 '확인'인 kind


def build(req: ClassifyRequest, r: RuleResult, types: list[str], tasks: list[TaskOut], moved: list[TaskOut],
          kind=None) -> list[CheckOut]:
    """최종 유형 · 할 일이 정해진 뒤 확인 항목을 만든다. 할 일이 있으면 만들지 않는다.
    kind(v3.2, 확신한 kind 결과)가 있으면 칸은 kind 표를 따른다: '확인' 칸 kind면 확인 항목, '참고' 칸 kind면 옮긴 할 일이 있을 때만."""
    if tasks:
        return []
    sents = _sentences(req)
    if kind is not None and kind.kind.lane != "할 일":
        k = kind.kind
        ev = kind.signals.evidence
        if moved:
            text = " · ".join(dict.fromkeys(t.text for t in moved))[:80]
            return [CheckOut(text=text, reason=KIND_REASON.get(k.id, "읽고 확인"), evidence=None, source="exaone")]
        if k.lane == "확인":
            evidence = next((ev[s] for s in ("done_word", "answer_word", "general_audience", "alert_word") if s in ev), None)
            return [CheckOut(text=gist(req.subject, sents), reason=KIND_REASON.get(k.id, "읽고 확인"), evidence=evidence)]
        return []
    done = next((s for s in sents if COMPLETION.search(s)), None) if r.recipient == "to" else None
    audience = next((s for s in sents if GENERAL_AUDIENCE.search(s) and REQUEST.search(s)), None) if r.recipient == "list" else None
    if moved:  # 엑사원 할 일을 옮긴 것은 받는 방식과 상관없이 남긴다(버리지 않는다)
        reason = ("완료 보고" if done else "결과 회신" if types[0] == "회신" and r.recipient == "to"
                  else "해당 여부 확인" if audience else "읽고 확인")
        text = " · ".join(dict.fromkeys(t.text for t in moved))[:80]
        return [CheckOut(text=text, reason=reason, evidence=done or audience, source="exaone")]
    if done:
        return [CheckOut(text=gist(req.subject, sents), reason="완료 보고", evidence=done)]
    if types[0] == "회신" and r.recipient == "to":
        ans = next((s for s in sents if ANSWER.search(s)), sents[0] if sents else None)
        return [CheckOut(text=gist(req.subject, sents), reason="결과 회신", evidence=ans)]
    if audience:
        return [CheckOut(text=gist(req.subject, sents), reason="해당 여부 확인", evidence=audience)]
    return []
