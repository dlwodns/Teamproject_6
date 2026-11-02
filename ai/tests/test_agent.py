from datetime import datetime

import pytest

from app.agent.plan import plan
from app.llm.client import LLMError
from app.prompts.agent_v1 import load_examples
from app.schemas.agent import ActionSpec, PlanContext, PlanRequest

ACTIONS = [ActionSpec(id=f"T{i:02d}", name=n) for i, n in enumerate(
    ["오늘_요약", "미처리_조회", "일괄_완료", "되돌리기", "나중에_처리", "무응답_확인", "회신_초안", "근거_설명",
     "리마인드_설정", "제외_처리", "중요_발신자_지정", "초안_작성", "기한_보기", "템플릿_전송"], start=1)]
NOW = datetime(2026, 11, 2, 10, 0)  # 월요일


def req(text, selected=(), last=(), actions=ACTIONS):
    return PlanRequest(text=text, actions=actions,
                       context=PlanContext(now=NOW, selected_mail_ids=list(selected), last_result_ids=list(last)))


@pytest.mark.parametrize("text, action", [
    ("오늘 뭐 해야 돼?", "T01"),
    ("이번 주 공지 메일 다 처리했어", "T03"),
    ("회신 다 했어", "T03"),  # 충돌: 과거형 완료 우선
    ("방금 거 취소해", "T04"),
    ("견적 건은 금요일에 다시 알려줘", "T05"),
    ("답장 안 온 메일 있어?", "T06"),
    ("답장 안 온 거 재촉 메일 보내줘", "T14"),  # 충돌: 발송이 조회보다 우선
])
def test_rule_path_detail_7_2(fake_llm, text, action):
    r = plan(req(text), fake_llm)
    assert r.action == action and r.source == "rule" and fake_llm.calls == []



# v1.2 바꿔 말하기 — 평가 문장 · 예시 문장과 다른 새 문장
@pytest.mark.parametrize("text, action", [
    ("내일 할 거 알려줘", "T01"),
    ("아직 못 끝낸 메일 보여줘", "T02"),
    ("답장 전부 보냈어", "T03"),
    ("실행한 거 원상복구 해줘", "T04"),
    ("보고서 건 다음 주 화요일로 연기해", "T05"),
    ("답변 안 준 사람 있어?", "T06"),
    ("이 메일 답장 좀 써줘", "T07"),
    ("이게 왜 중요로 분류됐어", "T08"),
    ("알림 시간 9시로 바꿔", "T09"),
    ("이 뉴스레터 숨겨줘", "T10"),
    ("앞으로 오 차장님 메일은 중요하게", "T11"),
    ("회의 취소 메일 박 대리에게 써줘", "T12"),  # '회의 취소'는 되돌리기가 아니다
    ("다음 주 마감 몰린 날 알려줘", "T13"),
])
def test_rule_paraphrases_v1_2(fake_llm, text, action):
    r = plan(req(text), fake_llm)
    assert r.action == action and r.source == "rule" and fake_llm.calls == []


@pytest.mark.parametrize("text, reason", [
    ("뉴스레터 구독 취소해줘", "unsupported"),  # 되돌리기(T04)로 잡지 않는다
    ("이 메일 김 팀장님한테 전달해", "unsupported"),
    ("광고 메일 차단해", "unsupported"),
    ("첨부 파일 다운받아줘", "unsupported"),
    ("오늘 날씨 어때", "unsupported"),
    ("알아서 해줘", "ambiguous"),
    ("공지 쪽 정리 좀", "ambiguous"),
    ("견적 건 좀 봐줘", "ambiguous"),
])
def test_rule_rejects_without_model(fake_llm, text, reason):
    r = plan(req(text), fake_llm)
    assert r.action is None and r.reason == reason and r.source == "rule" and fake_llm.calls == []


