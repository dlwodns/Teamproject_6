"""PR #21 리뷰 반영: 기한 문맥 찾기 · 설정 값 확인. 규칙 기한 우선(같은 요청 판정)은 AI-D15에서 규칙이 요청을 찾지 않게 되어 뺐다."""
from datetime import datetime

import pytest

from app.core.config import Settings, check_settings, ensure_settings
from app.pipeline.classify import _context
from app.pipeline.dates import parse_deadline
from app.schemas.classify import ClassifyRequest, OwnerProfile, SenderFlags

ME = "me@corp.example"
OWNER = OwnerProfile(email=ME, name="김나래", position="팀장", team="데이터1팀", member_of=[])


@pytest.mark.parametrize("raw", ["10/22(목)", "10/22 (목)", "10/22 목"])
def test_context_ignores_spacing(raw):
    # 근거 확인(_squash)을 통과한 기한 글자는 띄어쓰기 · 괄호가 달라도 원문 자리를 찾아 마감 표지를 함께 본다
    req = ClassifyRequest(**{"from": "a@corp.example"}, mail_id="X-1", to=[ME], cc=[], subject="문의",
                          body="발표 자료는 10/22(목)까지 보내 주세요.", attachments=[], received_at="2026-10-19T09:00",
                          owner=OWNER, sender=SenderFlags())
    due = parse_deadline(_context(raw, req), datetime(2026, 10, 19, 9))
    assert due and due.due_at == datetime(2026, 10, 22, 18)


def test_bad_settings_stop_start(monkeypatch):
    # 설정이 틀리면 시작할 때 멈춘다. ROUTER_MODE · ROUTER_THRESHOLD는 AI-D15에서 없어졌다(라우터 없음)
    for name in ("LLM_BACKEND", "LLM_TIMEOUT_S", "OLLAMA_BASE_URL", "LLAMACPP_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_TIMEOUT_S", "-1")
    assert check_settings() == ["LLM_TIMEOUT_S: 0보다 커야 한다"]
    with pytest.raises(RuntimeError, match="LLM_TIMEOUT_S"):
        ensure_settings()
    monkeypatch.setenv("LLM_TIMEOUT_S", "120")
    monkeypatch.setenv("ROUTER_MODE", "gate")  # 남은 옛 값은 무시한다(AI-D15로 없어진 변수라 .env.example에 없음) boundary-ok
    assert check_settings() == []


def test_good_settings():
    assert not hasattr(Settings(), "router_mode") and Settings().llm_enabled
