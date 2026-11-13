"""에이전트 명령 API (BE-11 2단계). 시드 DB(dummy_mails.json, 시각 B) + 가짜 ai로 시연 ②③을 확인한다.
CI에서 엑사원을 부르지 않으므로 ai /agent/plan 응답은 가짜로 넣는다(INF-9). 응답 모양은 PlanResult(#28) 그대로다."""
import pytest

from app.ai_client.client import AIError, get_ai_client
from app.core.db import engine
from app.dev.seed import load
from app.main import app
from app.models import ActionLog, ActionPreview, Mail, Task
from app.schemas.ai import PlanResult

PLANS = {  # 명령 문장 → ai가 돌려줄 해석(규칙 경로 모양)
    "김 팀장 건 다 처리했어": {"action": "T03", "action_name": "일괄_완료", "target": {"sender": "김 팀장"}},
    "방금 거 취소해": {"action": "T04", "action_name": "되돌리기", "params": {}},
    "배고프다": {"action": None, "reason": "unsupported"},
}


class FakeAI:
    def __init__(self, error: AIError | None = None):
        self.error, self.calls = error, []

    def plan(self, text, actions, *, now, selected_mail_ids=None, last_result_ids=None):
        self.calls.append({"text": text, "actions": actions, "now": now, "selected": selected_mail_ids,
                           "last": last_result_ids})
        if self.error:
            raise self.error
        return PlanResult.model_validate({"source": "rule", "rules_version": "test", **PLANS[text]})


@pytest.fixture
def seeded(db):
    load(engine, "2026-10-20T09:00")  # 시연 시각 B, 메일 100통 · 업무 62개
    db.expire_all()
    return db


@pytest.fixture
def ai():
    fake = FakeAI()
    app.dependency_overrides[get_ai_client] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_ai_client, None)


def _kim_tasks(db) -> list[Task]:
    db.expire_all()
    return [t for t in db.query(Task).join(Mail).filter(Mail.source_id.in_(["M-0026", "M-0040", "M-0089"]))]


def test_kim_done_then_undo(seeded, ai, client):
    # 완료 기준(동하님 분담 11-12): "김 팀장 건 다 처리했어" → 3건 완료, "방금 거 취소해" → 3건 복원
    r = client.post("/api/agent/command", json={"text": "김 팀장 건 다 처리했어"})
    assert r.status_code == 200, r.text
    card = r.json()
    assert card["kind"] == "confirm" and card["title"] == "업무 3건을 완료로 바꿀까요?"
    assert sorted(t["mail_id"] for t in card["targets"]) == sorted(t.mail_id for t in _kim_tasks(seeded))
    assert all(t.status == "pending" for t in _kim_tasks(seeded))  # 확인 전에는 안 바뀐다

    done = client.post("/api/actions/execute", json={"preview_id": card["preview_id"]})
    assert done.status_code == 200 and done.json()["action_id"]
    assert [t.status for t in _kim_tasks(seeded)] == ["done"] * 3
    log = seeded.get(ActionLog, done.json()["action_id"])
    assert log.action == "T03" and log.source == "agent_rule" and log.confirmed

    back = client.post("/api/agent/command", json={"text": "방금 거 취소해"})
    assert back.status_code == 200 and back.json()["kind"] == "done"
    assert back.json()["title"] == "3건을 되돌렸어요"
    assert [t.status for t in _kim_tasks(seeded)] == ["pending"] * 3


def test_plan_request_carries_registry_and_mail_ids(seeded, ai, client):
    client.post("/api/agent/command", json={"text": "배고프다", "selected_mail_ids": [3], "last_result_ids": [5, 7]})
    call = ai.calls[0]
    assert [a["id"] for a in call["actions"]] == [f"T{i:02d}" for i in range(1, 15)]  # 레지스트리에서 만든 목록
    assert call["selected"] == [3] and call["last"] == [5, 7]
    assert call["now"].tzinfo is None  # clock.now()(시간대 없는 KST, D47)


def test_unsupported_is_200_without_change(seeded, ai, client):
    before = seeded.query(ActionLog).count()  # 시드가 메일 기억하기 기록을 남길 수 있어(#44 BE-D17) 0이 아니라 전후를 비교한다
    r = client.post("/api/agent/command", json={"text": "배고프다"})
    assert r.status_code == 200 and r.json()["kind"] == "unsupported"
    assert seeded.query(ActionLog).count() == before


@pytest.mark.parametrize("kind", ["unavailable", "timeout", "bad_response"])
def test_ai_down_is_503_not_500(seeded, ai, client, kind):
    # ai가 꺼짐 · 늦음 · 계약과 다른 응답 → 500 없이 503, 상태 · 기록 · 미리보기 그대로
    ai.error = AIError(kind, "test")
    logs, previews = seeded.query(ActionLog).count(), seeded.query(ActionPreview).count()
    r = client.post("/api/agent/command", json={"text": "김 팀장 건 다 처리했어"})
    assert r.status_code == 503 and "처리할 수 없어요" in r.json()["detail"]
    seeded.expire_all()
    assert seeded.query(ActionLog).count() == logs and seeded.query(ActionPreview).count() == previews


def test_rejects_empty_text_and_unknown_user(seeded, ai, client):
    assert client.post("/api/agent/command", json={"text": ""}).status_code == 422
    r = client.post("/api/agent/command", json={"text": "배고프다"}, headers={"X-User-Id": "999"})
    assert r.status_code == 401 and not ai.calls  # 없는 사용자는 core/user.py 기준 401(BE-D16)
