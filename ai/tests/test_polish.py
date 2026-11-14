"""답장 다듬기 POST /polish. 엑사원 대신 FakeLLM. 모델이 내용을 바꾸면 받은 글을 그대로 돌려준다."""
import pytest

from app.agent.polish import check, polish
from app.llm.client import LLMError
from app.prompts import polish_v1
from app.schemas.assist import PolishRequest
from tests.conftest import FakeLLM

TEXT = "확인했습니다 내일 오후3시까지 자료 보내드릴게요 [전화번호 1]로 연락주세요"


def _req(text=TEXT, style="polite", mail=None):
    return PolishRequest(text=text, style=style, mail=mail)


def test_endpoint_returns_polished_text(client, fake_llm):
    fake_llm.replies = [{"text": "확인했습니다. 내일 오후 3시까지 자료를 보내 드리겠습니다. [전화번호 1]로 연락 주세요."}]
    r = client.post("/polish", json={"text": TEXT, "style": "polite",
                                     "mail": {"subject": "자료 요청", "body": "김◯◯입니다. 자료 부탁드립니다.", "sender": "user1@x.example"}})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "exaone" and body["changed"] and body["style"] == "polite"
    assert body["text"].startswith("확인했습니다.") and body["prompt_version"] == "polish_v1"
    call = fake_llm.calls[0]
    assert "다듬기 방식: 정중하게" in call["user"] and "원 메일 본문(맥락만)" in call["user"] and TEXT in call["user"]


@pytest.mark.parametrize("style", list(polish_v1.STYLES))
def test_every_style_has_instruction(style, fake_llm):
    fake_llm.replies = [{"text": TEXT}]
    polish(_req(style=style), fake_llm)
    name, how = polish_v1.STYLES[style]
    assert f"다듬기 방식: {name} — {how}" in fake_llm.calls[0]["user"]


@pytest.mark.parametrize(("after", "reason"), [
    ("", "빈 결과"),
    ("확인했습니다. 내일 오후 4시까지 보내 드리겠습니다. [전화번호 1]", "받은 글에 없던 숫자"),  # 3시 → 4시
    ("확인했습니다. 11월 15일 오후 3시까지 보내 드리겠습니다. [전화번호 1]", "받은 글에 없던 숫자"),
    ("확인했습니다. 내일 오후 3시까지 보내 드리겠습니다.", "가려 둔 값 1개가 사라짐"),  # 전화번호를 뺌
    ("박◯◯ 책임님, 내일 오후 3시까지 보내 드리겠습니다. [전화번호 1]", "없던 가린 값"),  # 없던 사람
    ("가" * 1000, "너무 긴 결과"),
])
def test_unsafe_result_returns_original(fake_llm, after, reason):
    fake_llm.replies = [{"text": after}]
    r = polish(_req(), fake_llm)
    assert r.text == TEXT and not r.changed and r.source == "none" and r.fallback.startswith(reason)


def test_name_from_original_mail_is_allowed_in_greeting(fake_llm):
    mail = {"subject": "자료 요청", "body": "자료 부탁드립니다.\n김◯◯ 드림", "sender": "user2@x.example"}
    fake_llm.replies = [{"text": "김◯◯ 팀장님, 내일 오후 3시까지 자료를 보내 드리겠습니다. [전화번호 1]로 연락 주세요."}]
    r = polish(_req(mail=mail), fake_llm)
    assert r.source == "exaone" and r.text.startswith("김◯◯ 팀장님")


def test_list_numbers_from_clear_style_are_not_invented_numbers(fake_llm):
    fake_llm.replies = [{"text": "1. 내일 오후 3시까지 자료를 보냅니다.\n2. [전화번호 1]로 연락 주세요."}]
    assert polish(_req(style="clear"), fake_llm).source == "exaone"


def test_quotes_around_result_are_removed(fake_llm):
    fake_llm.replies = [{"text": '"확인했습니다. 내일 오후 3시까지 보내 드리겠습니다. [전화번호 1]"'}]
    assert polish(_req(), fake_llm).text == "확인했습니다. 내일 오후 3시까지 보내 드리겠습니다. [전화번호 1]"


def test_model_failure_returns_original(fake_llm):
    fake_llm.replies = [LLMError("시간 초과")]
    r = polish(_req(), fake_llm)
    assert (r.text, r.changed, r.source) == (TEXT, False, "none") and "모델 호출 실패" in r.fallback


def test_same_text_is_not_changed(fake_llm):
    fake_llm.replies = [{"text": TEXT}]
    r = polish(_req(style="proofread"), fake_llm)
    assert r.source == "exaone" and not r.changed


@pytest.mark.parametrize("body", [{"text": "", "style": "polite"}, {"text": "안녕", "style": "funny"},
                                  {"text": "가" * 4001, "style": "polite"}])
def test_bad_request_is_422(client, body):
    assert client.post("/polish", json=body).status_code == 422


def test_check_keeps_existing_masked_values():
    assert check("김◯◯2님께 [카드번호 1] 전달", "김◯◯2님께 [카드번호 1]을 전달합니다") is None
