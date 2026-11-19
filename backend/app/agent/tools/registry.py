"""행동 레지스트리 — 에이전트가 할 수 있는 행동을 정의하는 한 곳 (BE-11, D37 · D43 · D47, docs/30_backend/detail.md 2절).

웹 에이전트 · REST 버튼 · MCP(P2)가 이 목록을 같이 쓴다. ai `/agent/plan`에 보내는 목록도 여기서 만든다(actions_for_ai).
행동 ID(T01~T15)와 params 키는 backend · ai 공동 계약이다. 바꾸면 `ai/app/agent/rules_v1.py`(extract_params)와 같은 PR 묶음에서
함께 고친다(D47 결정 3). 이름 · params 키는 docs/40_ai/detail.md 2 · 2.1절과 같다.
"""
from dataclasses import dataclass, field

KINDS = ("query", "display", "state_change", "settings", "send")


@dataclass(frozen=True)
class ActionDef:
    id: str  # ai /agent/plan 응답의 action 값과 같다. 레지스트리 조회 키
    name: str  # ai 응답 action_name, 화면 표시용
    description: str  # ai 명령 해석에 함께 보내는 한 줄 설명
    kind: str  # query | display | state_change | settings | send → 확인 판정(policy.needs_confirm)
    params: tuple[str, ...] = ()  # 이 행동이 받는 params 키(D47 고정)
    required: tuple[str, ...] = ()  # 값이 null이면 실행하지 않고 되묻는다(#6 리뷰)
    undoable: bool = False
    mcp_tool: str | None = None  # MCP 노출 이름(AI detail 5.3절). None이면 노출하지 않는다
    priority: str = "P0"
    ready: bool = False  # 백엔드 실행이 준비됐나. False면 "아직 지원하지 않는 요청"
    targets_tasks: bool = field(default=False)  # 대상 해석으로 업무를 찾는 행동인가
    ai: bool = True  # ai `/agent/plan`에 보내는 목록에 넣나. False면 버튼 전용(명령 해석 대상이 아니다)


_ACTIONS = [
    # 11-14: 하루 요약(morning) · 회고(evening)를 채팅에서 바로 본다. 내용은 브리핑(app/reminders/briefings)과 같다
    ActionDef("T01", "오늘_요약", "오늘(또는 내일) 할 일과 기한 임박 업무를 요약한다. 업무 요약 · 브리핑 · 회고도 이것이다(kind=evening이면 오늘 회고)", "query", ("date", "kind"),
              mcp_tool="get_today_summary", ready=True),
    ActionDef("T02", "미처리_조회", "조건(발신자 · 분류 · 기한 범위 · 키워드)에 맞는 업무를 보여 준다. 기본은 미처리, '끝낸 거' · '미룬 거'라고 하면 그 업무", "query",
              mcp_tool="list_pending", ready=True, targets_tasks=True),
    ActionDef("T03", "일괄_완료", "조건에 맞는 미처리 업무를 완료로 바꾼다", "state_change",
              undoable=True, mcp_tool="preview_action", ready=True, targets_tasks=True),
    ActionDef("T04", "되돌리기", "방금 한 행동(또는 지정한 행동)을 되돌린다", "state_change", ("action_id",),
              mcp_tool="undo_action", ready=True),
    ActionDef("T05", "나중에_처리", "업무를 정한 시각까지 미루고 그때 다시 알려 준다", "state_change", ("until",), ("until",),
              undoable=True, mcp_tool="preview_action", ready=True, targets_tasks=True),
    ActionDef("T06", "무응답_확인", "보낸 요청 메일 중 기준일 넘게 답이 없는 것을 보여 준다", "query", ("min_days",),
              mcp_tool="list_awaiting_reply", ready=True),  # BE-13: services/awaiting
    ActionDef("T07", "회신_초안", "선택한 메일의 회신 초안을 보여 준다(보내지 않는다)", "display", ("tone",),
              mcp_tool="draft_reply"),
    ActionDef("T08", "근거_설명", "업무로 판단한 근거 문장을 보여 준다('이거 왜 할 일이야')", "query", priority="P1", ready=True),
    ActionDef("T09", "리마인드_설정", "리마인드 시각 · 기한 전 알림을 바꾼다", "settings", ("rule", "time", "hours"),
              undoable=True, priority="P1"),
    ActionDef("T10", "제외_처리", "업무가 아닌 메일을 목록에서 뺀다", "state_change",
              undoable=True, mcp_tool="preview_action", priority="P1", ready=True, targets_tasks=True),
    ActionDef("T11", "중요_발신자_지정", "발신자를 상급자 · 즐겨찾기로 지정한다", "settings", ("level",),
              undoable=True, priority="P1"),
    ActionDef("T12", "초안_작성", "새 메일 초안을 보여 준다(보내지 않는다)", "display", ("topic",), priority="P1"),
    ActionDef("T13", "기한_보기", "기간(오늘 · 내일 · 이번 주 등)의 캘린더 일정 · 회의 · 마감 목록을 날짜 순으로 보여 준다('이번 주 회의 일정 뭐 있어'). 특정 회의 하나의 장소 · 시각을 묻는 말은 T18이다", "query",
              priority="P1", ready=True),
    ActionDef("T14", "템플릿_전송", "선택한 메일에 템플릿 메일을 보낸다(미리보기 + 확인 후)", "send",
              ("template_kind", "template_name"), priority="P1", ready=True),  # 재촉(nudge)만. 일반 템플릿은 BE-16(P2)
    # BE-15 · D50 결정 6: 앱 캘린더에 일정을 넣는다(Outlook에는 쓰지 않는다). 1건이고 되돌릴 수 있어 바로 실행한다.
    # start가 없으면 고른 메일의 일정참석 업무 시각(메일에 적힌 것만)으로 채우고, 그것도 없으면 되묻는다(executor)
    ActionDef("T15", "일정_등록", "앱 캘린더에 일정을 넣는다(회의 · 개인 일정 · '~하라고 알려줘' 같은 개인 알림. 말로 준 날짜 · 시각, 또는 고른 메일 · 이름으로 찾은 메일의 회의 시각)", "state_change",
              ("start", "end", "title"), undoable=True, priority="P1", ready=True),
]

