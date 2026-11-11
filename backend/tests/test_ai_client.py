"""ai 서비스 호출 (BE-9). 실제 ai · 엑사원 없이 httpx 가짜 응답으로 확인한다(INF-9: CI에서 엑사원을 부르지 않는다)."""
import json
from datetime import date, datetime

import httpx
import pytest

from app.ai_client.client import AIClient, AIError
from app.core.request_id import request_id_var

CLASSIFY_OUT = {
    "mail_id": "101", "category": "회신", "action_types": ["회신요청"],
    "tasks": [{"text": "견적 회신", "due_raw": "내일까지", "due_at": "2026-11-03T18:00:00"},
              {"text": "자료 공유", "due_raw": "ASAP", "due_at": None}],
    "checks": [], "lane": "할 일", "mentioned_me": True, "urgent": True, "is_follow_up": False, "priority": "P1",
    "source": "exaone", "confidence": 0.9, "rules_version": "mail_rules_v1.8", "new_field_from_ai": 1,
}
PLAN_OUT = {
    "action": "T05", "action_name": "나중에_처리",
    "target": {"sender": "김 팀장", "keyword": "견적", "mail_ids": ["3", "5"],
               "date_range": {"start": "2026-11-03", "end": "2026-11-07"}},
    "params": {"until": "2026-11-07T09:00:00"}, "source": "rule", "rules_version": "agent_rules_v1.4",
}


def _client(handler) -> AIClient:
    return AIClient("http://ai.test", transport=httpx.MockTransport(handler))


def _reply(body, status=200):
    return lambda req: httpx.Response(status, json=body)


def test_classify_converts_ids_and_times():
    seen = {}

    def handler(req: httpx.Request):
        seen["path"], seen["body"] = req.url.path, json.loads(req.content)
        return httpx.Response(200, json=CLASSIFY_OUT)

    out = _client(handler).classify({"mail_id": 101, "from": "lead@example.com", "subject": "견적",
                                     "received_at": datetime(2026, 11, 2, 10, 0), "owner": {"email": "me@example.com"}})
    assert seen["path"] == "/classify"
    assert seen["body"]["mail_id"] == 101 and seen["body"]["received_at"] == "2026-11-02T10:00:00"
    assert out.mail_id == 101  # D47: ai 응답 문자열 ID → 정수
    assert out.tasks[0].due_at == datetime(2026, 11, 3, 18, 0)  # 시간대 없는 KST 그대로
    assert out.tasks[1].due_at is None and out.tasks[1].due_raw == "ASAP"  # AI-D11: 문구만 있는 기한
    assert out.lane == "할 일" and out.urgent is True


def test_aware_time_from_ai_becomes_kst_naive():
    body = {**CLASSIFY_OUT, "tasks": [{"text": "x", "due_at": "2026-11-03T09:00:00Z"}]}
    out = _client(_reply(body)).classify({})
    assert out.tasks[0].due_at == datetime(2026, 11, 3, 18, 0)


def test_plan_converts_target_and_until():
    seen = {}

    def handler(req: httpx.Request):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=PLAN_OUT)

    out = _client(handler).plan("견적 건은 금요일에 다시 알려줘", [{"id": "T05", "name": "나중에_처리", "description": "미루기"}],
                                now=datetime(2026, 11, 3, 9, 0), selected_mail_ids=[3])
    assert seen["body"]["context"] == {"now": "2026-11-03T09:00:00", "selected_mail_ids": [3], "last_result_ids": []}
    assert out.action == "T05" and out.target.mail_ids == [3, 5]
    assert out.target.date_range.start == date(2026, 11, 3)
    assert out.params["until"] == datetime(2026, 11, 7, 9, 0)


def test_plan_unsupported_and_null_param():
    body = {"action": None, "reason": "unsupported", "params": {"until": None}, "source": "rule", "rules_version": "v"}
    out = _client(_reply(body)).plan("배고프다", [], now=datetime(2026, 11, 3))
    assert out.action is None and out.reason == "unsupported"
    assert "until" in out.params and out.params["until"] is None  # 못 읽은 값은 키를 두고 null(#6 리뷰)


def test_request_id_forwarded():
    seen = {}

    def handler(req: httpx.Request):
        seen["rid"] = req.headers.get("X-Request-ID")
        return httpx.Response(200, json={"text": "요약", "source": "code"})

    token = request_id_var.set("abc-123")
    try:
        _client(handler).summarize({"mode": "today", "now": datetime(2026, 11, 3)})
    finally:
        request_id_var.reset(token)
    assert seen["rid"] == "abc-123"


@pytest.mark.parametrize("handler, kind", [
    (lambda req: (_ for _ in ()).throw(httpx.ReadTimeout("느림")), "timeout"),
    (lambda req: (_ for _ in ()).throw(httpx.ConnectError("꺼짐")), "unavailable"),
    (_reply({"detail": "x"}, 500), "bad_response"),
    (lambda req: httpx.Response(200, content=b"not json"), "bad_response"),
    (_reply({"text": "필드가 모자람"}), "bad_response"),
])
def test_errors_are_classified(handler, kind):
    with pytest.raises(AIError) as e:
        _client(handler).draft({"kind": "reply"})
    assert e.value.kind == kind


def test_health_never_raises():
    down = _client(lambda req: (_ for _ in ()).throw(httpx.ConnectError("꺼짐"))).health()
    assert down == {"status": "down"}
    up = _client(_reply({"status": "ok", "model": "exaone", "llm": {"reachable": True}})).health()
    assert up["status"] == "ok"
