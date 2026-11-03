"""명령 해석: 규칙 → (0개 · 2개 이상이면) 엑사원 + 예시 → 허용 목록 검증 (AI-11 · AI-12, AI detail 4.1절).

대상 해석(발신자 DB 매칭) · 확인 정책 판정 · 실행 · action_log 기록은 backend가 한다(D37).
"""
from app.agent import rules_v1
from app.llm.client import LLMClient, LLMError
from app.prompts import agent_v1
from app.schemas.agent import PlanRequest, PlanResponse, Target


def _response(req: PlanRequest, action: str, target: Target, source: str, **kw) -> PlanResponse:
    names = {a.id: a.name for a in req.actions}
    params = rules_v1.extract_params(action, req.text, req.context, target)
    return PlanResponse(action=action, action_name=names[action], target=target, params=params, source=source,
                        rules_version=rules_v1.RULES_VERSION, **kw)


def plan(req: PlanRequest, llm: LLMClient) -> PlanResponse:
    allowed = {a.id for a in req.actions}
    hits = [h for h in rules_v1.match(req.text, req.context.now) if h in allowed]
    target = rules_v1.extract_target(req.text, req.context)
    if hits and (reason := rules_v1.guard(req.text, hits)):  # 규칙이 잡은 행동이어도 지원 외 · 부정 지시면 실행하지 않는다
        return PlanResponse(action=None, source="rule", reason=reason, candidates=hits, rules_version=rules_v1.RULES_VERSION)
    if len(hits) == 1:
        return _response(req, hits[0], target, "rule")
    # 행동이 하나도 안 걸렸고 지원 외 · 애매가 분명하면 모델 없이 끝낸다(모델 경로 1건 약 22초)
    reason = rules_v1.reject_reason(req.text) if not hits else None
    if reason:
        return PlanResponse(action=None, source="rule", reason=reason, rules_version=rules_v1.RULES_VERSION)

    try:
        out = llm.chat_json(agent_v1.render_system(req.actions), agent_v1.render_user(req.text, req.context),
                            agent_v1.schema(req.actions))
    except LLMError as e:
        reason = "ambiguous" if hits else "unsupported"
        return PlanResponse(action=None, source="rule", reason=reason, candidates=hits,
                            rules_version=rules_v1.RULES_VERSION, fallback=str(e))

    action = out.get("action")
    if action == "ambiguous":  # 행동 하나로 정하지 못함 → backend가 되묻는다
        return PlanResponse(action=None, source="model", reason="ambiguous", candidates=hits,
                            prompt_version=agent_v1.PROMPT_VERSION, rules_version=rules_v1.RULES_VERSION)
    if action not in allowed:  # 허용 목록 검증 — 'unsupported' · 지어낸 행동 · 형식 오류
        return PlanResponse(action=None, source="model", reason="unsupported", candidates=hits,
                            prompt_version=agent_v1.PROMPT_VERSION, rules_version=rules_v1.RULES_VERSION)
    # 규칙으로 뽑은 대상이 우선, 비어 있는 칸만 모델 값으로 채운다
    if not target.sender and out.get("sender"):
        target.sender = str(out["sender"])
    if not target.keyword and out.get("keyword"):
        target.keyword = str(out["keyword"])
    if not target.category and out.get("category") in ("회신", "요청", "검토", "공지", "기타"):
        target.category = out["category"]
    if not target.mail_ids and out.get("selected"):
        target.mail_ids = list(req.context.selected_mail_ids)
    text = req.text if not out.get("when") else f"{req.text} {out['when']}"
    req = req.model_copy(update={"text": text})
    return _response(req, action, target, "model", candidates=hits, prompt_version=agent_v1.PROMPT_VERSION)
