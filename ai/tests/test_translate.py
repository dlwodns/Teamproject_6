"""메일 번역 (AI-32): 누를 때만 1회, 40자 미만 · 한국어는 부르지 않는다, 원문을 번역처럼 내지 않는다."""
from app.agent.translate import translate
from app.llm.client import LLMError
from app.schemas.assist import TranslateRequest
from tests.conftest import FakeLLM

EN = "Could you send us the signed test plan by noon Monday? Please also confirm the go-live checklist."


def test_translates_once():
    llm = FakeLLM([{"text": "서명한 테스트 계획서를 월요일 정오까지 보내 주시겠어요?"}])
    r = translate(TranslateRequest(text=EN), llm)
    assert r.source == "exaone" and r.text.startswith("서명한") and r.lang == "en" and len(llm.calls) == 1


def test_short_or_korean_is_not_sent_to_model():
    llm = FakeLLM([])
    assert translate(TranslateRequest(text="Thanks, see you."), llm).fallback == "40자 미만"
    assert translate(TranslateRequest(text="회의 자료를 금요일까지 보내 주세요. " * 3), llm).fallback == "이미 한국어"
    assert llm.calls == []


def test_echoed_original_or_failure_is_not_a_translation():
    r = translate(TranslateRequest(text=EN), FakeLLM([{"text": EN}]))
    assert r.text == "" and r.source == "none" and r.fallback == "번역문이 한국어가 아님"
    r = translate(TranslateRequest(text=EN), FakeLLM([LLMError("x")]))
    assert r.text == "" and r.fallback.startswith("모델 호출 실패")
