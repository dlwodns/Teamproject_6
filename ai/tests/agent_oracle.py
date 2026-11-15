"""명령 해석 테스트용 가짜 모델: 규칙(rules_v1)이 v1.5까지 내리던 결정을 모델 답처럼 돌려준다(AI-D19 전환 회귀용).

AI-D19부터 행동은 모델이 고른다. 이 가짜 모델은 '모델이 v1.5 규칙과 같은 행동을 골랐을 때' 대상 · 값 계산 · 되묻기 같은
구조 부분이 예전과 같은 결과를 내는지 보려고 쓴다. 실제 모델의 판단 품질은 명령 평가 세트(eval)로 따로 잰다.
테스트가 replies에 답을 넣으면 그 답을 먼저 쓴다.
"""
import re

from app.agent import rules_v1
from tests.conftest import FakeLLM


def rule_answer(text: str, now, allowed: set[str]) -> dict | None:
    an = rules_v1.analyze(text, now, allowed)
    hits = [h for h in an.hits if h in allowed]
    if hits and (reason := rules_v1.guard(text, hits)):
        return {"action": reason}
    if "T15" in hits and rules_v1.COMPOUND_WITH & set(hits):
        return {"action": "ambiguous"}
    if len(hits) == 1:
        return {"action": hits[0]}
    reason = rules_v1.reject_reason(text, an) if not hits else None
    return {"action": reason} if reason else None


class RuleLikeLLM(FakeLLM):
    def chat_json(self, system, user, schema):
        if self.replies:
            return super().chat_json(system, user, schema)
        self.calls.append({"kind": "json", "system": system, "user": user})
        text = re.search(r"^지시: (.*)$", user, re.M)[1]
        from datetime import datetime
        now = datetime.strptime(re.search(r"^현재 시각: (.*)$", user, re.M)[1], "%Y-%m-%d %H:%M")
        allowed = set(schema["properties"]["action"]["enum"]) - {"unsupported", "ambiguous"}
        return rule_answer(text, now, allowed) or {"action": "ambiguous"}
