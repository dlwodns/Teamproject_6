from datetime import datetime

import pytest

from app.agent.plan import plan
from app.agent.rules_v1 import MUTATING, analyze
from app.llm.client import LLMError
from app.prompts.agent_v1 import load_examples
from app.schemas.agent import ActionSpec, PlanContext, PlanRequest
from tests.agent_oracle import RuleLikeLLM

ACTIONS = [ActionSpec(id=f"T{i:02d}", name=n) for i, n in enumerate(
    ["오늘_요약", "미처리_조회", "일괄_완료", "되돌리기", "나중에_처리", "무응답_확인", "회신_초안", "근거_설명",
     "리마인드_설정", "제외_처리", "중요_발신자_지정", "초안_작성", "기한_보기", "템플릿_전송"], start=1)]
NOW = datetime(2026, 11, 2, 10, 0)  # 월요일


@pytest.fixture
def fake_llm():
    """AI-D19: 행동은 모델이 고른다. 답을 넣지 않은 테스트는 v1.5 규칙과 같은 행동을 고르는 가짜 모델(tests/agent_oracle.py)."""
    return RuleLikeLLM()


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
    assert r.action == action and r.source == "model"



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
    ("이 뉴스레터 숨겨줘", "T10"),  # v1.4: 지시어는 고른 메일이 있어야 한다(아래 req에 M-9를 준다)
    ("앞으로 오 차장님 메일은 중요하게", "T11"),
    ("회의 취소 메일 박 대리에게 써줘", "T12"),  # '회의 취소'는 되돌리기가 아니다
    ("다음 주 마감 몰린 날 알려줘", "T13"),
])
def test_rule_paraphrases_v1_2(fake_llm, text, action):
    r = plan(req(text, selected=["M-9"]), fake_llm)
    assert r.action == action and r.source == "model"


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
    assert r.action is None and r.reason == reason and r.source == "model"


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
    # 모델에게도 가린 이름을 줄이거나 바꾸지 말고 그대로 옮기라고 알린다(되돌리지 못하면 연락처를 못 찾음, #201 리뷰)
    from app.prompts import agent_v1
    assert "김◯◯" in agent_v1.SYSTEM and "글자 그대로" in agent_v1.SYSTEM
    # backend가 가린 이름(BE-6)도 보낸 사람으로 본다 — backend가 되돌린 뒤 연락처를 찾는다
    for masked in ("김◯◯", "김◯◯2"):
        r = plan(req(f"{masked} 팀장님 건 다 처리했어"), fake_llm)
        assert r.target.sender == f"{masked} 팀장" and r.target.keyword is None


def test_deictic_uses_selection(fake_llm):
    r = plan(req("이거 완료", selected=["M-1"]), fake_llm)
    assert r.action == "T03" and r.target.mail_ids == ["M-1"]


def test_nudge_targets_awaiting_list_or_last_result(fake_llm):
    r = plan(req("답장 안 온 거 재촉 메일 보내줘"), fake_llm)
    assert r.params["template_kind"] == "nudge" and r.target.awaiting_reply
    r = plan(req("그 2건 재촉 메일 보내", last=["S-1", "S-2"]), fake_llm)
    assert r.target.mail_ids == ["S-1", "S-2"] and not r.target.awaiting_reply
    fake_llm.replies = [{"action": "T14", "selected": True}]  # '한 번 더 확인 요청' — 사이에 낱말이 끼어도 재촉(11-17)
    r = plan(req("이거 한 번 더 확인 요청하는 메일 보내 줘", selected=["S-4"]), fake_llm)
    assert r.params["template_kind"] == "nudge" and r.target.mail_ids == ["S-4"]


def test_unmatched_goes_to_model_and_is_validated(fake_llm):
    fake_llm.replies = [{"action": "T13", "when": "이번 달"}]
    r = plan(req("제출 날짜 몰린 날 언제야"), fake_llm)
    assert r.action == "T13" and r.source == "model" and r.prompt_version == "agent_v1.6"
    assert "메일 본문" not in fake_llm.calls[0]["user"]


