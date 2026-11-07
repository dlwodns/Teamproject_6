"""행동 레지스트리 · 확인 판정 · 대상 해석 · 실행기 (BE-11). ai 없이 plan(ai 응답 모양)을 직접 넣는다."""
from datetime import datetime

import pytest

from app.agent import executor
from app.agent.policy import needs_confirm
from app.agent.tools.registry import REGISTRY, actions_for_ai
from app.models import Account, ActionLog, ActionPreview, Contact, Mail, Task, User

T0 = datetime(2026, 11, 3, 9, 0)
NAMES = ["오늘_요약", "미처리_조회", "일괄_완료", "되돌리기", "나중에_처리", "무응답_확인", "회신_초안", "근거_설명",
         "리마인드_설정", "제외_처리", "중요_발신자_지정", "초안_작성", "기한_보기", "템플릿_전송"]  # ai/tests · eval과 같은 이름
MCP_TOOLS = {"list_pending", "get_today_summary", "list_awaiting_reply", "preview_action", "execute_action",
             "undo_action", "draft_reply"}  # AI detail 5.3절


@pytest.fixture
def box(db):
    """김민준 팀장 메일 3통(업무 1개씩) + 박서연 책임 공지 메일 1통(업무 1개)."""
    db.add(User(id=1, name="나"))
    db.flush()
    db.add(Account(id=1, user_id=1, provider="dummy", email="me@example.com"))
    db.add_all([Contact(user_id=1, email="lead@example.com", name="김민준", position="팀장", is_superior=True),
                Contact(user_id=1, email="park@example.com", name="박서연", position="책임")])
    db.flush()
    rows = [("M-1", "lead@example.com", "계약서 수정본 검토", "검토", datetime(2026, 11, 3, 18)),
            ("M-2", "lead@example.com", "협력사 평가표 작성", "요청", datetime(2026, 11, 5, 18)),
            ("M-3", "lead@example.com", "견적 회신", "회신", datetime(2026, 11, 10, 18)),
            ("M-4", "park@example.com", "보안 교육 이수", "공지", None)]
    for i, (sid, sender, text, cat, due) in enumerate(rows, start=1):
        db.add(Mail(id=i, account_id=1, source_id=sid, direction="received", sender=sender, subject=text,
                    category=cat, sent_at=datetime(2026, 11, 2, 9 + i)))
        db.flush()
        db.add(Task(id=i, mail_id=i, text=text, due_at=due))
    db.commit()
    return db


def _plan(action, target=None, params=None, source="rule", reason=None):
    return {"action": action, "action_name": None, "target": target or {}, "params": params or {},
            "source": source, "reason": reason}


def _status(db, tid):
    db.expire_all()
    return db.get(Task, tid).status


# ---- 레지스트리 · 확인 판정 ----

def test_registry_matches_contract():
    assert [a.id for a in REGISTRY.values()] == [f"T{i:02d}" for i in range(1, 15)]
    assert [a.name for a in REGISTRY.values()] == NAMES
    assert {a.mcp_tool for a in REGISTRY.values() if a.mcp_tool} <= MCP_TOOLS
    assert actions_for_ai()[0] == {"id": "T01", "name": "오늘_요약", "description": REGISTRY["T01"].description}
    assert REGISTRY["T05"].params == ("until",) and REGISTRY["T05"].required == ("until",)


@pytest.mark.parametrize("aid, ids, ambiguous, expected", [
    ("T02", [1, 2, 3], False, False),  # 조회
    ("T07", [1], False, False),  # 표시
    ("T03", [1], False, False),  # 상태 변경 1건 → 바로
    ("T03", [1, 2], False, True),  # 2건 이상 → 확인
    ("T03", [1], True, True),  # 후보 여럿 → 1건이어도 확인
    ("T09", [], False, True),  # 설정 → 확인
    ("T14", [1], False, True),  # 발송 → 항상 확인
])
def test_needs_confirm_table(aid, ids, ambiguous, expected):
    assert needs_confirm(REGISTRY[aid], ids, ambiguous) is expected


# ---- 실행기 ----

def test_one_selected_mail_done_immediately(box, client):
    # "이거 완료"(선택 메일 1통) → 확인 없이 실행 · 기록(T03, agent_rule) · 실행 취소 가능
    r = executor.run(box, 1, _plan("T03", {"mail_ids": [2]}))
    box.commit()
    assert r.kind == "done" and r.title == "1건을 완료로 바꿨어요" and r.action_id
    assert _status(box, 2) == "done"
    log = box.get(ActionLog, r.action_id)
    assert log.action == "T03" and log.source == "agent_rule"
    assert client.post(f"/api/actions/{r.action_id}/undo").status_code == 200
    assert _status(box, 2) == "pending"


