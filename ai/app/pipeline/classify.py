"""분류 파이프라인: 규칙 → 라우터 → (확신도 낮으면) 엑사원 → 후처리 (AI-2~AI-6, 구조도 4절)."""
from app.core.config import Settings
from app.llm.client import LLMClient, LLMError
from app.pipeline import priority
from app.pipeline.dates import parse_due
from app.pipeline.rules.mail_rules_v1 import RULES_VERSION, RuleResult, judge
from app.prompts import classify_v1
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


def _from_model(out: dict, req: ClassifyRequest, r: RuleResult) -> tuple[list[str], list[TaskOut], bool, bool, bool]:
    types = [t for t in out.get("action_types") or [] if t in classify_v1.ACTION_TYPES] or ["기타"]
    tasks = []
    for t in out.get("tasks") or []:
        if not isinstance(t, dict) or not str(t.get("action", "")).strip():
            continue
        raw = str(t.get("due_raw") or "").strip()
        raw = None if raw in ("", "없음", "null", "None") else raw
        due = parse_due(raw, req.received_at) if raw else None
        fmt = str(t.get("format") or "").strip()
        tasks.append(TaskOut(text=str(t["action"]).strip()[:80], due_raw=raw, due_at=due.due_at if due else None,
                             format=None if fmt in ("", "없음") else fmt))
    # 벤치 후처리 P1: 참조로만 받았고 지목이 없으면 업무를 만들지 않는다
    if r.recipient == "cc" and not r.mentioned_me and not out.get("mentioned_me"):
        types, tasks = ["참조"], []
    # 누락 방지(D15): 모델이 업무를 비웠어도 규칙이 나를 향한 요청 문장을 찾았으면 규칙 업무를 남긴다
    if not tasks and r.tasks:
        types, tasks = _from_rules(r)
    return types, tasks, bool(out.get("mentioned_me")) or r.mentioned_me, bool(out.get("urgent")) or r.urgent, \
        bool(out.get("is_follow_up")) or r.is_follow_up


def classify(req: ClassifyRequest, llm: LLMClient, settings: Settings) -> ClassifyResponse:
    r = judge(req)
    types, tasks = _from_rules(r)
    mentioned, urgent, follow_up = r.mentioned_me, r.urgent, r.is_follow_up
    source, fallback, prompt_version = "rule", None, None

    if r.confidence < settings.router_threshold:  # AI-3 라우터
        try:
            out = llm.chat_json(classify_v1.SYSTEM, classify_v1.render_user(req, r.recipient), classify_v1.SCHEMA)
            types, tasks, mentioned, urgent, follow_up = _from_model(out, req, r)
            source, prompt_version = "exaone", classify_v1.PROMPT_VERSION
        except LLMError as e:
            fallback = str(e)  # ai 장애여도 규칙 결과는 낸다

    mentioned = mentioned and bool(tasks)  # 지목은 나에게 할 일이 있을 때만이다(라벨 기준). 모델은 거의 늘 true를 낸다

    pts = priority.score(superior_or_favorite=req.sender.is_superior or req.sender.is_favorite,
                         dues=[t.due_at for t in tasks if t.due_at], received_at=req.received_at,
                         urgent=urgent, follow_up=follow_up, recipient=r.recipient)
    return ClassifyResponse(
        mail_id=req.mail_id, category=_category(types, bool(tasks)), action_types=types, tasks=tasks,
        mentioned_me=mentioned, urgent=urgent, is_follow_up=follow_up, priority=priority.level(pts),
        source=source, confidence=r.confidence, model=llm.model if source == "exaone" else None,
        prompt_version=prompt_version, rules_version=RULES_VERSION, fallback=fallback,
    )
