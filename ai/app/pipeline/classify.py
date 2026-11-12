"""분류 파이프라인: 규칙 → 메일 성격(kind) → 라우터 → (애매하면) 엑사원 → 후처리 (AI-2~AI-6, 구조도 4절).

v3.2(11/3, 사용자 항목 1 · 3): 할 일 탐지(재현율)는 규칙 v1.5, 유형 · 칸은 kind 형식 점수기(pipeline/kinds.py)가 정한다.
- 라우터(문지기): kind가 애매하거나, 규칙 확신도가 낮은데 kind가 '할 일 없음'을 확신하지 못하면 엑사원으로 보낸다.
- 합치기: kind가 확신하면 유형은 kind를 따른다(엑사원 유형을 받지 않음). 애매하면 엑사원 유형을 kind 후보 안에서만 받는다.
"""
import os
import re

from app.core.config import Settings
from app.llm.client import LLMClient, LLMError
from app.pipeline import checks, kinds, priority
from app.pipeline.dates import parse_deadline
from app.pipeline.rules.mail_rules_v1 import NO_ACTION, REPLY_SUBJECT, RULES_VERSION, RuleResult, event_due, judge, strip_body
from app.prompts import classify_v3, classify_v5

# 지금 쓰는 분류 프롬프트. 평가 실행기도 이 값으로 버전을 적는다. v5(형식 후보 안에서 고르기)는 실측 비교용 후보안이다
PROMPT = classify_v5 if os.environ.get("CLASSIFY_PROMPT", "").strip() == "v5" else classify_v3
from app.schemas.classify import ClassifyRequest, ClassifyResponse, TaskOut

NO_TASK_TYPES = {"공지", "참조", "회신", "기타"}
CATEGORY = {"회신요청": "회신", "자료제출요청": "요청", "수정재전송요청": "요청", "일정참석": "요청",
            "검토승인요청": "검토", "공지": "공지", "참조": "기타", "회신": "기타", "기타": "기타"}  # D39 묶음


def _category(types: list[str], has_tasks: bool) -> str:
    # 공지 속 나를 지목한 요청은 '요청' 업무다(D40)
    first = next((t for t in types if t not in NO_TASK_TYPES), types[0]) if has_tasks else types[0]
    return CATEGORY[first]


def _from_rules(r: RuleResult) -> tuple[list[str], list[TaskOut]]:
    tasks = [TaskOut(text=t.text, format=t.format, due_raw=t.due.raw if t.due else None,
                     due_at=t.due.due_at if t.due else None, evidence=t.evidence) for t in r.tasks]
    return r.action_types, tasks


GENERIC_TASK = re.compile(r"^\S{0,8}\s*(?:내용\s*|결과\s*)?(?:확인|검토)$")  # '결과 검토'처럼 대상 · 산출물 없는 할 일


def _bigrams(text: str) -> set[str]:
    t = re.sub(r"\s+", "", text)
    return {t[i:i + 2] for i in range(len(t) - 1)}


def _squash(text: str) -> str:
    return re.sub(r"[\s()]+", "", text)


def _external(req: ClassifyRequest) -> bool:
    """보낸 사람 도메인이 메일함 주인과 다르면 사외 메일이다."""
    def dom(a: str) -> str:
        return a.rsplit("@", 1)[-1].strip("<> ").lower()
    return "@" in req.from_ and "@" in req.owner.email and dom(req.from_) != dom(req.owner.email)


def _kbigrams(text: str) -> set[str]:
    """한글만 남긴 bigram. 숫자('10월' · '10/23')와 기호가 겹쳐 보이지 않게 한다."""
    return _bigrams(re.sub(r"[^가-힣]", "", text))