def test_sender_three_tasks_confirm_then_execute_subset(box, client):
    # V-16: "김 팀장님 건 다 처리했어" → 확인 카드 3건 → 체크 하나 풀고 2건만 실행
    r = executor.run(box, 1, _plan("T03", {"sender": "김 팀장"}, source="model"))
    box.commit()
    assert r.kind == "confirm" and r.title == "업무 3건을 완료로 바꿀까요?"
    assert [t.id for t in r.targets] == [1, 2, 3] and any("김민준 팀장" in n for n in r.notes)
    assert r.expires_at.utcoffset().total_seconds() == 9 * 3600  # D47
    assert all(_status(box, i) == "pending" for i in (1, 2, 3))  # 확인 전에는 안 바뀐다

    out = client.post("/api/actions/execute", json={"preview_id": r.preview_id, "task_ids": [1, 3]})
    assert out.status_code == 200
    assert [_status(box, i) for i in (1, 2, 3)] == ["done", "pending", "done"]
    log = box.get(ActionLog, out.json()["action_id"])
    assert log.action == "T03" and log.source == "agent_model" and log.confirmed  # 사용자가 확인해도 에이전트 기록


def test_execute_subset_must_be_inside_preview(box, client):
    r = executor.run(box, 1, _plan("T03", {"sender": "김 팀장"}))
    box.commit()
    assert client.post("/api/actions/execute", json={"preview_id": r.preview_id, "task_ids": [1, 4]}).status_code == 422
    assert client.post("/api/actions/execute", json={"preview_id": r.preview_id, "task_ids": []}).status_code == 422
    assert box.query(ActionPreview).one().used_at is None  # 거절되면 미리보기는 그대로 쓸 수 있다


def test_snooze_needs_until(box):
    r = executor.run(box, 1, _plan("T05", {"keyword": "견적"}, {"until": None}))
    assert r.kind == "ask" and r.title == "언제 다시 알려 드릴까요?"
    r = executor.run(box, 1, _plan("T05", {"keyword": "견적"}, {"until": "2026-11-07T09:00:00"}))
    box.commit()
    assert r.kind == "done" and r.title == "1건을 11/07 09:00까지 미뤘어요"
    box.expire_all()
    assert box.get(Task, 3).snoozed_until == datetime(2026, 11, 7, 9, 0)


@pytest.mark.parametrize("plan, kind", [
    (_plan(None, reason="unsupported"), "unsupported"),  # "배고프다"
    (_plan(None, reason="ambiguous"), "ask"),
    (_plan("T99"), "unsupported"),  # 레지스트리에 없는 행동
    (_plan("T03", {"sender": "김 팀장"}, {"due_within": 3}), "unsupported"),  # 계약에 없는 params 키(D47)
    (_plan("T01", params={"date": "2026-11-03"}), "unsupported"),  # 아직 준비 중(ai 요약 연결 전)
    (_plan("T03"), "ask"),  # 조건 없음 → 전부를 고르지 않는다
])
def test_rejected_without_change(box, plan, kind):
    r = executor.run(box, 1, plan)
    assert r.kind == kind
    assert box.query(ActionLog).count() == 0 and box.query(ActionPreview).count() == 0


def test_unknown_sender_is_empty(box):
    r = executor.run(box, 1, _plan("T03", {"sender": "최 상무"}))
    assert r.kind == "empty" and any("최 상무" in n for n in r.notes)


def test_category_and_query_by_due(box):
    # "공지 메일 다 처리했어"(1건) → 바로 실행 / "이번 주 기한인 거"(T02) → 기한 기준 조회
    r = executor.run(box, 1, _plan("T02", {"date_range": {"start": "2026-11-03", "end": "2026-11-07"}}))
    assert r.kind == "query" and [t.id for t in r.targets] == [1, 2]
    r = executor.run(box, 1, _plan("T03", {"category": "공지"}))
    assert r.kind == "done" and [t.id for t in r.targets] == [4]


def test_ambiguous_sender_confirms_even_one(box):
    box.add(Contact(user_id=1, email="kim2@example.com", name="김서준", position="팀장"))
    box.commit()
    r = executor.run(box, 1, _plan("T03", {"sender": "김 팀장", "category": "요청"}))
    assert r.kind == "confirm" and [t.id for t in r.targets] == [2]
    assert any("여러 명" in n for n in r.notes)


def test_undo_latest_and_nothing_left(box):
    assert executor.run(box, 1, _plan("T04")).kind == "empty"  # 아직 아무 행동도 없음
    done = executor.run(box, 1, _plan("T03", {"mail_ids": [1]}))
    box.commit()
    r = executor.run(box, 1, _plan("T04", params={"action_id": None}))  # "방금 거 취소해"
    box.commit()
    assert r.kind == "done" and _status(box, 1) == "pending"
    assert box.get(ActionLog, done.action_id).undone_at is not None
    assert box.get(ActionLog, r.action_id).source == "agent_rule"
