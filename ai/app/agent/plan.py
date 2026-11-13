"""명령 해석: 규칙 → (0개 · 2개 이상이면) 엑사원 + 예시 → 허용 목록 검증 (AI-11 · AI-12, AI detail 4.1절).

대상 해석(발신자 DB 매칭) · 확인 정책 판정 · 실행 · action_log 기록은 backend가 한다(D37).
v1.4: 행동이 정해진 뒤 대상 · 값이 빠졌으면 되묻는다(규칙 · 모델 공통). 규칙이 못 잡은 상태 변경 행동을 모델이 냈는데
문장에 부정 · 의문 · 과거 표지가 있거나 규칙이 근거를 들어 지운 행동이면 실행하지 않고 되묻는다.
"""
from app.agent import rules_v1
from app.llm.client import LLMClient, LLMError
from app.prompts import agent_v1
from app.schemas.agent import PlanRequest, PlanResponse, Target


def _reject(reason: str, source: str, candidates: list[str], **kw) -> PlanResponse:
    return PlanResponse(action=None, source=source, reason=reason, candidates=candidates,
                        rules_version=rules_v1.RULES_VERSION, **kw)


def _response(req: PlanRequest, action: str, target: Target, source: str, candidates: list[str], **kw) -> PlanResponse:
    names = {a.id: a.name for a in req.actions}
    params = rules_v1.extract_params(action, req.text, req.context, target)
    if not rules_v1.slots_ok(action, req.text, req.context, target, params):  # v1.4 '빼줘' · '알림 바꿔줘' · 못 푼 '그거'
        return _reject("ambiguous", source, candidates or [action], **kw)
    return PlanResponse(action=action, action_name=names[action], target=target, params=params, source=source,
                        candidates=candidates, rules_version=rules_v1.RULES_VERSION, **kw)


def plan(req: PlanRequest, llm: LLMClient) -> PlanResponse:
    allowed = {a.id for a in req.actions}
    an = rules_v1.analyze(req.text, req.context.now, allowed)
    hits = [h for h in an.hits if h in allowed]
    target = rules_v1.extract_target(req.text, req.context)
    if hits and (reason := rules_v1.guard(req.text, hits)):  # 규칙이 잡은 행동이어도 지원 외면 실행하지 않는다
        return _reject(reason, "rule", hits)
    if "T15" in hits and rules_v1.COMPOUND_WITH & set(hits):  # v1.5 '초안 쓰고 회의 잡아줘' — 하나만 골라 실행하지 않는다(한 번에 하나씩 되묻기)
        return _reject("ambiguous", "rule", hits)
    if len(hits) == 1:
        return _response(req, hits[0], target, "rule", [])
    # 행동이 하나도 안 걸렸고 지원 외 · 애매가 분명하면 모델 없이 끝낸다(모델 경로 1건 약 22초)
    reason = rules_v1.reject_reason(req.text, an) if not hits else None
    if reason:
        return _reject(reason, "rule", list(an.dropped))

    try:
        out = llm.chat_json(agent_v1.render_system(req.actions), agent_v1.render_user(req.text, req.context),
                            agent_v1.schema(req.actions))
    except LLMError as e:
        reason = "ambiguous" if hits else "unsupported"
        return _reject(reason, "rule", hits, fallback=str(e))

    model_kw = {"prompt_version": agent_v1.PROMPT_VERSION}
    action = out.get("action")
    if action == "ambiguous":  # 행동 하나로 정하지 못함 → backend가 되묻는다
        return _reject("ambiguous", "model", hits, **model_kw)
    if action not in allowed:  # 허용 목록 검증 — 'unsupported' · 지어낸 행동 · 형식 오류
        return _reject("unsupported", "model", hits, **model_kw)
    # v1.4 안전장치: 규칙 후보에 없던 상태 변경 행동을 모델이 골랐는데 부정 · 의문 · 과거 표지가 있거나,
    # 규칙이 근거(부정 · 의문 · 과거 · 메일 아닌 대상)를 들어 지운 행동이면 실행하지 않는다. 날짜가 없어 지운 T05는 모델 when으로 살린다
    vetoed = {a for a, why in an.dropped.items() if why != "no_date"}
    if action in rules_v1.MUTATING and action not in hits and (action in vetoed or rules_v1.non_command(req.text, action)):
        return _reject("ambiguous", "model", hits or [action], **model_kw)
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
    return _response(req, action, target, "model", hits, **model_kw)