def _context(raw: str, req: ClassifyRequest) -> str:
    """모델 기한 글자가 나온 원문 자리 + 뒤 10글자('10/22(목)' → '10/22(목)까지 보내'). 못 찾으면 글자 그대로.
    근거 확인(_squash)과 같은 기준으로 찾는다: 띄어쓰기 · 괄호만 다른 '10/22 (목)'도 원문 '10/22(목)' 자리를 찾는다(#21 리뷰)."""
    core = _squash(raw)
    if not core:
        return raw
    pat = re.compile(r"[\s()]*".join(map(re.escape, core)))
    for text in (req.body, req.subject):
        if (m := pat.search(text)):
            return text[max(0, m.start() - 20): m.end() + 10]
    return raw


def _fill_event_due(types: list[str], tasks: list[TaskOut], req: ClassifyRequest) -> None:
    """회의 참석 할 일은 회의 일시가 기한이다. 기한 문구가 아예 없을 때만 채운다(규칙 · 엑사원 경로 공통)."""
    if types and types[0] == "일정참석" and (ev := event_due(req)):
        for t in tasks:
            if t.due_at is None and not t.due_raw:
                t.due_raw, t.due_at = ev.raw, ev.due_at


SAME_REQUEST = 0.5  # 엑사원 할 일 문구의 한글 bigram 중 이 비율 이상이 규칙 요청 문장에 있으면 같은 요청으로 본다


def _share(rule_text: str, task_text: str) -> float:
    """엑사원 할 일 문구(task_text)의 한글 bigram 중 규칙 요청 문장(rule_text)에도 있는 비율."""
    kt = _kbigrams(task_text)
    return len(_kbigrams(rule_text) & kt) / max(len(kt), 1)


def _rule_due_first(r: RuleResult, tasks: list[TaskOut]) -> None:
    """v1.8: 규칙은 요청 문장에 붙은 기한을 읽는다. 둘 다 기한을 찾았으면 규칙 기한을 먼저 쓴다
    (11/5 dev M-0060: 요청 문장은 '오늘 중으로', 엑사원은 고객 쪽 사정 '내일 오전까지'를 골랐다).

    #21 리뷰: 엑사원 기한이 있는 할 일은 같은 요청일 때만 덮는다. 규칙 요청 문장은 문장 전체라 '자료' 같은 단어 하나만
    겹쳐도 다른 요청('발표 자료 공유')의 기한이 바뀌었다 → 둘 다 할 일 1개이거나, 규칙 할 일 하나당 가장 닮은 엑사원 할 일
    하나(한글 bigram SAME_REQUEST 이상)만 덮는다. 엑사원이 기한을 비운 할 일은 v3.2처럼 가장 닮은 규칙 할 일 기한으로 채운다."""
    one_to_one = len(r.tasks) == 1 and len(tasks) == 1  # 둘 다 할 일 1개면 같은 요청이다(v3.2, dev M-0097 '작성 여부 회신' ↔ '퇴근 전에')
    dated = [t for t in tasks if t.due_at is not None or t.due_raw]
    taken: set[int] = set()
    for rt in r.tasks:
        if not rt.due or not dated:
            continue
        rule_text = rt.text + " " + rt.evidence
        t = max(dated, key=lambda x: _share(rule_text, x.text))
        if id(t) not in taken and (one_to_one or _share(rule_text, t.text) >= SAME_REQUEST):
            t.due_raw, t.due_at = rt.due.raw, rt.due.due_at
            taken.add(id(t))
    for t in tasks:
        if t.due_at is not None or t.due_raw:
            continue
        best = max(r.tasks, key=lambda rt: len(_bigrams(rt.text + rt.evidence) & _bigrams(t.text)))
        if best.due and (one_to_one or _bigrams(best.text + best.evidence) & _bigrams(t.text)):
            t.due_raw, t.due_at = best.due.raw, best.due.due_at