@pytest.mark.parametrize("text", [
    "점심 약속 메일 언제 왔지",  # 메일 업무 낱말이 있으면 '점심'만 보고 지원 외로 막지 않는다
    "회의 일정 취소해줘",  # 메일 속 일정 취소 — 규칙이 정하지 않는다
    "답장 보냈어?",  # 질문은 완료 보고가 아니다 — T03으로 확정하지 않는다
])
def test_unclear_goes_to_model_not_rule(fake_llm, text):
    fake_llm.replies = [{"action": "ambiguous"}]
    r = plan(req(text), fake_llm)
    assert r.source == "model" and len(fake_llm.calls) == 1


def test_target_and_params(fake_llm):
    r = plan(req("이번 주 공지 메일 다 처리했어"), fake_llm)
    assert r.target.category == "공지" and str(r.target.date_range.start) == "2026-11-02"
    r = plan(req("견적 건은 금요일에 다시 알려줘"), fake_llm)
    assert r.target.keyword == "견적" and r.params["until"] == "2026-11-06T08:30:00"  # 시각 없으면 08:30
    r = plan(req("김 팀장님 건 다 처리했어"), fake_llm)
    assert r.target.sender == "김 팀장" and r.target.keyword is None


def test_deictic_uses_selection(fake_llm):
    r = plan(req("이거 완료", selected=["M-1"]), fake_llm)
    assert r.action == "T03" and r.target.mail_ids == ["M-1"]


def test_nudge_targets_awaiting_list_or_last_result(fake_llm):
    r = plan(req("답장 안 온 거 재촉 메일 보내줘"), fake_llm)
    assert r.params["template_kind"] == "nudge" and r.target.awaiting_reply
    r = plan(req("그 2건 재촉 메일 보내", last=["S-1", "S-2"]), fake_llm)
    assert r.target.mail_ids == ["S-1", "S-2"] and not r.target.awaiting_reply


def test_unmatched_goes_to_model_and_is_validated(fake_llm):
    fake_llm.replies = [{"action": "T13", "when": "이번 달"}]
    r = plan(req("제출 날짜 몰린 날 언제야"), fake_llm)
    assert r.action == "T13" and r.source == "model" and r.prompt_version == "agent_v1.1"
    assert "메일 본문" not in fake_llm.calls[0]["user"]


def test_model_cannot_pick_action_outside_allowed_list(fake_llm):
    fake_llm.replies = [{"action": "T99_메일_신고"}]
    r = plan(req("스팸 메일 신고해줘"), fake_llm)
    assert r.action is None and r.reason == "unsupported"
    # backend가 허용하지 않은 행동은 규칙에 걸려도 고르지 않는다
    fake_llm.replies = [LLMError("down")]
    r = plan(req("답장 안 온 거 재촉 메일 보내줘", actions=ACTIONS[:13]), fake_llm)
    assert r.action != "T14"


def test_model_down_returns_unsupported_not_guess(fake_llm):
    fake_llm.replies = [LLMError("ollama 호출 실패: ConnectError")]
    r = plan(req("배고프다"), fake_llm)
    assert r.action is None and r.reason == "unsupported" and r.fallback


def test_delete_is_unsupported_without_model(fake_llm):
    r = plan(req("받은 메일 전부 삭제해"), fake_llm)
    assert r.action is None and r.reason == "unsupported" and fake_llm.calls == []


def test_model_ambiguous_asks_back(fake_llm):
    fake_llm.replies = [{"action": "ambiguous"}]
    r = plan(req("그 사람 거 어떻게 된 거야"), fake_llm)
    assert r.action is None and r.reason == "ambiguous" and r.source == "model"


def test_examples_have_valid_actions():
    ids = {a.id for a in ACTIONS} | {"unsupported", "ambiguous"}
    assert all(e["output"]["action"] in ids for e in load_examples())


def test_agent_endpoint(client):
    body = {"text": "오늘 뭐 해야 돼?", "actions": [a.model_dump() for a in ACTIONS], "context": {"now": "2026-11-02T10:00"}}
    r = client.post("/agent/plan", json=body)
    assert r.status_code == 200 and r.json()["action"] == "T01" and r.json()["params"] == {"date": "2026-11-02"}
