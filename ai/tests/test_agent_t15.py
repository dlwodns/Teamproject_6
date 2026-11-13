"""T15 일정_등록 명령 해석 (AI-20 · D50, agent_rules_v1.5). CNE 앱 캘린더에만 넣는다. 시각을 지어내지 않는다."""
from datetime import datetime

import pytest

from app.agent.plan import plan
from app.agent.rules_v1 import event_title
from app.prompts.agent_v1 import render_system
from app.schemas.agent import ActionSpec
from tests.test_agent import ACTIONS, fake_llm, req  # noqa: F401  fake_llm: 규칙과 같은 행동을 고르는 가짜 모델

WITH_T15 = ACTIONS + [ActionSpec(id="T15", name="일정_등록")]
NOW = datetime(2026, 11, 2, 10, 0)  # 월요일 (tests.test_agent와 같다)


def t15(text, selected=()):
    return req(text, selected=selected, actions=WITH_T15)


@pytest.mark.parametrize("text, start, end, title", [
    ("내일 오후 3시에 김 팀장님이랑 예산 회의 잡아줘", "2026-11-03T15:00:00", None, "김 팀장님이랑 예산 회의"),
    ("캘린더에 11/5 14:00~15:30 분기 리뷰 넣어줘", "2026-11-05T14:00:00", "2026-11-05T15:30:00", "분기 리뷰"),
    ("다음 주 수요일 10시 고객 미팅 잡아줘", "2026-11-11T10:00:00", None, "고객 미팅"),
    ("목요일 오후 2시 반에 신규 프로젝트 킥오프 미팅 잡아 줘", "2026-11-05T14:30:00", None, "신규 프로젝트 킥오프 미팅"),
    ("11월 20일 10시부터 12시까지 보안 교육 일정 추가해줘", "2026-11-20T10:00:00", "2026-11-20T12:00:00", "보안 교육 일정"),
    ("3시에 팀 회의 잡아줘", "2026-11-02T15:00:00", None, "팀 회의"),  # 날짜 없으면 오늘
    ("9시에 팀 회의 잡아줘", "2026-11-03T09:00:00", None, "팀 회의"),  # 오늘 9시는 지났다 → 내일
    ("내일 3시 회의 일정 캘린더에 등록해줘", "2026-11-03T15:00:00", None, "회의 일정"),
])
def test_t15_params(fake_llm, text, start, end, title):
    r = plan(t15(text), fake_llm)
    assert r.action == "T15" and r.action_name == "일정_등록" and r.source == "model"
    assert r.params == {"start": start, "end": end, "title": title}


def test_t15_target_is_only_selected_mail(fake_llm):
    # 사람 이름 · 날짜는 일정 내용이다. 메일을 찾는 조건으로 넘기지 않는다
    r = plan(t15("내일 오후 3시에 김 팀장님이랑 예산 회의 잡아줘"), fake_llm)
    assert r.target.sender is None and r.target.date_range is None and r.target.keyword is None and r.target.mail_ids == []


def test_t15_selected_mail_without_time(fake_llm):
    # 고른 메일의 회의: 시각은 backend가 그 메일 일정(due_time_stated가 true인 것)으로 채운다
    r = plan(t15("이 회의 캘린더에 등록해줘", selected=[9]), fake_llm)
    assert r.action == "T15" and r.target.mail_ids == ["9"] and r.params == {"start": None, "end": None, "title": None}


@pytest.mark.parametrize("text, selected", [
    ("내일 회의 잡아줘", ()),  # 날짜만, 시각 없음 → 18:00을 지어내지 않는다
    ("금요일 오전에 면담 잡아줘", ()),  # '오전'은 시각이 아니다
    ("금요일 오전에 면담 잡아줘", (9,)),  # 고른 메일이 있어도 말한 날짜와 다를 수 있다 → 되묻는다
    ("이 회의 캘린더에 등록해줘", ()),  # 가리킨 메일이 없다
    ("회의 잡아줘", ()),  # 언제인지 없다
])
def test_t15_asks_when_time_missing(fake_llm, text, selected):
    r = plan(t15(text, selected=selected), fake_llm)
    assert r.action is None and r.reason == "ambiguous"


def test_t15_with_draft_in_one_sentence_is_not_half_done(fake_llm):
    # 공유안 시연 문장: 초안과 일정 등록을 한 번에 시켰다 → 모델이 '하나로 못 정함'이라고 하면 되묻는다(AI-D19: 판단은 모델)
    r = plan(t15("김 대리 메일 회신 초안 쓰고 내일 오전 10시 회의 잡아줘", selected=[3]), fake_llm)
    assert r.action is None and r.reason == "ambiguous" and r.source == "model"