def _from_model(out: dict, req: ClassifyRequest, r: RuleResult,
                moved: list[TaskOut] | None = None) -> tuple[list[str], list[TaskOut]]:
    """엑사원 출력을 규칙 결과와 합친다. 모델은 '할 일이 있나 · 무엇인가'를 보고, 정의로 정해지는 칸은 규칙을 따른다(AI-5).
    11/3 dev · dev2 엑사원 경로 오답 기준. 긴급 · 재요청 · 지목은 모델 값을 쓰지 않는다(classify).
    할 일에서 뺀 읽을거리는 버리지 않고 moved에 담는다 → 확인 칸(checks.build, 사용자 항목 2)."""
    moved = [] if moved is None else moved
    types = [t for t in out.get("action_types") or [] if t in PROMPT.ACTION_TYPES] or ["기타"]
    mail_text = _squash(f"{req.subject} {req.body}")
    tasks = []
    for t in out.get("tasks") or []:
        if not isinstance(t, dict) or not str(t.get("action", "")).strip():
            continue
        raw = str(t.get("due_raw") or "").strip()
        raw = None if raw in ("", "없음", "null", "None") else raw
        if raw and _squash(raw) not in mail_text:  # 메일에 없는 기한 글자는 모델이 지어낸 것이다(근거 검증). 날짜 계산은 코드가 한다
            raw = None
        # v1.7: 모델이 고른 날짜가 기한인지 메일 원문 앞뒤로 다시 본다. 마감 표지가 없으면 일정 · 지난 일('금요일에 보내드린') 날짜다
        due = parse_deadline(_context(raw, req), req.received_at) if raw else None
        raw = due.raw if due else None
        fmt = str(t.get("format") or "").strip()
        tasks.append(TaskOut(text=str(t["action"]).strip()[:80], due_raw=raw, due_at=due.due_at if due else None,
                             format=None if fmt in ("", "없음") else fmt))
    # 벤치 후처리 P1: 참조로만 받았고 규칙이 지목을 못 찾으면 업무를 만들지 않는다
    if r.recipient == "cc" and not r.mentioned_me:
        types, tasks = ["참조"], []
    # 공지는 사내 부서가 보내는 안내다. 사외 메일을 공지 · 참조로 고르면 홍보 · 초청(기타)이고 할 일이 아니다
    if _external(req) and types[0] in ("공지", "참조"):
        types, tasks = ["기타"], []
    # 모델이 '회신 · 참조 · 기타'를 맨 앞에 두고 붙인 할 일은 '~ 확인 · 준비' 같은 읽을거리였다(11/3 dev2 회신 메일 4통).
    # 규칙도 요청 문장을 못 찾았을 때만 뺀다. 공지 맨 앞은 '공지 속 지목 요청'일 수 있어 남긴다(D15 · 프롬프트 규칙2)
    if tasks and not r.tasks and types[0] in NO_TASK_TYPES - {"공지"}:
        moved.extend(tasks)  # 전에는 버렸다. 확인 칸으로 옮긴다
        tasks = []
    # 규칙도 나를 향한 요청을 못 찾았고 모델 할 일이 모두 기한 없는 '~ 확인 · 참고'뿐이면 할 일이 아니라 확인할 것이다(AI-T5).
    # 기한이 있거나 규칙이 요청을 찾았으면 옮기지 않는다(D15). 회의 일시로 기한을 채우기 전에 본다
    if tasks and not r.tasks and all(checks.read_only(t) for t in tasks):
        moved.extend(tasks)
        tasks = []
    # 같은 당부를 쪼갠 '결과 검토' 같은 빈 할 일은 다른 할 일이 있을 때만 뺀다(메일 단위 누락은 생기지 않는다)
    if len(tasks) > 1:
        tasks = [t for t in tasks if t.due_at or not GENERIC_TASK.match(t.text)] or tasks[:1]
    # 회의 일시 채우기는 최종 유형이 정해진 뒤 한 번만 한다(_fill_event_due). 여기서 채우면 유형이 바뀐 할 일에 회의 날짜가 남는다(v1.7)
    if r.tasks and r.not_mine and len(tasks) > len(r.tasks):
        # v1.7 상호보완: 규칙이 '나를 향하지 않았다'고 본 요청 문장('전 임직원은 ~ 실행해 주십시오')을 모델이 할 일로 더 만들었으면
        # 그 할 일은 확인 칸으로 옮긴다. 할 일 수는 규칙이 찾은 수보다 줄지 않는다(11/5 dev2 M-0008 · M-0033)
        def near(t, texts):
            return max((_share(x, t.text) for x in texts), default=0)
        mine = [rt.text + " " + rt.evidence for rt in r.tasks]
        ranked = sorted(tasks, key=lambda t: near(t, r.not_mine) - near(t, mine), reverse=True)
        for t in ranked[: len(tasks) - len(r.tasks)]:
            if near(t, r.not_mine) > near(t, mine):
                moved.append(t)
                tasks = [x for x in tasks if x is not t]
    if r.tasks and tasks:  # 둘 다 할 일을 찾았으면 유형은 규칙(문장 단서)을 따르고 할 일 문구 · 기한은 모델 것을 쓴다
        types = r.action_types
        _rule_due_first(r, tasks)
        # v1.8: 규칙이 찾은 회의 참석 할 일을 모델이 빠뜨렸으면 더한다(회의 초대 + 자료 요청 메일 → 할 일 2개)
        attend = next((rt for rt in r.tasks if rt.action_type == "일정참석"), None)
        if attend and not any(re.search(r"참석|회의|미팅|보고회|간담회|워크숍", t.text) for t in tasks):
            tasks.insert(0, _from_rules(RuleResult(["일정참석"], [attend], r.mentioned_me, r.urgent, r.is_follow_up,
                                                   r.recipient, r.confidence))[1][0])
    elif not tasks and not r.tasks and r.action_types[0] in NO_TASK_TYPES:
        types = r.action_types  # 할 일 없음 유형(회신 · 공지 · 참조 · 기타)은 수신 방식 · 제목 단서로 정한 규칙 쪽이 맞았다
    # 누락 방지(D15): 모델이 업무를 비웠어도 규칙이 나를 향한 요청 문장을 찾았으면 규칙 업무를 남긴다
    if not tasks and r.tasks:
        types, tasks = _from_rules(r)
    return types, tasks


