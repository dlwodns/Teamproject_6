"""명령 해석 (AI-11 · AI-12 · AI-23, AI detail 4.1절): 모델이 행동을 고른다 → 구조 검사(허용 목록 · 빠진 값 · 상태 변경 확인).

AI-D19(11/13): 판단은 모두 모델이 한다. v1.5까지는 규칙이 먼저 행동을 정하고(1개면 모델을 부르지 않음), '지원 외'도 규칙이
모델 없이 끝냈다. 지금은 모든 지시를 모델이 먼저 읽고 행동을 고른다. 규칙(rules_v1)은 구조 · 틀만 맡는다.
- 허용 목록 검증: 목록에 없는 행동 · 형식 오류는 실행하지 않는다
- 값 계산: 날짜 · 시각 · 제목 같은 params는 코드가 계산한다(모델은 날짜 표현을 원문 그대로 when에 옮긴다)
- 대상: 모델이 낸 sender · keyword · category가 먼저다. 모델이 비운 칸만 코드가 읽은 값(고른 메일 · 직전 결과 · 날짜 범위)으로 채운다
- 빠진 값: 행동에 필요한 대상 · 값이 없으면 실행하지 않고 되묻는다(slots_ok)
- 상태 변경 확인: 모델이 고른 상태 변경 행동인데 문장에 부정 · 의문 · 과거 표지가 있으면 실행하지 않고 되묻는다(non_command).
  모델이 고른 행동을 다른 행동으로 바꾸지 않는다 — 실행 전에 사람에게 한 번 더 묻는 틀이다
- 지원 외 지시: 모델이 고른 상태 변경 행동인데 문장이 삭제 · 휴지통 · 스팸 신고 · 전달 · 차단처럼 지원하지 않는 메일 조작이면
  실행하지 않고 지원 외로 끝낸다(rules_v1.guard, AI-T6 '메일 다 지워줘' → T10 재발 방지, #67 리뷰)
모델 호출이 실패하면 규칙 결과를 내지 않고 LLMError를 올린다(API가 503으로 알린다).
대상 해석(발신자 DB 매칭) · 확인 정책 판정 · 실행 · action_log 기록은 backend가 한다(D37).
"""
from app.agent import rules_v1
from app.llm.client import LLMClient
from app.prompts import agent_v1
from app.schemas.agent import PlanRequest, PlanResponse, Target


def _reject(reason: str, source: str, candidates: list[str], **kw) -> PlanResponse:
    return PlanResponse(action=None, source=source, reason=reason, candidates=candidates,
                        rules_version=rules_v1.RULES_VERSION, **kw)


def _response(req: PlanRequest, action: str, target: Target, candidates: list[str], **kw) -> PlanResponse:
    names = {a.id: a.name for a in req.actions}
    params = rules_v1.extract_params(action, req.text, req.context, target)
    if not rules_v1.slots_ok(action, req.text, req.context, target, params):  # '빼줘' · '알림 바꿔줘' · 못 푼 '그거'
        return _reject("ambiguous", "model", candidates or [action], **kw)
    return PlanResponse(action=action, action_name=names[action], target=target, params=params, source="model",
                        candidates=candidates, rules_version=rules_v1.RULES_VERSION, **kw)


def _target(req: PlanRequest, out: dict) -> Target:
    """모델 값이 먼저, 모델이 비운 칸만 코드가 읽은 값으로 채운다."""
    t = rules_v1.extract_target(req.text, req.context)
    if out.get("sender"):
        t.sender = str(out["sender"])
    if out.get("keyword"):
        t.keyword = str(out["keyword"])
    if out.get("category") in ("회신", "요청", "검토", "공지", "기타"):
        t.category = out["category"]
    if out.get("selected") and req.context.selected_mail_ids:
        t.mail_ids = list(req.context.selected_mail_ids)
    return t


def _needs_confirm(req: PlanRequest, action: str, allowed: set[str]) -> bool:
    """상태 변경 전 확인(v1.4 안전장치를 그대로 옮김). 모델이 고른 상태 변경 행동이 문장에서 지시로 읽히지 않으면 실행하지 않고 되묻는다.
    - 지시로 읽힘: 문장에 그 행동의 지시 표현이 부정 없이 있다('보고서 건은 미루지 말고 오늘 완료 처리해'의 완료)
    - 지시로 안 읽힘: 그 행동 표현이 부정 · 의문 · 과거 · 메일 아닌 대상(회의 · 일정)에 걸렸거나, 문장 전체가 부정 · 의문 · 과거다
    모델이 고른 행동을 다른 행동으로 바꾸지 않는다. 날짜가 없어 지운 미루기(T05)는 모델 when으로 살린다."""
    an = rules_v1.analyze(req.text, req.context.now, allowed)
    if action in an.hits:
        return False
    vetoed = {a for a, why in an.dropped.items() if why != "no_date"}
    return action in vetoed or rules_v1.non_command(req.text, action)


def plan(req: PlanRequest, llm: LLMClient) -> PlanResponse:
    allowed = {a.id for a in req.actions}
    out = llm.chat_json(agent_v1.render_system(req.actions), agent_v1.render_user(req.text, req.context),
                        agent_v1.schema(req.actions))  # LLMError는 그대로 올린다
    kw = {"prompt_version": agent_v1.PROMPT_VERSION}
    action = out.get("action")
    if action == "ambiguous":  # 행동 하나로 정하지 못함 → backend가 되묻는다
        return _reject("ambiguous", "model", [], **kw)
    if action not in allowed:  # 허용 목록 검증 — 'unsupported' · 지어낸 행동 · 형식 오류
        return _reject("unsupported", "model", [], **kw)
    if action in rules_v1.MUTATING and rules_v1.guard(req.text, [action]):  # 지원 외 지시(삭제 · 휴지통 · 스팸 신고 · 전달 · 차단, AI-T6)
        return _reject("unsupported", "model", [], **kw)                    # 를 모델이 가까운 상태 변경으로 골라도 실행하지 않는다
    if action in rules_v1.MUTATING and _needs_confirm(req, action, allowed):  # 상태 변경 전 확인(틀)
        return _reject("ambiguous", "model", [action], **kw)
    text = req.text if not out.get("when") else f"{req.text} {out['when']}"
    req = req.model_copy(update={"text": text})
    return _response(req, action, _target(req, out), [], **kw)