@pytest.mark.parametrize("text, action", [
    ("캘린더 보여줘", "T13"),  # 보기는 그대로 기한 보기
    ("이번 주 기한 캘린더로 보여줘", "T13"),
    ("회의 일정 잡는 메일 박 대리에게 써줘", "T12"),  # 메일 주제
    ("팀 회의 다음 주로 미뤄줘", None),  # 일정 변경은 지원 외(메일 아닌 대상)
])
def test_t15_does_not_steal_other_commands(fake_llm, text, action):
    r = plan(t15(text), fake_llm)  # 가짜 모델이 v1.5 규칙과 같은 행동을 고른다(tests/agent_oracle.py)
    assert r.action == action


@pytest.mark.parametrize("text", ["회의 잡지 마", "회의 잡았어", "회의 잡는 방법이 뭐야"])
def test_t15_negation_past_howto(fake_llm, text):
    fake_llm.replies = [{"action": "T15"}]
    r = plan(t15(text), fake_llm)
    assert r.action is None


@pytest.mark.parametrize("text", ["내일 3시 회의 일정 캘린더에 등록해줘", "김 팀장님이랑 목요일 오후 3시에 회의 잡아 줘"])
def test_without_t15_in_registry_still_unsupported(fake_llm, text):
    # backend가 T15를 허용하기 전(봉인된 명령 평가 v2 ~ v4 포함)에는 이전과 같이 지원 외다
    r = plan(req(text), fake_llm)
    assert r.action is None and r.reason == "unsupported"


def test_model_path_uses_when(fake_llm):
    # 규칙이 못 잡은 말투 → 모델이 T15와 when을 낸다 → 같은 코드로 시각 · 제목을 뽑는다
    fake_llm.replies = [{"action": "T15", "when": "11/6 16:00"}]
    r = plan(t15("거래처랑 보는 거 그날로 박아 둬"), fake_llm)
    assert r.action == "T15" and r.source == "model" and r.params["start"] == "2026-11-06T16:00:00"


def test_prompt_shows_t15_examples_only_when_allowed():
    assert "T15" not in render_system(ACTIONS)
    assert '"action": "T15"' in render_system(WITH_T15)


@pytest.mark.parametrize("text, title", [
    ("이 회의 캘린더에 등록해줘", None),
    ("내일 10시 일정 잡아줘", None),
    ("캘린더에 11/12 14:00 분기 리뷰 넣어줘", "분기 리뷰"),
])
def test_event_title(text, title):
    assert event_title(text) == title


# ── 엣지 케이스 (11/10 사용자 점검) ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text", ["3일 뒤 오후 2시 회의 잡아줘", "다음 주에 2시 회의 잡아줘", "주말에 10시 모임 잡아줘",
                                  "금요일 17시 마감 전 리뷰 회의 잡아줘"])
def test_t15_relative_or_deadline_time_asks(fake_llm, text):
    # 4. 상대 시점을 오늘로 두지 않는다 · 1. 마감 시각을 회의 시각으로 쓰지 않는다 → 되묻기
    r = plan(t15(text), fake_llm)
    assert r.action is None and r.reason == "ambiguous"


@pytest.mark.parametrize("text, start, end", [
    ("모레 2시 회의 잡아줘", "2026-11-04T14:00:00", None),
    ("11/5 23:30~00:30 야간 점검 일정 잡아줘", "2026-11-05T23:30:00", "2026-11-06T00:30:00"),  # 2. 자정 넘김
])
def test_t15_dates_edge(fake_llm, text, start, end):
    r = plan(t15(text), fake_llm)
    assert r.action == "T15" and r.params["start"] == start and r.params["end"] == end


@pytest.mark.parametrize("when", ["11/5(목) 14:00~15:30", "목요일 오후 2시 반", "내일 10시부터 12시까지", "11/5 23:30~00:30"])
def test_command_and_mail_use_same_clock(fake_llm, when):
    # 4. 명령과 메일 회의 시각이 같은 코드로 읽혀 같은 값이 나온다(기준이 어긋나지 않는다)
    from app.pipeline.dates import parse_event_at, parse_event_end
    from tests.test_classify import mail, run, task
    r = plan(t15(f"{when} 회의 잡아줘"), fake_llm)
    m, _ = run(mail(f"일시: {when}\n회의에 참석 부탁드립니다."), "요청", task("일정참석", "회의 참석"))
    cls = m.tasks[0]
    ref = parse_event_at(when, NOW)
    assert r.params["start"] == cls.due_at.isoformat() == ref.due_at.isoformat()
    assert r.params["end"] == (cls.end_at.isoformat() if cls.end_at else None) == (
        e.isoformat() if (e := parse_event_end(when, ref.due_at)) else None)