def _sure(k: kinds.KindResult) -> bool:
    return k.kind is not None and not k.needs_model


def _candidates(k: kinds.KindResult) -> set[str]:
    """kind가 애매할 때 엑사원 유형을 받아들일 후보: 1등 · 2등 · 부모가 다른 1등 kind의 부모 유형."""
    if k.kind is None:
        return set(kinds.ACTION_TYPES)
    ranked = sorted(k.scores.items(), key=lambda kv: -kv[1])
    out = {k.kind.parent}
    for kid, _ in ranked[1:]:
        p = kinds.BY_ID[kid].parent
        out.add(p)
        if p != k.kind.parent:  # 부모가 다른 1등까지
            break
    return out


def _with_kind(types: list[str], tasks: list[TaskOut], k: kinds.KindResult, r: RuleResult,
               model_types: list[str], moved: list[TaskOut], cand: set[str] | None = None,
               all_mode: bool = False) -> tuple[list[str], list[TaskOut]]:
    """엑사원 합치기 뒤 유형 · 칸을 kind로 고친다(v3.2). 11/3 dev3 실측: 둘 다 할 일을 찾으면 규칙 유형을 쓰는 옛 합치기 때문에
    60통을 모두 엑사원에 보내도 결과가 한 통도 바뀌지 않았다 → 유형은 kind 형식이 정하고, 애매할 때만 엑사원이 후보 안에서 고른다."""
    if _sure(k) and all_mode and r.tasks and tasks and k.kind.lane == "할 일" and all(t.specific for t in r.tasks):
        # v1.8: 요청 문장에 유형을 콕 집는 단서가 있으면(이름만 보내 주세요 → 회신, 재제출 → 수정재전송, 와 주세요 → 참석)
        # 형식(kind) 부모보다 문장을 따른다. 일반 단어('보내 주세요' · '확인')만 있으면 형식이 더 잘 맞혔다(dev2 · dev3 4통)
        return list(r.action_types), tasks
    if _sure(k):
        # 할 일 없는 형식(완료 보고 · 회신 · 공지 · 홍보 …)을 확신하고 규칙도 요청을 못 찾았으면, 엑사원 할 일 중 기한 없는 것은
        # 확인 칸으로 옮긴다(사용자 항목 2). 기한이 있는 할 일은 남긴다(D15)
        if k.kind.lane != "할 일" and not r.tasks and tasks:
            keep = [t for t in tasks if t.due_at]
            moved.extend(t for t in tasks if not t.due_at)
            tasks = keep
            if tasks:  # 기한 있는 할 일이 남았다 → '할 일 없음' 형식이 틀렸을 수 있다. 유형은 엑사원 쪽을 둔다
                return types, tasks
        return kinds.kind_types(k, r.action_types if r.tasks else types), tasks
    cand = cand or _candidates(k)
    if all_mode and r.tasks and tasks and not any(t.weak_type for t in r.tasks):
        # v1.7 상호보완: 형식이 애매할 때 규칙이 요청 문장 속 유형 단어('다시 제출' · '결재')로 정한 유형이 후보 안이면 규칙을 따른다.
        # 모델 유형은 규칙 유형 단어가 없을 때(약함)만 쓴다
        return list(r.action_types), tasks
    if model_types and model_types[0] in cand:
        head = model_types[0]
        return [head, *[t for t in types if t != head]], tasks
    if k.kind is not None:  # 엑사원이 후보 밖 유형을 냈다 → kind 1등을 따른다
        return kinds.kind_types(k, r.action_types if r.tasks else types), tasks
    return types, tasks


