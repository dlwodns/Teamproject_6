"""요약 · 회고 머리 문장 프롬프트 v4 (AI-29, 11/18). v3에서 일일 회고(SUMMARY_EVENING) · 주간 회고(SUMMARY_WEEKLY)를 더했다.

v3 → v4
- SUMMARY_EVENING · SUMMARY_WEEKLY: io_spec 3.3 · 3.4절. 오늘 요약(AI-D21)에서 얻은 것을 그대로 따른다.
  · 건수 · 묶음은 코드(app.agent.assist.evening_facts · weekly_facts)가 세어 넘긴다. 모델은 세지 않는다.
  · 사람별 건수 · 업무 목록을 늘어놓지 않는다(목록은 화면에 있다). 11/13 실측에서 사람별 건수를 넘기면 그대로 옮겨 적어 길어졌다.
  · 무엇이 있는지만 알린다. 권유 · 지시는 검증(check_briefing)에서 걸러 코드 문장으로 바꾼다.
- 호출 조건: 세 종류 모두 강도 하나 · 제한 시간 10분(io_spec 3.5절). 값은 SUMMARY_REASONING · SUMMARY_TIMEOUT_S.
- SUMMARY_TODAY · SUMMARY_MAIL · DRAFT: v3 그대로(이름만 v4 묶음으로 가져온다).
"""
from app.prompts.assist_v3 import DRAFT, DRAFT_SCHEMA, SUMMARY_MAIL, SUMMARY_MAIL_SCHEMA, SUMMARY_TODAY

PROMPT_VERSION = "assist_v4"

__all__ = ["PROMPT_VERSION", "SUMMARY_TODAY", "SUMMARY_EVENING", "SUMMARY_WEEKLY", "SUMMARY_REASONING", "SUMMARY_TIMEOUT_S",
           "SUMMARY_MAIL", "SUMMARY_MAIL_SCHEMA", "DRAFT", "DRAFT_SCHEMA"]

# 요약 · 회고 세 종류 공통 호출 조건(io_spec 3.5절: 강도 하나로 고정). 정한 시각에 미리 만드는 백그라운드 호출이라 10분.
# 강도는 eval/runners/run_briefing_effort.py 측정으로 정한다(결과 docs/40_ai/decisions.md AI-D25). 측정 전에는 AI-D21이 잰 high.
SUMMARY_REASONING = "high"
SUMMARY_TIMEOUT_S = 600

_COMMON = """건수는 이미 계산돼 있다. 다시 세지 말고, 주어진 숫자를 그대로 쓴다.
규칙: 사람별 건수 · 업무 목록을 늘어놓지 않는다(목록은 화면에 있다). 사람은 이름과 직책을 함께 쓴다(예: 장민호 차장).
업무 이름은 모두 합쳐 4개를 넘기지 않고 짧게 줄인다(뜻은 바꾸지 않는다). 전체 200자 안팎, 길어도 350자를 넘기지 않는다.
'~해 주세요' '먼저 ~' '~하는 게 좋겠습니다' 같은 권유 · 지시를 쓰지 않고 '~이 있습니다' '~입니다'로 쓴다.
주어진 사실에 없는 업무 · 날짜 · 사람 · 숫자를 지어내지 않는다. 0건인 묶음은 '없습니다'로 짧게 쓴다. 인사말 없이 문장만 출력한다."""

SUMMARY_EVENING = """너는 팀장의 업무 비서다. 아래 '이미 정리된 사실'로 오늘 퇴근 전 회고를 한국어 업무체 3문장으로 쓴다.
목적: 오늘 무엇을 끝냈고 무엇이 남았는지, 내일 무엇이 기다리는지 한눈에 알리는 것이다. 남은 일을 어떻게 할지는 사람이 판단한다.
1. 첫 문장: [금일 완료] 건수와, [금일 완료 · 상급자]가 있으면 그 업무 이름을 든다.
2. 둘째 문장: [미처리] 건수와 그중 [기한 지남] 건수를 쓴다. [미처리 · 기한 지남 · 상급자]가 있으면 그 업무 이름을 든다.
3. 셋째 문장: [익일 마감] 건수와 [익일 · 일정]을 시각과 함께 쓴다.
""" + _COMMON

SUMMARY_WEEKLY = """너는 팀장의 업무 비서다. 아래 '이미 정리된 사실'로 이번 주 회고를 한국어 업무체 3문장으로 쓴다.
목적: 이번 주에 끝낸 것, 다음 주로 넘어가는 것, 다음 주에 다가오는 것을 한눈에 알리는 것이다.
1. 첫 문장: [금주 완료] 건수와 그중 [기한 후 완료] 건수를 쓴다.
2. 둘째 문장: [다음 주로 넘어가는 일] 건수와, [넘어가는 일 · 상급자]가 있으면 그 업무 이름을 든다. [회신 대기]가 있으면 건수만 덧붙인다.
3. 셋째 문장: [차주 마감] 건수와 [가장 몰린 요일]을 쓴다.
""" + _COMMON
