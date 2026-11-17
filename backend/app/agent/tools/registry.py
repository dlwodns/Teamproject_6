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
    ActionDef("T02", "미처리_조회", "조건(발신자 · 분류 · 기한 범위 · 키워드)에 맞는 미처리 업무를 보여 준다", "query",
              mcp_tool="list_pending", ready=True, targets_tasks=True),
    ActionDef("T03", "일괄_완료", "조건에 맞는 미처리 업무를 완료로 바꾼다", "state_change",
              undoable=True, mcp_tool="preview_action", ready=True, targets_tasks=True),
    ActionDef("T04", "되돌리기", "방금 한 행동(또는 지정한 행동)을 되돌린다", "state_change", ("action_id",),
              mcp_tool="undo_action", ready=True),
    ActionDef("T05", "나중에_처리", "업무를 정한 시각까지 미루고 그때 다시 알려 준다", "state_change", ("until",), ("until",),
              undoable=True, mcp_tool="preview_action", ready=True, targets_tasks=True),
    ActionDef("T06", "무응답_확인", "보낸 요청 메일 중 기준일 넘게 답이 없는 것을 보여 준다", "query", ("min_days",),
              mcp_tool="list_awaiting_reply"),
    ActionDef("T07", "회신_초안", "선택한 메일의 회신 초안을 보여 준다(보내지 않는다)", "display", ("tone",),
              mcp_tool="draft_reply"),
    ActionDef("T08", "근거_설명", "업무로 판단한 근거 문장을 보여 준다", "query", priority="P1"),
    ActionDef("T09", "리마인드_설정", "리마인드 시각 · 기한 전 알림을 바꾼다", "settings", ("rule", "time", "hours"),
              undoable=True, priority="P1"),
    ActionDef("T10", "제외_처리", "업무가 아닌 메일을 목록에서 뺀다", "state_change",
              undoable=True, mcp_tool="preview_action", priority="P1", targets_tasks=True),
    ActionDef("T11", "중요_발신자_지정", "발신자를 상급자 · 즐겨찾기로 지정한다", "settings", ("level",),
              undoable=True, priority="P1"),
    ActionDef("T12", "초안_작성", "새 메일 초안을 보여 준다(보내지 않는다)", "display", ("topic",), priority="P1"),
    ActionDef("T13", "기한_보기", "기간의 기한 업무를 캘린더로 보여 준다", "query", priority="P1"),
    ActionDef("T14", "템플릿_전송", "선택한 메일에 템플릿 메일을 보낸다(미리보기 + 확인 후)", "send",
              ("template_kind", "template_name"), priority="P1"),
    # BE-15 · D50 결정 6: 앱 캘린더에 일정을 넣는다(Outlook에는 쓰지 않는다). 1건이고 되돌릴 수 있어 바로 실행한다.
    # start가 없으면 고른 메일의 일정참석 업무 시각(메일에 적힌 것만)으로 채우고, 그것도 없으면 되묻는다(executor)
    ActionDef("T15", "일정_등록", "앱 캘린더에 일정을 넣는다(말로 준 날짜 · 시각, 또는 고른 메일의 회의 시각)", "state_change",
              ("start", "end", "title"), undoable=True, priority="P1", ready=True),
]

# BE-12 · 명세 reminders.md 7.3절: 리마인더 '기한 바뀜' 항목의 [새 기한으로 바꾸기]. 1건이고 되돌릴 수 있어 바로 실행한다.
# 지금은 버튼 전용이다(POST /api/reminders/{key}/apply → app/reminders/actions.change_due). 그래서 ai 목록에 넣지 않고(ai=False)
# 명령 실행기(executor)도 받지 않는다(ready=False → "준비 중"). 말로 기한을 바꾸게 하려면 ai `rules_v1.py`와 executor를 함께 고친다(D47 결정 3).
_ACTIONS += [
    ActionDef("T16", "기한_변경", "업무의 기한을 바꾼다(되돌리기는 이전 기한으로)", "state_change", ("task_id", "due_at"),
              ("task_id", "due_at"), undoable=True, priority="P1", ai=False),
]

# 11-17 결정(문규남): 대화에서 "김 팀장이 누구였지 · 무슨 메일 보냈었지"를 묻는다. '메일 내용 분석 허용'을 켜면
# 메일에서 알아낸 맡은 일 · 소속(contact_facts)으로 답한다(켜기 = 저장 + 그 정보로 답하기에 동의). 끄면 메일 · 업무 목록만.
_ACTIONS += [
    ActionDef("T17", "사람_조회", "보낸 사람이 누구인지(맡은 일 · 소속)와 그 사람이 보낸 메일 · 업무를 보여 준다", "query",
              priority="P1", ready=True),
]

REGISTRY: dict[str, ActionDef] = {a.id: a for a in _ACTIONS}


def actions_for_ai() -> list[dict[str, str]]:
    """ai `/agent/plan` 요청의 actions. 손으로 따로 적지 않고 여기서 만든다(detail 2.1절)."""
    return [{"id": a.id, "name": a.name, "description": a.description} for a in _ACTIONS if a.ai]