def route(r: RuleResult, k: kinds.KindResult, threshold: float) -> bool:
    """문지기 라우터(v3.2): kind가 애매하면 보낸다. 규칙 확신도가 기준 미만이어도 kind가 '할 일 없음'을 확신하고
    나를 향한 요청 문장이 없으면 보내지 않는다(dev · dev2 · dev3 207통에서 건너뛴 메일 중 정답 할 일 메일 0통)."""
    sure_no_task = _sure(k) and k.kind.lane != "할 일" and "request_loose" not in k.signals.on
    # 규칙이 '지목 불확실한 요청'을 본 메일은 kind 칸이 '확인'일 때만 건너뛴다 — 확인 칸에 '해당 여부 확인'으로 떠서
    # 사용자가 볼 수 있다. '참고' 칸이면 어디에도 안 뜨므로 엑사원에 묻는다(보수적, D15)
    if "지목 불확실한 요청" in r.reasons and k.kind is not None and k.kind.lane != "확인":
        sure_no_task = False
    return k.needs_model or (r.confidence < threshold and not sure_no_task)


def _no_action_said(req: ClassifyRequest) -> bool:
    """'참고만 해 주세요' · '하실 일은 없습니다'처럼 할 일이 없다고 밝혔나. '없으면 회신하지 않으셔도'처럼 조건이 붙은 문장은 아니다."""
    for ln in strip_body(req.body):
        for sent in re.split(r"(?<=[.?!])\s+", ln):
            if NO_ACTION.search(sent) and not re.search(r"(?:없|않|있)으면|경우|이면", sent):
                return True
    return False


TASK_TYPES = [t for t in CATEGORY if t not in NO_TASK_TYPES]


