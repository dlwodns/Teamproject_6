"""backend ↔ ai 값 형식 (PR #4 리뷰): 시간대가 붙은 시각 · 정수 ID를 받아도 500 없이 KST 기준으로 같은 결과."""
from datetime import datetime

import pytest

from app.schemas.agent import PlanContext
from app.schemas.assist import SummaryItem
from app.schemas.common import to_kst_naive

ME = "me@corp.example"
OWNER = {"email": ME, "name": "김나래", "position": "팀장", "team": "데이터1팀"}
NAIVE_NOW = "2026-11-02T10:00:00"


@pytest.mark.parametrize("value", ["2026-11-02T10:00:00", "2026-11-02T10:00:00+09:00", "2026-11-02T01:00:00Z"])
def test_now_is_kst_naive(value):
    assert PlanContext(now=value).now == datetime(2026, 11, 2, 10, 0)


def test_to_kst_naive_keeps_naive():
    assert to_kst_naive(datetime(2026, 11, 2, 10, 0)) == datetime(2026, 11, 2, 10, 0)


def test_int_ids_become_str():
    ctx = PlanContext(now=NAIVE_NOW, selected_mail_ids=[12, "M-1"], last_result_ids=[3])
    assert ctx.selected_mail_ids == ["12", "M-1"] and ctx.last_result_ids == ["3"]
    assert SummaryItem(task_id=7, text="x").task_id == "7"


@pytest.mark.parametrize("received_at", ["2026-11-02T10:00:00", "2026-11-02T10:00:00+09:00", "2026-11-02T01:00:00Z"])
def test_classify_with_tz_and_int_id(client, fake_llm, received_at):
    # priority.py: min(dues) - received_at — dues는 시간대 없는 값이라 received_at도 맞춰야 한다
    body = {"mail_id": 101, "from": "a@corp.example", "to": [ME], "subject": "요청", "received_at": received_at,
            "body": "[긴급] 자료를 내일까지 제출 부탁드립니다.", "owner": OWNER}
    fake_llm.replies.append({"mail_type": "요청", "tasks": [{"type": "자료제출요청", "action": "자료 제출", "due_raw": "내일까지",
                                                           "format": "없음", "to": "요청자"}]})
    r = client.post("/classify", json=body)
    assert r.status_code == 200
    j = r.json()
    assert j["mail_id"] == "101" and j["tasks"][0]["due_at"] == "2026-11-03T18:00:00"


@pytest.mark.parametrize("now", [NAIVE_NOW, "2026-11-02T10:00:00+09:00"])
def test_plan_with_tz_and_int_ids(client, fake_llm, now):
    # rules_v1.remind_at: datetime.combine(...) 후 at > now
    body = {"text": "이거 오후 3시에 다시 알려줘", "actions": [{"id": "T05", "name": "나중에_처리"}],
            "context": {"now": now, "selected_mail_ids": [12]}}
    fake_llm.replies.append({"action": "T05", "selected": True})  # 행동은 모델이 고른다(AI-D19)
    r = client.post("/agent/plan", json=body)
    assert r.status_code == 200
    j = r.json()
    assert j["action"] == "T05" and j["target"]["mail_ids"] == ["12"] and j["params"]["until"] == "2026-11-02T15:00:00"


def test_summarize_with_tz(client):
    # assist._rank: due_at < now, datetime.max
    body = {"mode": "today", "now": "2026-11-02T09:00:00+09:00", "use_model": False, "items": [
        {"task_id": 1, "text": "실적 자료 제출", "due_at": "2026-11-02T08:00:00Z", "priority": "P2"},  # KST 17:00
        {"task_id": 2, "text": "절차서 검토", "due_at": "2026-11-01T18:00:00", "priority": "P3"},
        {"task_id": 3, "text": "견적 확인", "priority": "P3"},
    ]}
    r = client.post("/summarize", json=body)
    assert r.status_code == 200
    assert r.json()["counts"] == {"pending": 3, "due_today": 2, "overdue": 1, "awaiting_reply": 0}
    assert r.json()["text"] == "기한이 지난 업무가 1건 있습니다. 오늘 마감인 업무가 1건 있습니다."  # Z → KST 17:00이라 오늘
