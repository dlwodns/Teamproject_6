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
from app.pipeline.dates import parse_due
from app.pipeline.rules.mail_rules_v1 import RULES_VERSION, RuleResult, event_due, judge
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
        due = parse_due(raw, req.received_at) if raw else None
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
    # 회의 참석은 회의 일시가 기한이다. 모델이 기한을 비우면 규칙이 읽은 회의 시각을 쓴다
    if types[0] == "일정참석" and (ev := event_due(req)):
        for t in tasks:
            if t.due_at is None:
                t.due_raw, t.due_at = ev.raw, ev.due_at
    if r.tasks and tasks:  # 둘 다 할 일을 찾았으면 유형은 규칙(문장 단서)을 따르고 할 일 문구 · 기한은 모델 것을 쓴다
        types = r.action_types
        for t in tasks:  # 모델이 기한을 비운 할 일은 문구가 가장 닮은 규칙 할 일의 기한을 쓴다('함께 보내 주세요' → 같은 기한)
            if t.due_at is None:
                best = max(r.tasks, key=lambda rt: len(_bigrams(rt.text + rt.evidence) & _bigrams(t.text)))
                one_to_one = len(r.tasks) == 1 and len(tasks) == 1  # 둘 다 할 일 1개면 같은 요청이다(v3.2, dev M-0097 '작성 여부 회신' ↔ '퇴근 전에')
                if best.due and (one_to_one or _bigrams(best.text + best.evidence) & _bigrams(t.text)):
                    t.due_raw, t.due_at = best.due.raw, best.due.due_at
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
               model_types: list[str], moved: list[TaskOut], cand: set[str] | None = None) -> tuple[list[str], list[TaskOut]]:
    """엑사원 합치기 뒤 유형 · 칸을 kind로 고친다(v3.2). 11/3 dev3 실측: 둘 다 할 일을 찾으면 규칙 유형을 쓰는 옛 합치기 때문에
    60통을 모두 엑사원에 보내도 결과가 한 통도 바뀌지 않았다 → 유형은 kind 형식이 정하고, 애매할 때만 엑사원이 후보 안에서 고른다."""
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


def classify(req: ClassifyRequest, llm: LLMClient, settings: Settings) -> ClassifyResponse:
    r = judge(req)
    k = kinds.classify_kind(req, r)
    types, tasks = _from_rules(r)
    if _sure(k):  # kind가 확신하면 유형은 kind. 애매한 메일의 규칙 경로 유형은 규칙 그대로 둔다
        types = kinds.kind_types(k, r.action_types)  # (11/3 애매 24통 kind 1등 19 · 규칙 11이지만 dev+dev2만은 7 · 7이고 dev 완전 정답 97→95)
    mentioned, urgent, follow_up = r.mentioned_me, r.urgent, r.is_follow_up
    source, fallback, prompt_version = "rule", None, None
    moved: list[TaskOut] = []  # 엑사원 할 일 중 확인 칸으로 옮긴 것

    if route(r, k, settings.router_threshold):  # AI-3 라우터
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
            types, tasks = _with_kind(types, tasks, k, r, model_types, moved, cand)
            # 지목은 받는사람이 나이거나 규칙이 본문에서 나를 찾았을 때다. 모델은 지목 · 긴급을 거의 늘 true로 냈다(11/3 dev)
            mentioned = r.mentioned_me or r.recipient == "to"
            source, prompt_version = "exaone", PROMPT.PROMPT_VERSION
        except LLMError as e:
            fallback = str(e)  # ai 장애여도 규칙 결과는 낸다
            moved.clear()

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