# ── 5. T15를 허용한 /agent/plan 엔드포인트: 실행 · 되묻기 흐름 전체 ───────────────────────────────
def body(text, selected=(), actions=WITH_T15):
    return {"text": text, "actions": [a.model_dump() for a in actions],
            "context": {"now": "2026-11-02T10:00:00+09:00", "selected_mail_ids": list(selected)}}


def test_api_t15_executes(client, fake_llm):
    r = client.post("/agent/plan", json=body("내일 오후 3시에 김 팀장님이랑 예산 회의 잡아줘")).json()
    assert r["action"] == "T15" and r["action_name"] == "일정_등록" and r["source"] == "model" and r["reason"] is None
    assert r["params"] == {"start": "2026-11-03T15:00:00", "end": None, "title": "김 팀장님이랑 예산 회의"}
    assert r["target"]["sender"] is None and r["target"]["mail_ids"] == []


def test_api_t15_selected_mail(client):
    # 3. 고른 메일: start는 null — backend는 그 메일 일정참석 할 일이 due_time_stated=true일 때만 due_at을 쓰고, 아니면 되묻는다
    r = client.post("/agent/plan", json=body("이 회의 캘린더에 등록해줘", selected=[42])).json()
    assert r["action"] == "T15" and r["target"]["mail_ids"] == ["42"] and r["params"] == {"start": None, "end": None, "title": None}


@pytest.mark.parametrize("text, selected", [("내일 회의 잡아줘", ()), ("이 회의 캘린더에 등록해줘", ()), ("3일 뒤 2시 회의 잡아줘", ()),
                                            ("김 대리 메일 회신 초안 쓰고 내일 오전 10시 회의 잡아줘", (3,))])
def test_api_t15_asks(client, fake_llm, text, selected):
    r = client.post("/agent/plan", json=body(text, selected)).json()
    assert r["action"] is None and r["reason"] == "ambiguous" and r["params"] == {}


def test_api_t15_model_path(client, fake_llm):
    fake_llm.replies = [{"action": "T15", "when": "11/6 16:00"}]
    r = client.post("/agent/plan", json=body("거래처랑 보는 거 그날로 박아 둬")).json()
    assert r["action"] == "T15" and r["source"] == "model" and r["params"]["start"] == "2026-11-06T16:00:00"
    assert r["prompt_version"] == "agent_v1.3"


def test_api_t15_model_without_time_asks(client, fake_llm):
    # 모델이 T15를 골라도 시각이 없으면 실행하지 않는다(slots_ok)
    fake_llm.replies = [{"action": "T15", "when": "다음 주"}]
    r = client.post("/agent/plan", json=body("거래처랑 보는 거 언제 한번 박아 둬")).json()
    assert r["action"] is None and r["reason"] == "ambiguous" and r["source"] == "model"


def test_api_t15_model_vetoed_on_negation(client, fake_llm):
    fake_llm.replies = [{"action": "T15", "when": "내일 3시"}]
    r = client.post("/agent/plan", json=body("내일 3시 그거는 박아 두지 마")).json()
    assert r["action"] is None


def test_api_without_t15_is_unsupported(client, fake_llm):
    r = client.post("/agent/plan", json=body("내일 오후 3시에 예산 회의 잡아줘", actions=ACTIONS)).json()
    assert r["action"] is None and r["reason"] == "unsupported"


def test_t15_not_allowed_does_not_beat_existing(fake_llm):
    # T15가 허용되기 전에는 충돌 규칙으로 기존 행동을 지우지 않는다(v1.4와 같다)
    from app.agent.rules_v1 import analyze
    text = "캘린더에 이번 주 기한 올려서 보여줘"
    assert "T15" not in analyze(text, NOW, {a.id for a in ACTIONS}).hits
    assert "T15" in analyze(text, NOW, {a.id for a in WITH_T15}).hits


@pytest.mark.parametrize("text", ["11/31 3시 회의 잡아줘", "13/5 10시 고객 미팅 잡아줘", "2월 30일 2시 리뷰 잡아줘"])
def test_t15_unreadable_date_asks(fake_llm, text):
    # 없는 날짜('11/31')를 건너뛰고 시각만 읽으면 오늘 · 내일 일정이 된다(11/31 → 11/3). 날짜를 말했는데 못 읽으면 되묻는다
    r = plan(t15(text), fake_llm)
    assert r.action is None and r.reason == "ambiguous"
