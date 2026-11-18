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
    # 11-18 실측: 엑사원이 '내일'을 받은 날 조건(date_range)으로도 넣는다 → 고른 리마인더가 있으면 그 조건은 보지 않는다
    "이거 내일 아침으로 미뤄 줘": {"action": "T05", "action_name": "연기", "params": {"until": "2099-01-05T09:00:00"},
                         "target": {"mail_ids": [1], "date_range": {"start": "2026-10-21", "end": "2026-10-21"}}},
    # 개인정보 가리기(BE-6): backend가 '김민석'을 '김◯◯'로 가려 보내고, ai(규칙)는 가린 이름을 그대로 대상으로 돌려준다
    "김◯◯ 팀장 건 다 처리했어": {"action": "T03", "action_name": "일괄_완료", "target": {"sender": "김◯◯ 팀장"}},
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
    assert card["kind"] == "confirm" and card["title"] == "업무 3건을 완료로 변경하시겠습니까?"
    assert sorted(t["mail_id"] for t in card["targets"]) == sorted(t.mail_id for t in _kim_tasks(seeded))
    assert all(t.status == "pending" for t in _kim_tasks(seeded))  # 확인 전에는 안 바뀐다

    done = client.post("/api/actions/execute", json={"preview_id": card["preview_id"]})
    assert done.status_code == 200 and done.json()["action_id"]
    assert [t.status for t in _kim_tasks(seeded)] == ["done"] * 3
    log = seeded.get(ActionLog, done.json()["action_id"])
    assert log.action == "T03" and log.source == "agent_rule" and log.confirmed

    back = client.post("/api/agent/command", json={"text": "방금 거 취소해"})
    assert back.status_code == 200 and back.json()["kind"] == "done"
    assert back.json()["title"] == "3건의 처리를 취소했습니다"
    assert [t.status for t in _kim_tasks(seeded)] == ["pending"] * 3


def test_selected_reminder_task_ids_are_the_target(seeded, ai, client):
    # 캐치봇 '고른 리마인더' 칩: FE가 task_ids · reminder_key를 보낸다(reminders.md 131행). 고른 업무 1건만 바로 미룬다
    kim = _kim_tasks(seeded)[0]
    other = seeded.query(Task).filter(Task.mail_id == kim.mail_id, Task.id != kim.id).all()
    r = client.post("/api/agent/command", json={"text": "이거 내일 아침으로 미뤄 줘", "selected_mail_ids": [kim.mail_id],
                                                "task_ids": [kim.id], "reminder_key": f"t{kim.id}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "done" and [t["id"] for t in body["targets"]] == [kim.id] and body["action_id"]
    seeded.expire_all()
    assert seeded.get(Task, kim.id).status == "snoozed"
    assert all(t.status == "pending" for t in other)  # 같은 메일의 다른 업무는 그대로


def test_selected_reminder_ignores_done_or_foreign_task_ids(seeded, ai, client):
    r = client.post("/api/agent/command", json={"text": "이거 내일 아침으로 미뤄 줘", "task_ids": [999999]})
    assert r.status_code == 200 and r.json()["kind"] == "empty"


def test_full_name_is_masked_to_ai_and_restored_to_find_contact(seeded, ai, client):
    r = client.post("/api/agent/command", json={"text": "김민석 팀장 건 다 처리했어"})
    assert r.status_code == 200, r.text
    assert ai.calls[-1]["text"] == "김◯◯ 팀장 건 다 처리했어"  # 이름은 ai로 나가지 않는다
    card = r.json()
    assert card["kind"] == "confirm" and card["title"] == "업무 3건을 완료로 변경하시겠습니까?"  # 되돌린 이름으로 김민석 연락처를 찾음
    assert sorted(t["mail_id"] for t in card["targets"]) == sorted(t.mail_id for t in _kim_tasks(seeded))
    assert "김◯◯" not in r.text


def test_pii_mask_off_sends_command_as_is(seeded, ai, client, monkeypatch):
    monkeypatch.setenv("PII_MASK", "0")
    client.post("/api/agent/command", json={"text": "김 팀장 건 다 처리했어"})
    assert ai.calls[-1]["text"] == "김 팀장 건 다 처리했어"


def test_plan_request_carries_registry_and_mail_ids(seeded, ai, client):
    client.post("/api/agent/command", json={"text": "배고프다", "selected_mail_ids": [3], "last_result_ids": [5, 7]})
    call = ai.calls[0]
    assert [a["id"] for a in call["actions"]] == [f"T{i:02d}" for i in range(1, 16)] + ["T17"]  # 레지스트리에서 만든 목록(T15 일정 넣기, #74)
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


def test_whitespace_only_text_is_422_before_ai(seeded, ai, client):
    # #50 리뷰 1: 공백만 있는 명령은 ai를 부르지 않고 422(엑사원 해석이 수십 초라 바로 막는다)
    for text in ("   ", "\n\t "):
        assert client.post("/api/agent/command", json={"text": text}).status_code == 422
    assert not ai.calls
    client.post("/api/agent/command", json={"text": "  배고프다  "})
    assert ai.calls[0]["text"] == "배고프다"  # 앞뒤 공백은 지우고 보낸다


def test_undo_command_reverts_checkbox_done(seeded, ai, client):
    # #50 리뷰 2(의도한 동작): "방금 거 취소해"는 사용자의 가장 최근 행동을 되돌린다 — 체크 상자(버튼)로 한 완료도 포함
    task = _kim_tasks(seeded)[0]
    assert client.patch(f"/api/tasks/{task.id}", json={"status": "done"}).status_code == 200
    r = client.post("/api/agent/command", json={"text": "방금 거 취소해"})
    assert r.status_code == 200 and r.json()["kind"] == "done" and r.json()["title"] == "1건의 처리를 취소했습니다"
    seeded.expire_all()
    assert seeded.get(Task, task.id).status == "pending"