def test_model_cannot_pick_action_outside_allowed_list(fake_llm):
    fake_llm.replies = [{"action": "T99_메일_신고"}]
    r = plan(req("스팸 메일 신고해줘"), fake_llm)
    assert r.action is None and r.reason == "unsupported"
    # backend가 허용하지 않은 행동은 모델 선택지(스키마 enum)에도 없다
    plan(req("답장 안 온 거 재촉 메일 보내줘", actions=ACTIONS[:13]), fake_llm)
    assert "T14" not in fake_llm.calls[-1]["system"]


def test_model_down_is_reported_not_guessed(fake_llm, client):
    # AI-D19: 모델이 못 고르면 규칙으로 짐작하지 않고 실패를 올린다. API는 503(backend: '지금은 명령을 처리할 수 없습니다')
    fake_llm.replies = [LLMError("엑사원 API 호출 실패: ConnectError")]
    with pytest.raises(LLMError):
        plan(req("오늘 뭐 해야 돼?"), fake_llm)
    fake_llm.replies = [LLMError("엑사원 API 호출 실패: ConnectError")]
    body = {"text": "오늘 뭐 해야 돼?", "actions": [a.model_dump() for a in ACTIONS], "context": {"now": "2026-11-02T10:00"}}
    r = client.post("/agent/plan", json=body)
    assert r.status_code == 503 and r.json()["detail"]["kind"] == "model_failed"


def test_delete_is_unsupported_without_model(fake_llm):
    r = plan(req("받은 메일 전부 삭제해"), fake_llm)
    assert r.action is None and r.reason == "unsupported"


@pytest.mark.parametrize("text, action", [
    ("이 메일 삭제해", "T03"),
    ("이 메일 휴지통으로 보내", "T05"),
    ("이 메일 스팸 신고해", "T03"),
    ("메일 다 지워줘", "T10"),  # AI-T6
    ("써 둔 회신 초안 내일 아침 9시에 예약 발송해 줘", "T05"),  # v4.1 엑사원 오탐(11-17)
])
def test_unsupported_wins_over_model_state_change(fake_llm, text, action):
    # #67 리뷰: 모델이 지원 외 지시에 가까운 상태 변경을 골라도 실행하지 않는다(backend는 1건 상태 변경을 확인 없이 바로 실행)
    fake_llm.replies = [{"action": action, "selected": True}]
    r = plan(req(text, selected=["7"]), fake_llm)
    assert r.action is None and r.reason == "unsupported" and len(fake_llm.calls) == 1


def test_model_ambiguous_asks_back(fake_llm):
    fake_llm.replies = [{"action": "ambiguous"}]
    r = plan(req("그 사람 거 어떻게 된 거야"), fake_llm)
    assert r.action is None and r.reason == "ambiguous" and r.source == "model"


def test_examples_have_valid_actions():
    ids = {a.id for a in ACTIONS} | {"T15", "unsupported", "ambiguous"}  # T15는 backend가 허용할 때만 프롬프트에 들어간다(AI-20)
    assert all(e["output"]["action"] in ids for e in load_examples())


def test_agent_endpoint(client):
    body = {"text": "오늘 뭐 해야 돼?", "actions": [a.model_dump() for a in ACTIONS], "context": {"now": "2026-11-02T10:00"}}
    r = client.post("/agent/plan", json=body)
    assert r.status_code == 200 and r.json()["action"] == "T01" and r.json()["params"] == {"date": "2026-11-02"}


# v1.3 안전 장치 — 규칙이 행동을 잡았어도 실행하지 않는 문장 (11/3 조사: BFCL '관련 없음' · 부정 지시)
@pytest.mark.parametrize("text, reason", [
    ("처리 안 한 거 완료 처리하지 마", "unsupported"),  # 부정 지시 + 상태 변경(T03). v1.4: 지시가 아닌 말은 지원 외(개발 세트 v2 기준)
    ("날씨 보여줘", "unsupported"),  # T02 '보여줘'만 걸린 메일 무관 요청
    ("영어로 번역해서 답장 써줘", "unsupported"),  # 지원 외 낱말이 T07보다 먼저
    ("보낸 메일 발송 취소", "unsupported"),  # 발송 취소는 되돌리기(T04)가 아니다
])
def test_guard_blocks_rule_hit(fake_llm, text, reason):
    r = plan(req(text), fake_llm)
    assert r.action is None and r.reason == reason and r.source == "model"


