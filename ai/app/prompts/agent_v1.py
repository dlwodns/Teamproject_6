"""명령 해석 프롬프트 v1 (AI-12, AI detail 4.3절). v1.3(AI-D19)부터 모든 지시를 받아 모델이 행동을 고른다.

입력: 허용 행동 목록 + 예시 + 지시 글자 + 맥락(현재 시각 · 선택 메일 수). 메일 본문은 넣지 않는다.
예시 문장은 `agent_examples_v1.jsonl`, 평가 문장은 `eval/datasets/agent_commands_v1.jsonl` — 서로 겹치지 않는다(AI-14).
"""
import json
from pathlib import Path

PROMPT_VERSION = "agent_v1.5"  # v1.5(11/17, AI-D22): 개인 알림 → T15 예시 1개. v1.4(11/15): T01 예시 2개(내일 할 일 요약 · 오늘 회고). v1.3(11/13, AI-D19): 모든 지시를 받는다(규칙이 먼저 거르지 않음), 문구만 고침. v1.2(11/10, AI-20): T15 일정_등록 예시 2개. T15가 허용 목록에 없으면 프롬프트는 v1.1과 같다
EXAMPLES_PATH = Path(__file__).with_name("agent_examples_v1.jsonl")

SYSTEM = """너는 메일 업무 비서의 명령 해석기다. 사용자의 지시를 아래 행동 목록 중 하나로 고르고 JSON 하나만 출력한다.
규칙1 목록에 없는 일이면 action은 "unsupported"다. 목록 밖 행동을 지어내지 않는다.
  목록에 있는 일 같지만 어느 행동인지 하나로 정할 수 없으면 "ambiguous"다. 가장 비슷한 행동으로 짐작하지 않는다.
규칙2 과거형 완료 표현("다 했어", "처리했어")은 완료(T03)다. 회신 초안이 아니다.
규칙3 대상: 사람 이름+직급은 sender("김 팀장"), 분류(회신·요청·검토·공지·기타)는 category, "견적 건"처럼 주제는 keyword.
  ◯가 들어간 이름(김◯◯, 김◯◯2)은 가려 둔 이름이다. 줄이거나 바꾸지 말고 sender에 글자 그대로 옮긴다("김◯◯ 팀장").
  "이거", "선택한"처럼 가리키는 말은 selected=true. 날짜 표현은 원문 그대로 when에 옮긴다(계산하지 않는다).

행동 목록:
{actions}

예시:
{examples}"""

SCHEMA_BASE = {
    "type": "object",
    "properties": {
        "action": {"type": "string"},
        "sender": {"type": "string"},
        "category": {"type": "string"},
        "keyword": {"type": "string"},
        "when": {"type": "string"},
        "selected": {"type": "boolean"},
    },
    "required": ["action"],
}


def load_examples() -> list[dict]:
    return [json.loads(ln) for ln in EXAMPLES_PATH.read_text(encoding="utf-8").splitlines() if ln.strip()]


def render_system(actions) -> str:
    allowed = {a.id for a in actions}
    acts = "\n".join(f"- {a.id} {a.name}: {a.description or ''}".rstrip(": ") for a in actions)
    ex = "\n".join(f'"{e["text"]}" → {json.dumps(e["output"], ensure_ascii=False)}'
                   for e in load_examples() if e["output"]["action"] in allowed | {"unsupported", "ambiguous"})
    return SYSTEM.format(actions=acts, examples=ex)


def schema(actions) -> dict:
    s = json.loads(json.dumps(SCHEMA_BASE))
    s["properties"]["action"]["enum"] = [a.id for a in actions] + ["unsupported", "ambiguous"]
    return s


def render_user(text: str, ctx) -> str:
    return f"현재 시각: {ctx.now:%Y-%m-%d %H:%M}\n선택한 메일: {len(ctx.selected_mail_ids)}건\n지시: {text}"
