"""분류 파이프라인: 규칙 → 라우터 → (확신도 낮으면) 엑사원 → 후처리 (AI-2~AI-6, 구조도 4절)."""
import re

from app.core.config import Settings
from app.llm.client import LLMClient, LLMError
from app.pipeline import priority
from app.pipeline.dates import parse_due
from app.pipeline.rules.mail_rules_v1 import RULES_VERSION, RuleResult, event_due, judge
from app.prompts import classify_v3

PROMPT = classify_v3  # 지금 쓰는 분류 프롬프트. 평가 실행기도 이 값으로 버전을 적는다
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


def _external(req: ClassifyRequest) -> bool:
    """보낸 사람 도메인이 메일함 주인과 다르면 사외 메일이다."""
    def dom(a: str) -> str:
        return a.rsplit("@", 1)[-1].strip("<> ").lower()
    return "@" in req.from_ and "@" in req.owner.email and dom(req.from_) != dom(req.owner.email)


def _from_model(out: dict, req: ClassifyRequest, r: RuleResult) -> tuple[list[str], list[TaskOut]]:
    """엑사원 출력을 규칙 결과와 합친다. 모델은 '할 일이 있나 · 무엇인가'를 보고, 정의로 정해지는 칸은 규칙을 따른다(AI-5).
    11/3 dev · dev2 엑사원 경로 오답 기준. 긴급 · 재요청 · 지목은 모델 값을 쓰지 않는다(classify)."""
    types = [t for t in out.get("action_types") or [] if t in PROMPT.ACTION_TYPES] or ["기타"]
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
    # 벤치 후처리 P1: 참조로만 받았고 규칙이 지목을 못 찾으면 업무를 만들지 않는다
    if r.recipient == "cc" and not r.mentioned_me:
        types, tasks = ["참조"], []
    # 공지는 사내 부서가 보내는 안내다. 사외 메일을 공지 · 참조로 고르면 홍보 · 초청(기타)이고 할 일이 아니다
    if _external(req) and types[0] in ("공지", "참조"):
        types, tasks = ["기타"], []
    # 모델이 '회신 · 참조 · 기타'를 맨 앞에 두고 붙인 할 일은 '~ 확인 · 준비' 같은 읽을거리였다(11/3 dev2 회신 메일 4통).
    # 규칙도 요청 문장을 못 찾았을 때만 뺀다. 공지 맨 앞은 '공지 속 지목 요청'일 수 있어 남긴다(D15 · 프롬프트 규칙2)
    if tasks and not r.tasks and types[0] in NO_TASK_TYPES - {"공지"}:
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
                if best.due and _bigrams(best.text + best.evidence) & _bigrams(t.text):
                    t.due_raw, t.due_at = best.due.raw, best.due.due_at
    elif not tasks and not r.tasks and r.action_types[0] in NO_TASK_TYPES:
        types = r.action_types  # 할 일 없음 유형(회신 · 공지 · 참조 · 기타)은 수신 방식 · 제목 단서로 정한 규칙 쪽이 맞았다
    # 누락 방지(D15): 모델이 업무를 비웠어도 규칙이 나를 향한 요청 문장을 찾았으면 규칙 업무를 남긴다
    if not tasks and r.tasks:
        types, tasks = _from_rules(r)
    return types, tasks


def classify(req: ClassifyRequest, llm: LLMClient, settings: Settings) -> ClassifyResponse:
    r = judge(req)
    types, tasks = _from_rules(r)
    mentioned, urgent, follow_up = r.mentioned_me, r.urgent, r.is_follow_up
    source, fallback, prompt_version = "rule", None, None

    if r.confidence < settings.router_threshold:  # AI-3 라우터
        try:
            out = llm.chat_json(PROMPT.SYSTEM, PROMPT.render_user(req, r.recipient), PROMPT.SCHEMA)
            types, tasks = _from_model(out, req, r)
            # 지목은 받는사람이 나이거나 규칙이 본문에서 나를 찾았을 때다. 모델은 지목 · 긴급을 거의 늘 true로 냈다(11/3 dev)
            mentioned = r.mentioned_me or r.recipient == "to"
            source, prompt_version = "exaone", PROMPT.PROMPT_VERSION
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