@pytest.mark.parametrize("text, action", [("방금 거 하나 취소해", "T04"), ("박 책임 메일 빼고 보여줘", "T02"), ("광고는 앞으로 안 보이게", "T10")])
def test_guard_keeps_normal_commands(fake_llm, text, action):
    assert plan(req(text), fake_llm).action == action


# ── v1.4 — 개발 세트 v2 오답을 증상별로 묶어 고친 원리. 문장은 모두 v2 · v1에 없는 새 문장이다 ──
L3 = ["S-1", "S-2", "S-3"]


@pytest.mark.parametrize("text, selected", [
    ("공지 메일은 완료 처리하지 마세요", []),
    ("그 뉴스레터는 숨기면 안 돼", ["M-1"]),
    ("굳이 재촉할 필요 없어", []),
    ("광고는 빼지 말고 그대로 둬", []),
    ("답장 초안 쓰지 마", ["M-1"]),  # 금지로 끝나면 초안(표시)도 만들지 않는다
])
def test_prohibition_is_not_a_command(fake_llm, text, selected):
    r = plan(req(text, selected=selected), fake_llm)
    assert r.action is None and r.reason == "unsupported" and r.source == "model"


@pytest.mark.parametrize("text, selected, action, field, value", [
    ("보고서 건은 미루지 말고 오늘 완료 처리해", [], "T03", "keyword", "보고서"),  # 부정은 '미루지'에만 걸린다
    ("완료 처리하지 말고 금요일에 다시 알려줘", ["M-1"], "T05", "mail_ids", ["M-1"]),
    ("박 책임 메일 말고 김 팀장 메일 보여줘", [], "T02", "sender", "김 팀장"),  # 'X 말고'는 대상에서도 뺀다
])
def test_negation_scope_keeps_main_command(fake_llm, text, selected, action, field, value):
    r = plan(req(text, selected=selected), fake_llm)
    assert r.action == action and r.source == "model" and getattr(r.target, field) == value


@pytest.mark.parametrize("text, selected, last, model_action, reason", [
    ("이건 아직 완료 처리하면 안 돼요", ["M-1"], [], "T03", "unsupported"),  # 하지 말라는 말뿐 — 모델이 행동을 골라도 되묻지 않는다(v1.6)
    ("그 건은 재촉하지 말고 좀 더 기다려 보자", [], ["S-6"], "T14", "unsupported"),
    ("완료 처리하지 말고 금요일에 다시 알려줘", ["M-1"], [], "T03", "ambiguous"),  # 다른 지시(미루기)가 남은 부정은 되묻는다
])
def test_model_mutation_on_forbidden_sentence(fake_llm, text, selected, last, model_action, reason):
    fake_llm.replies = [{"action": model_action, "selected": bool(selected)}]
    r = plan(req(text, selected=selected, last=last), fake_llm)
    assert r.action is None and r.reason == reason


@pytest.mark.parametrize("text, model_action", [
    ("중요 발신자로 등록됐어?", "T11"),  # 의문
    ("알림 9시로 설정돼 있지", "T09"),  # 물음표 없는 의문(음성)
    ("이거 완료된 거 맞지", "T03"),
    ("어제 공지 메일 다 처리했었어", "T03"),  # 대과거
    ("김 팀장이 다 처리했대", "T03"),  # 전해 들은 말
    ("지난주에 견적 건 미뤄 뒀었는데", "T05"),
    ("알림 시간 9시로 설정했어", "T09"),  # 한 일을 말한 것(완료 T03 밖의 과거형)
    ("이거 빼야 하나?", "T10"),
    ("이거 완료 처리할까 말까", "T03"),  # 망설임
])
def test_question_and_past_never_mutate_even_if_model_says_so(fake_llm, text, model_action):
    """규칙은 상태 변경 후보를 지우고 모델로 넘긴다. 모델이 상태 변경 행동을 골라도 안전장치가 되묻기로 바꾼다."""
    assert not set(analyze(text, NOW).hits) & MUTATING
    fake_llm.replies = [{"action": model_action, "selected": True}]
    r = plan(req(text, selected=["M-1"]), fake_llm)
    assert r.action is None and r.reason == "ambiguous" and r.source == "model"


@pytest.mark.parametrize("text", ["스누즈가 뭐야?", "템플릿 전송은 어떻게 해요?", "제외하는 방법 알려줘", "재촉 메일은 어디서 보내?"])
def test_howto_question_is_unsupported_without_model(fake_llm, text):
    r = plan(req(text), fake_llm)
    assert r.action is None and r.reason == "unsupported"


