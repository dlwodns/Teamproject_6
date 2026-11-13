"""문맥 기억 추출 /memory/extract (PL-16, BE-D21). 엑사원 대신 FakeLLM."""
from fastapi.testclient import TestClient

from app.api.deps import llm_dep
from app.llm.client import LLMError
from app.main import app
from tests.conftest import FakeLLM

BODY = ("안녕하세요, 한빛은행 IT기획부 장민호 차장입니다.\n저는 이번 한빛은행 2단계 전환 사업을 맡고 있습니다.\n"
        "일정 초안을 공유해 주실 수 있을지요.")
REQ = {"mail_id": 7, "from": "minho.jang@hanbitbank.example", "sender_name": "장민호", "subject": "일정 문의",
       "body": BODY, "owner": {"email": "junho.lee@lgcns.example", "name": "이준호", "position": "팀장"}}


def _call(replies):
    fake = FakeLLM(replies)
    app.dependency_overrides[llm_dep] = lambda: fake
    try:
        with TestClient(app) as c:
            return c.post("/memory/extract", json=REQ).json(), fake
    finally:
        app.dependency_overrides.clear()


def test_extracts_and_filters():
    out, fake = _call([{"facts": [
        {"kind": "works_on", "value": "한빛은행 2단계 전환", "evidence": "저는 이번 한빛은행 2단계 전환 사업을 맡고 있습니다."},
        {"kind": "org", "value": "한빛은행 IT기획부", "evidence": "안녕하세요, 한빛은행 IT기획부 장민호 차장입니다."},
        {"kind": "org", "value": "다른 값", "evidence": "안녕하세요, 한빛은행 IT기획부 장민호 차장입니다."},  # 같은 종류 두 번째
        {"kind": "birthday", "value": "5월", "evidence": "저는"},  # 없는 종류
        {"kind": "works_on", "value": "지어낸 사업", "evidence": "본문에 없는 문장"},
    ]}])
    assert out["mail_id"] == "7" and out["source"] == "exaone" and out["prompt_version"] == "memory_v1"
    assert [(f["kind"], f["value"]) for f in out["facts"]] == [("works_on", "한빛은행 2단계 전환"),
                                                                ("org", "한빛은행 IT기획부")]
    assert "보낸 사람: 장민호 <minho.jang@hanbitbank.example>" in fake.calls[0]["user"]


def test_hallucinated_evidence_and_long_value_dropped():
    out, _ = _call([{"facts": [{"kind": "works_on", "value": "가" * 41, "evidence": "일정 초안을 공유해 주실 수 있을지요."},
                               {"kind": "org", "value": "A사", "evidence": "A사 소속입니다"}]}])
    assert out["facts"] == []


def test_model_unavailable_is_fallback():
    out, _ = _call([LLMError("연결 안 됨")])
    assert out["facts"] == [] and out["source"] == "none" and out["fallback"].startswith("llm_unavailable")