# BE-12 · 명세 reminders.md 7.3절: 리마인더 '기한 바뀜' 항목의 [새 기한으로 바꾸기](POST /api/reminders/{key}/apply → change_due).
# 11-18: 말로도 바꾼다("이 업무 기한 금요일로 바꿔줘"). 대상은 고른 메일 · 낱말로 찾은 업무 1건, 값은 due_at(ai rules_v1이 계산).
# 1건이고 되돌릴 수 있어 바로 실행한다. 여러 건이면 되묻는다(executor)
_ACTIONS += [
    ActionDef("T16", "기한_변경", "업무의 기한(마감)을 다른 날짜로 바꾼다('기한 금요일로 바꿔줘'). 다시 알림만 미루는 것은 T05다", "state_change",
              ("task_id", "due_at"), ("due_at",), undoable=True, priority="P1", ready=True, targets_tasks=True),
]

# 11-17 결정(문규남): 대화에서 "김 팀장이 누구였지 · 무슨 메일 보냈었지"를 묻는다. '메일 내용 분석 허용'을 켜면
# 메일에서 알아낸 맡은 일 · 소속(contact_facts)으로 답한다(켜기 = 저장 + 그 정보로 답하기에 동의). 끄면 메일 · 업무 목록만.
_ACTIONS += [
    ActionDef("T17", "사람_조회", "보낸 사람이 누구인지(맡은 일 · 소속)와 그 사람이 보낸 메일 · 업무를 보여 준다", "query",
              priority="P1", ready=True),
]

# 11-18: "누리물류 킥오프 미팅 어디서 해" · "킥오프 미팅 장소 변경 어디야"처럼 메일에 적힌 내용을 묻는 말. 목록에 맞는 행동이 없어
# 모델이 '지원 외'로 끝냈다. 메일을 찾아 답이 적힌 본문 문장을 그대로 보여 준다(app/agent/ask.py, 모델로 답을 짓지 않는다)
_ACTIONS += [
    ActionDef("T18", "메일_내용_질문", "특정 메일 · 회의에 대해 적힌 내용(어디서 · 몇 시 · 금액 · 바뀐 내용 등)을 묻는 질문에 그 메일과 답이 적힌 문장을 보여 준다. "
              "업무 목록 · 기한 · 사람이 누구인지 묻는 말은 이것이 아니다", "query", priority="P1", ready=True),
]

# 11-18 사용자 목적별 시나리오(eval/datasets/agent_commands_v5.jsonl)에서 막힌 '메일 찾기' · '메일 요약'.
# 업무가 아니라 메일을 돌려준다(result.mails). 받은 · 보낸 메일 모두, 끝난 업무의 메일도 찾는다
_ACTIONS += [
    ActionDef("T19", "메일_찾기", "조건(보낸 사람 · 회사 · 낱말 · 기간 · 내가 보낸 메일)에 맞는 메일 목록과 건수를 보여 준다"
              "('누리물류 메일 다 보여줘' · '어제 받은 메일 몇 통' · '김 팀장한테 답장 보냈나')", "query", ("sent",),
              priority="P1", ready=True),
    ActionDef("T20", "메일_요약", "고른 메일(또는 낱말로 찾은 메일 1통)의 요지와 나에게 요청한 것을 요약한다('무슨 내용이야' · '요약해줘')", "query",
              priority="P1", ready=True),
]

REGISTRY: dict[str, ActionDef] = {a.id: a for a in _ACTIONS}


def actions_for_ai() -> list[dict[str, str]]:
    """ai `/agent/plan` 요청의 actions. 손으로 따로 적지 않고 여기서 만든다(detail 2.1절)."""
    return [{"id": a.id, "name": a.name, "description": a.description} for a in _ACTIONS if a.ai]