@pytest.mark.parametrize("text, action", [
    ("이 메일 금요일에 다시 알려줄래?", "T05"),  # 부탁형 물음은 지시다
    ("알림 시간 8시로 바꿔줄 수 있어?", "T09"),
    ("이 뉴스레터 빼 줄 수 있나요?", "T10"),
])
def test_request_question_still_executes(fake_llm, text, action):
    r = plan(req(text, selected=["M-1"]), fake_llm)
    assert r.action == action and r.source == "model"


@pytest.mark.parametrize("text, selected, action", [
    ("어제 재촉 메일 보냈는데 답장 안 온 거 보여줘", [], "T06"),  # 앞 절의 과거 서술은 배경이다
    ("다 처리했는데 완료로 바꿔줘", ["M-1"], "T03"),
    ("제외한 메일 목록 보여줘", [], "T02"),  # 관형절 '제외한'은 지시가 아니다
    ("완료 처리한 거 보여줘", [], "T02"),
    ("검토 건 완료했다고 표시해줘", [], "T03"),  # '~했다고 표시'는 지시다
])
def test_background_clause_does_not_trigger(fake_llm, text, selected, action):
    assert plan(req(text, selected=selected), fake_llm).action == action


@pytest.mark.parametrize("text, model_action", [
    ("팀 회의 다음 주로 미뤄줘", "T05"),
    ("출장 일정 연기해줘", "T05"),
    ("회의 끝났어", "T03"),
    ("휴가 일정에서 빼줘", "T10"),
    ("금요일 주간회의 다음 주로 미뤄 줘", "T05"),  # 붙여 쓴 회의 이름(v4.1 엑사원 오탐, 11-17)
])
def test_non_mail_target_is_vetoed(fake_llm, text, model_action):
    """회의 · 일정 같은 메일 아닌 대상: 규칙이 후보를 지우고, 모델이 같은 행동을 다시 골라도 실행하지 않는다."""
    assert not set(analyze(text, NOW).hits) & MUTATING
    fake_llm.replies = [{"action": model_action}]
    r = plan(req(text), fake_llm)
    assert r.action is None and r.reason == "ambiguous"


@pytest.mark.parametrize("text", ["캘린더에 내일 미팅 추가해줘", "알림 소리 바꿔줘", "다크 모드로 바꿔줘", "언어 설정 영어로 바꿔줘"])
def test_calendar_and_app_settings_are_unsupported(fake_llm, text):
    r = plan(req(text), fake_llm)
    assert r.action is None and r.reason == "unsupported"


@pytest.mark.parametrize("text, action", [
    ("회의 연기 안내 메일 김 대리한테 써줘", "T12"),  # 메일 주제인 '회의 연기'는 막지 않는다
    ("세미나 관련 메일 금요일에 다시 알려줘", "T05"),
])
def test_event_word_as_mail_topic_is_kept(fake_llm, text, action):
    assert plan(req(text), fake_llm).action == action


@pytest.mark.parametrize("text, selected, last, key, value", [
    ("이거 사흘 뒤에 다시 알려줘", ["M-1"], [], "until", "2026-11-05T08:30:00"),
    ("계약 건 한 시간 뒤에 리마인드 해줘", [], [], "until", "2026-11-02T11:00:00"),
    ("일주일 넘게 답장 안 온 메일 보여줘", [], [], "min_days", 7),
    ("아침 알림 열 시 반으로 바꿔줘", [], [], "time", "10:30"),
    ("알림 시간 7시 반으로 해줘", [], [], "time", "07:30"),  # 알림 시각은 업무 마감 규칙(7시 → 19시)을 쓰지 않는다
    ("기한 세 시간 전에 알림 오게 설정해", [], [], "hours", 3),
    ("이 메일 다음 주로 미뤄", ["M-1"], [], "until", "2026-11-09T08:30:00"),  # 요일 없는 '다음 주' → 월요일
    ("오후 3시에 다시 알려줘", ["M-1"], [], "until", "2026-11-02T15:00:00"),  # 시각만 있으면 오늘
    ("발주 건 내일 오후에 다시 알려줘", [], [], "until", "2026-11-03T18:00:00"),  # '오후'를 08:30으로 당기지 않는다(dates 규칙)
])
def test_korean_numerals_and_relative_time(fake_llm, text, selected, last, key, value):
    r = plan(req(text, selected=selected, last=last), fake_llm)
    assert r.source == "model" and r.params[key] == value


