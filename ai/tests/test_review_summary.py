"""일일 · 주간 회고 머리 문장(AI-29, io_spec 3.3 · 3.4절): 코드 문장 · 모델 문장 검증 · 호출 조건."""
from datetime import datetime

import httpx

from app.agent.assist import evening_facts, summarize, weekly_facts
from app.core.config import Settings
from app.llm.client import ExaoneApiClient, LLMError, Timed
from app.prompts import assist_v4
from app.schemas.assist import SummarizeRequest

NOW = datetime(2026, 11, 20, 17, 30)  # 금요일


class FakeLLM:
    def __init__(self, text: str | Exception):
        self.text, self.calls = text, []

    def chat_text(self, system, user):
        self.calls.append((system, user))
        if isinstance(self.text, Exception):
            raise self.text
        return self.text


def item(text, sender="장민호 차장", due=None, done=None, sup=False, event=None):
    return {"task_id": "1", "text": text, "sender": sender, "is_superior": sup, "is_event": event, "due_at": due, "done_at": done}


def evening(**kw):
    return SummarizeRequest(mode="evening", now=NOW, sections=[
        {"id": "done_today", "items": [item("예산안 검토", "한상우 사업단장", sup=True), item("회의록 공유")]},
        {"id": "remaining", "items": [item("보고서 제출", due=datetime(2026, 11, 19, 18)), item("자료 정리", due=datetime(2026, 11, 21, 18))]},
        {"id": "due_tomorrow", "items": [item("킥오프 미팅 참석", "백승현 과장", due=datetime(2026, 11, 21, 10))]},
    ], **kw)


def weekly(**kw):
    return SummarizeRequest(mode="weekly", now=NOW, sections=[
        {"id": "done_week", "items": [item("A", due=datetime(2026, 11, 17, 18), done=datetime(2026, 11, 18, 9)), item("B")]},
        {"id": "carry_over", "items": [item("C", "한상우 사업단장", sup=True)]},
        {"id": "waiting", "items": [item("D"), item("E")]},
        {"id": "due_next_week", "items": [item("F", due=datetime(2026, 11, 24, 9)), item("G", due=datetime(2026, 11, 24, 15)),
                                          item("H", due=datetime(2026, 11, 26, 9))]},
    ], **kw)


def test_evening_code_sentence_counts_from_sections():
    h = evening_facts(evening())
    assert h.counts == {"done_today": 2, "remaining": 2, "due_tomorrow": 1}
    assert "오늘 완료한 업무는 2건이며, 상급자 건은 한상우 사업단장의 '예산안 검토'입니다." in h.code
    assert "남은 미처리 업무는 2건이고, 그중 기한이 지난 것은 1건입니다." in h.code
    assert "10:00 백승현 과장 '킥오프 미팅 참석'" in h.code


def test_weekly_code_sentence_late_carry_peak():
    h = weekly_facts(weekly())
    assert "이번 주 완료한 업무는 2건이며, 그중 기한 후 완료는 1건입니다." in h.code
    assert "다음 주로 넘어가는 업무는 1건이며, 상급자 건은 한상우 사업단장의 'C'입니다. 회신을 기다리는 건은 2건입니다." in h.code
    assert "화요일에 2건으로 가장 많습니다" in h.code


def test_empty_review_skips_model():
    llm = FakeLLM("무엇이든")
    r = summarize(SummarizeRequest(mode="weekly", now=NOW), llm)
    assert r.source == "code" and r.fallback == "묶음 없음" and not llm.calls
    assert r.text == "이번 주 완료한 업무는 없습니다. 다음 주로 넘어가는 업무는 없습니다. 다음 주 기한인 업무는 없습니다."


def test_model_sentence_passes_check():
    text = "오늘 완료한 업무는 2건이며 한상우 사업단장의 예산안 검토가 포함됩니다. 남은 업무는 2건이고 그중 1건은 기한이 지났습니다."
    r = summarize(evening(), FakeLLM(text))
    assert r.source == "exaone" and r.text == text and r.prompt_version == "assist_v4"
    assert r.section_counts == {"done_today": 2, "remaining": 2, "due_tomorrow": 1}


def test_model_sentence_rejected_falls_back_to_code():
    for bad, why in (("남은 업무는 7건입니다.", "입력에 없는 숫자"), ("내일 일정부터 챙기세요.", "권유 표현"),
                     ("김철수 부장의 건이 남아 있습니다.", "입력에 없는 사람")):
        r = summarize(evening(), FakeLLM(bad))
        assert r.source == "code" and why in r.fallback and r.text == evening_facts(evening()).code


def test_model_failure_and_no_model():
    assert summarize(evening(), FakeLLM(LLMError("제한 시간"))).fallback == "제한 시간"
    llm = FakeLLM("x")
    r = summarize(weekly(use_model=False), llm)
    assert r.source == "code" and not llm.calls and r.section_counts["due_next_week"] == 3


def test_timed_passes_effort_only_to_exaone():
    seen = {}

    def handler(request: httpx.Request):
        import json
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {}})

    s = Settings(exaone_api_key="k", exaone_reasoning_effort="max")
    api = ExaoneApiClient(s, transport=httpx.MockTransport(handler))
    assert Timed(api, 600, assist_v4.SUMMARY_REASONING).chat_text("s", "u") == "ok"
    assert seen["reasoning_effort"] == assist_v4.SUMMARY_REASONING  # 호출 강도가 설정값(max)보다 먼저
    Timed(api, 600).chat_text("s", "u")
    assert seen["reasoning_effort"] == "max"

    class NoEffort:
        accepts_timeout = True

        def chat_text(self, system, user, *, timeout=None):
            return f"t={timeout}"

    assert Timed(NoEffort(), 600, "low").chat_text("s", "u") == "t=600"  # 강도 칸이 없는 클라이언트(ollama 등)에는 넘기지 않는다


def test_check_review_cases():
    """AI-29 리뷰: 인용한 업무 이름 속 '바랍니다'는 통과 · 지시는 걸림 · 프로젝트/이사회는 사람 아님 · 뺀 건수 · 요일."""
    from app.agent.assist import check_text
    src = "[미처리] 5건\n[기한 지남] 2건\n[가장 몰린 요일] 화요일 2건\n- 장민호 차장: 누리물류 프로젝트"
    ok = {5, 2, 3}
    people = {"장민호 차장"}
    assert check_text("장민호 차장의 '참석 여부 회신 바랍니다'가 남아 있습니다.", src, ok, people) is None
    assert "권유" in check_text("오늘 안에 처리해야 합니다.", src, ok, people)
    assert check_text("누리물류 프로젝트 건이 있습니다.", src, ok, people) is None
    assert check_text("기한이 지나지 않은 미처리는 3건입니다.", src, ok, people) is None
    assert "요일" in check_text("수요일에 가장 많습니다.", src, ok, people)