def _consistent(types: list[str], tasks: list[TaskOut], r: RuleResult, model_types: list[str], k, subject: str = "") -> list[str]:
    """v1.8: 유형과 할 일 여부를 맞춘다(11/5 test · test3 주 유형 오답 7통: 할 일이 있는데 '기타 · 참조', 없는데 '회신요청').
    - 할 일이 있으면 주 유형은 할 일 유형(공지 속 요청이면 '공지' 다음). 할 일 수보다 많은 요청 유형은 붙이지 않는다
    - 할 일이 없으면 할 일 없는 유형만 남긴다"""
    kind_parent = k.kind.parent if k.kind else None
    if tasks:
        pool = [t.action_type for t in r.tasks if not t.weak_type] + [t for t in types if t in TASK_TYPES] + \
               [t for t in model_types if t in TASK_TYPES] + ([kind_parent] if kind_parent in TASK_TYPES else []) + \
               [t.action_type for t in r.tasks] + ["회신요청"]
        task_types = []
        for t in [x for x in types if x in TASK_TYPES] or pool:
            if t not in task_types:
                task_types.append(t)
        if not task_types:
            task_types = [next(t for t in pool if t in TASK_TYPES)]
        task_types = task_types[: max(len(tasks), 1)]
        notice = "공지" in types or (r.action_types and r.action_types[0] == "공지")
        return (["공지"] if notice and r.tasks else []) + task_types
    # 할 일 없는 유형은 수신 방식 · 제목으로 정한 규칙이 맞았다(회신 제목 · 단체 공지 · 참조). 규칙이 근거 없이 정한 '기타'면 형식 · 합친 결과
    rule_nt = [t for t in r.action_types if t in NO_TASK_TYPES]
    kind_nt = [kind_parent] if (kind_parent in NO_TASK_TYPES and _sure(k)) else []
    # 합친 결과의 '회신'은 회신 제목이거나 형식 1등이 회신 계열(완료 보고 · 자료 회신)일 때만 받는다(test '[회의 취소] ~'를 회신으로 냈다)
    reply_ok = bool(REPLY_SUBJECT.match(subject)) or kind_parent == "회신" or PROMPT is classify_v5
    merged_nt = [t for t in types if t in NO_TASK_TYPES and (t != "회신" or reply_ok)]
    # 규칙의 '기타'가 근거 없이 정한 값(요청 표현 없음 · 단체 수신)이면 합친 결과를 먼저 본다. 사내 소식 · 자동회신 같은 근거가 있으면 규칙
    rule_weak = bool(rule_nt) and rule_nt[0] == "기타" and any(x in r.reasons for x in ("요청 표현 없음", "단체 수신", "공유 · 회신성"))
    pool = kind_nt or (rule_nt if rule_nt and not rule_weak else []) or merged_nt or rule_nt or ["기타"]
    return pool[:1] + [t for t in pool[1:] if t in NO_TASK_TYPES]


def wants_model(r: RuleResult, k: kinds.KindResult, settings: Settings) -> bool:
    """엑사원에 물을지. all이면 늘 묻는다(11/5 사용자 결정), gate면 문지기 라우터."""
    return settings.router_mode == "all" or route(r, k, settings.router_threshold)