@pytest.mark.parametrize("text, selected, last, expected", [
    ("그 두 건 재촉 메일 보내", [], ["S-1", "S-2"], ["S-1", "S-2"]),  # 한글 수사 + 직전 결과
    ("그거 다 완료 처리해줘", [], L3, L3),  # '그거'는 고른 메일이 없으면 직전 결과
    ("방금 나온 목록 전부 완료 처리", [], L3, L3),
    ("이 세 건 재촉 메일 보내줘", ["M-1", "M-2", "M-3"], [], ["M-1", "M-2", "M-3"]),
    ("다 처리했어", [], L3, L3),  # 대상 낱말 없이 '다'만 있으면 직전 결과
    ("빼줘", ["M-1"], [], ["M-1"]),  # 대상 낱말 없는 짧은 지시는 고른 메일
    ("방금 목록에서 첫 번째 거 완료 처리해", [], L3, L3[:1]),  # 순번은 그중 하나(11-17)
    ("방금 나온 목록 두 번째 거 완료 처리해", [], L3, L3[1:2]),
])
def test_reference_resolution(fake_llm, text, selected, last, expected):
    r = plan(req(text, selected=selected, last=last), fake_llm)
    assert r.action is not None and r.target.mail_ids == expected


def test_surname_i_is_not_deictic(fake_llm):
    r = plan(req("이 팀장님 메일 다 처리했어"), fake_llm)
    assert r.action == "T03" and r.target.sender == "이 팀장" and r.target.mail_ids == []


@pytest.mark.parametrize("text", [
    "그 메일 빼줘", "이거 완료", "그 사람한테 재촉 메일 보내",  # 가리킬 메일이 없는 지시어
    "숨겨줘", "다 미뤄", "중요로 해줘", "알림 설정 바꿔줘", "메일 써줘",  # 대상 · 값이 빠진 지시
    "견적 건은?", "아까 그 메일", "빨리 해줘",  # 행동 없는 말 조각 · 일반 동사
])
def test_missing_target_or_value_asks_back(fake_llm, text):
    r = plan(req(text), fake_llm)
    assert r.action is None and r.reason == "ambiguous" and r.source == "model"


@pytest.mark.parametrize("text, action", [
    ("기한 하루 전에 알림 오게 바꿔줘", "T09"),  # 기한 보기(T13)가 아니라 설정
    ("매일 아침 일곱 시에 알려줘", "T09"),  # 매일 → 설정, 이 메일 미루기(T05) 아님
    ("이 메일 기한이 왜 금요일이야?", "T08"),
    ("김 대리 메일 중요 발신자로 지정", "T11"),  # '메일 중요'를 '메일 중'(T02)으로 읽지 않는다
    ("투데이 브리핑", "T01"),
    ("오늘 거 정리해", None),  # '정리'만으로는 요약이 아니다
])
def test_collision_order(fake_llm, text, action):
    assert plan(req(text, selected=["M-1"]), fake_llm).action == action


def test_quoted_template_name_is_data(fake_llm):
    r = plan(req("'처리 완료했습니다' 템플릿 보내줘", selected=["M-1"]), fake_llm)
    assert r.action == "T14" and r.params["template_name"] == "처리 완료했습니다" and r.target.mail_ids == ["M-1"]


def test_model_mutation_without_markers_still_runs(fake_llm):
    """안전장치는 표지가 있을 때만 막는다 — 규칙이 못 잡은 평범한 지시는 모델 결과대로 실행한다."""
    fake_llm.replies = [{"action": "T10", "selected": True}]
    r = plan(req("이 광고성 거 걸러줘", selected=["M-1"]), fake_llm)
    assert r.action == "T10" and r.source == "model" and r.target.mail_ids == ["M-1"]
    fake_llm.replies = [{"action": "T10"}]  # 모델이 골라도 대상이 없으면 되묻는다
    r = plan(req("걸러줘"), fake_llm)
    assert r.action is None and r.reason == "ambiguous" and r.source == "model"