def classify(req: ClassifyRequest, llm: LLMClient, settings: Settings) -> ClassifyResponse:
    r = judge(req)
    k = kinds.classify_kind(req, r)
    types, tasks = _from_rules(r)
    if _sure(k):  # kind가 확신하면 유형은 kind. 애매한 메일의 규칙 경로 유형은 규칙 그대로 둔다
        types = kinds.kind_types(k, r.action_types)  # (11/3 애매 24통 kind 1등 19 · 규칙 11이지만 dev+dev2만은 7 · 7이고 dev 완전 정답 97→95)
    mentioned, urgent, follow_up = r.mentioned_me, r.urgent, r.is_follow_up
    source, fallback, prompt_version = "rule", None, None
    model_types: list[str] = []
    moved: list[TaskOut] = []  # 엑사원 할 일 중 확인 칸으로 옮긴 것

    if wants_model(r, k, settings):  # AI-3 라우터 · v1.7 전부 엑사원
        try:
            if PROMPT is classify_v5:  # 형식 후보 · 규칙 요청을 넘기고 kind enum을 후보로 좁힌다
                out = llm.chat_json(PROMPT.SYSTEM, PROMPT.render_user(req, r.recipient, k, [t.text for t in r.tasks]),
                                    PROMPT.schema_for(k))
                picked = kinds.BY_ID.get(str(out.get("kind")))
                out = {**out, "action_types": [picked.parent] if picked else []}
            else:
                out = llm.chat_json(PROMPT.SYSTEM, PROMPT.render_user(req, r.recipient), PROMPT.SCHEMA)
            types, tasks = _from_model(out, req, r, moved)
            model_types = [t for t in out.get("action_types") or [] if t in PROMPT.ACTION_TYPES]
            cand = {kinds.BY_ID[x].parent for x in classify_v5.candidates(k)} if PROMPT is classify_v5 else None
            types, tasks = _with_kind(types, tasks, k, r, model_types, moved, cand, settings.router_mode == "all")
            if tasks and not r.tasks and (
                    (_sure(k) and k.kind.id == "K18" and r.not_mine)
                    or (r.optional and not r.not_mine)
                    or _no_action_said(req)):
                # v1.8: 규칙이 '미이수자는 · 해당자는' 당부로 판정했고 형식도 '대상자 당부 공지'를 확신하는 메일,
                # 또는 '참고만 해 주세요 · 하실 일은 없습니다'라고 밝힌 메일에서 엑사원만 만든 할 일은 확인 칸으로(dev 5 · test3 2통)
                moved.extend(tasks)
                tasks = []
            # 엑사원만 찾은 할 일을 '요청 신호 없음 · 할 일 없는 형식'이라는 이유로 확인 칸으로 옮기는 안은 넣지 않았다(11/5):
            # dev에서는 오탐만 줄었지만 시험 세트에서 할 일 메일 누락이 test 0 → 6 · test3 1 → 4로 늘었다(D15 위반).
            # 엑사원만 찾은 할 일은 기한 없는 읽기 할 일(read_only)만 확인 칸으로 보낸다(기존 규칙)
            # 지목은 받는사람이 나이거나 규칙이 본문에서 나를 찾았을 때다. 모델은 지목 · 긴급을 거의 늘 true로 냈다(11/3 dev)
            mentioned = r.mentioned_me or r.recipient == "to"
            source, prompt_version = "exaone", PROMPT.PROMPT_VERSION
        except LLMError as e:
            fallback = str(e)  # ai 장애여도 규칙 결과는 낸다
            moved.clear()

    types = _consistent(types, tasks, r, model_types if source == "exaone" else [], k, req.subject)
    _fill_event_due(types, tasks, req)  # 규칙 경로도 회의 참석이면 회의 일시를 기한으로(v1.7, kind가 유형을 일정참석으로 바꾼 경우)
    mentioned = mentioned and bool(tasks)  # 지목은 나에게 할 일이 있을 때만이다(라벨 기준). 모델은 거의 늘 true를 낸다

    pts = priority.score(superior_or_favorite=req.sender.is_superior or req.sender.is_favorite,
                         dues=[t.due_at for t in tasks if t.due_at], received_at=req.received_at,
                         urgent=urgent, follow_up=follow_up, recipient=r.recipient)
    chk = checks.build(req, r, types, tasks, moved, k if _sure(k) else None)
    return ClassifyResponse(
        mail_id=req.mail_id, category=_category(types, bool(tasks)), action_types=types, tasks=tasks,
        checks=chk, kind=k.kind.id if k.kind else None, kind_name=k.kind.name if k.kind else None,
        kind_sure=_sure(k), lane="할 일" if tasks else "확인" if chk else "참고",
        mentioned_me=mentioned, urgent=urgent, is_follow_up=follow_up, priority=priority.level(pts),
        source=source, confidence=r.confidence, model=llm.model if source == "exaone" else None,
        prompt_version=prompt_version, rules_version=RULES_VERSION, fallback=fallback,
    )
