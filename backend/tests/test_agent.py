"""행동 레지스트리 · 확인 판정 · 대상 해석 · 실행기 (BE-11). ai 없이 plan(ai 응답 모양)을 직접 넣는다."""
from datetime import date, datetime, timedelta

import pytest

from app.agent import executor
from app.core.clock import now
from app.reminders import briefings
from app.agent.policy import needs_confirm
from app.agent.tools.registry import REGISTRY, actions_for_ai
from app.models import Account, ActionLog, ActionPreview, Contact, Mail, Task, User

T0 = datetime(2026, 11, 3, 9, 0)
NAMES = ["오늘_요약", "미처리_조회", "일괄_완료", "되돌리기", "나중에_처리", "무응답_확인", "회신_초안", "근거_설명",
         "리마인드_설정", "제외_처리", "중요_발신자_지정", "초안_작성", "기한_보기", "템플릿_전송", "일정_등록", "기한_변경", "사람_조회", "메일_내용_질문", "메일_찾기", "메일_요약"]  # ai/tests · eval과 같은 이름(T16은 버튼 전용, BE-12)
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
    assert [a.id for a in REGISTRY.values()] == [f"T{i:02d}" for i in range(1, 21)]
    assert "T16" in {a["id"] for a in actions_for_ai()}  # 11-18 말로도 기한을 바꾼다(전에는 버튼 전용, BE-12)
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
    assert r.kind == "done" and r.title == "1건을 완료로 변경했습니다" and r.action_id
    assert _status(box, 2) == "done"
    log = box.get(ActionLog, r.action_id)
    assert log.action == "T03" and log.source == "agent_rule"
    assert client.post(f"/api/actions/{r.action_id}/undo").status_code == 200
    assert _status(box, 2) == "pending"


def test_sender_three_tasks_confirm_then_execute_subset(box, client):
    # V-16: "김 팀장님 건 다 처리했어" → 확인 카드 3건 → 체크 하나 풀고 2건만 실행
    r = executor.run(box, 1, _plan("T03", {"sender": "김 팀장"}, source="model"))
    box.commit()
    assert r.kind == "confirm" and r.title == "업무 3건을 완료로 변경하시겠습니까?"
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
    assert r.kind == "ask" and r.title == "다시 알림 받을 시각을 알려 주십시오"
    r = executor.run(box, 1, _plan("T05", {"keyword": "견적"}, {"until": "2099-11-07T09:00:00"}))
    box.commit()
    assert r.kind == "done" and r.title == "1건을 11/07 09:00까지 연기했습니다"
    box.expire_all()
    assert box.get(Task, 3).snoozed_until == datetime(2099, 11, 7, 9, 0)


@pytest.mark.parametrize("plan, kind", [
    (_plan(None, reason="unsupported"), "unsupported"),  # "배고프다"
    (_plan(None, reason="ambiguous"), "ask"),
    (_plan("T99"), "unsupported"),  # 레지스트리에 없는 행동
    (_plan("T03", {"sender": "김 팀장"}, {"due_within": 3}), "unsupported"),  # 계약에 없는 params 키(D47)
    (_plan("T09"), "unsupported"),  # 아직 준비 중(리마인드 설정 — 설정 화면에서 바꾼다)
    (_plan("T03"), "ask"),  # 조건 없음 → 전부를 고르지 않는다
])
def test_rejected_without_change(box, plan, kind):
    r = executor.run(box, 1, plan)
    assert r.kind == kind
    assert box.query(ActionLog).count() == 0 and box.query(ActionPreview).count() == 0


def test_today_summary_and_review(box):
    """T01: 채팅에서 하루 요약 · 회고를 바로 본다(11-14). 아무것도 바꾸지 않는다."""
    m = executor.run(box, 1, _plan("T01", params={"date": None}))
    assert m.kind == "summary" and m.title.startswith("일일 업무 요약") and m.summary is not None
    assert len({i.task_id for i in m.summary.items}) == len(m.summary.items)  # 같은 업무는 한 번
    e = executor.run(box, 1, _plan("T01", params={"date": None, "kind": "evening"}))
    assert e.kind == "summary" and e.title.startswith("일일 업무 회고") and e.summary.items  # 남은 일이 있다
    assert box.query(ActionLog).count() == 0


def test_review_keeps_done_section_and_tomorrow_wording(box):
    """#190 리뷰 2 · 3: 회고의 완료 업무는 section으로 '완료'임을 싣고, 내일 요약 묶음 이름에 '금일'이 없다."""
    t = box.get(Task, 1)
    t.status, t.done_at, t.due_at = "done", now(), now() - timedelta(hours=1)  # 기한 지난 업무를 오늘 끝냄
    box.commit()
    e = executor.run(box, 1, _plan("T01", params={"date": None, "kind": "evening"}))
    assert {i.task_id: i.section for i in e.summary.items}[1] == "done_today"
    assert "금일 완료 업무" in e.summary.text
    tomorrow = (now() + timedelta(days=1)).date().isoformat()
    m = executor.run(box, 1, _plan("T01", params={"date": tomorrow}))
    labels = [s["label"] for s in briefings.build(box, 1, "morning", date.fromisoformat(tomorrow))["sections"]]
    assert labels[0] == "익일 마감 업무" and "금일" not in m.summary.text


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


# ---- 리뷰에서 고친 것 ----

def test_undo_other_users_action_refused(box):
    # 다른 사용자의 행동 번호로 되돌리지 않는다
    box.add(User(id=2, name="남"))
    box.flush()
    box.add(Account(id=2, user_id=2, provider="dummy", email="other@example.com"))
    box.flush()
    box.add(Mail(id=9, account_id=2, source_id="X-1", direction="received", sender="a@example.com", subject="x",
                 sent_at=T0))
    box.flush()
    box.add(Task(id=9, mail_id=9, text="남의 업무"))
    box.commit()
    theirs = executor.run(box, 2, _plan("T03", {"mail_ids": [9]}))
    box.commit()
    r = executor.run(box, 1, _plan("T04", params={"action_id": theirs.action_id}))
    assert r.kind == "empty" and _status(box, 9) == "done"


def test_undo_bad_action_id_asks(box):
    assert executor.run(box, 1, _plan("T04", params={"action_id": "직전"})).kind == "ask"


def test_query_without_filter_lists_all(box):
    # 조회는 조건이 없어도 전부 보여 준다("미처리 다 보여줘"). 상태 변경은 여전히 되묻는다
    r = executor.run(box, 1, _plan("T02"))
    assert r.kind == "query" and len(r.targets) == 4 and r.notes == ["미처리 업무 전체"]
    assert executor.run(box, 1, _plan("T03")).kind == "ask"


def test_keyword_wildcards_are_literal(box):
    # '%'는 SQL 와일드카드가 아니라 글자로 찾는다
    assert executor.run(box, 1, _plan("T02", {"keyword": "%"})).kind == "empty"


def test_sender_email_case_insensitive(box):
    r = executor.run(box, 1, _plan("T02", {"sender": "LEAD@example.com"}))
    assert r.kind == "query" and [t.id for t in r.targets] == [1, 2, 3]


# ---- #31 리뷰 (규남 · 재운 · 동하) ----

@pytest.fixture
def multi(db):
    """동하님 재현 구성: 메일1에 업무 1 · 2, 메일2에 업무 3, 메일3에 업무 4. 업무 id와 메일 id가 어긋난다."""
    db.add(User(id=1, name="나"))
    db.flush()
    db.add(Account(id=1, user_id=1, provider="dummy", email="me@example.com"))
    db.flush()
    for mid in (1, 2, 3):
        db.add(Mail(id=mid, account_id=1, source_id=f"M-{mid}", direction="received", sender="a@example.com",
                    subject=f"메일 {mid}", sent_at=datetime(2026, 11, 2, 9 + mid)))
    db.flush()
    db.add_all([Task(id=1, mail_id=1, text="a 할 일"), Task(id=2, mail_id=1, text="b 할 일"),
                Task(id=3, mail_id=2, text="c 할 일"), Task(id=4, mail_id=3, text="d 할 일")])
    db.commit()
    return db


def test_result_targets_carry_mail_id(multi):
    # 리뷰 1: 직전 결과(last_result_ids)는 메일 id다. 결과 대상에 mail_id를 실어 프론트가 그 값을 넘긴다
    found = executor.run(multi, 1, _plan("T02", {"keyword": "c"}))
    assert [(t.id, t.mail_id) for t in found.targets] == [(3, 2)]
    r = executor.run(multi, 1, _plan("T03", {"mail_ids": [t.mail_id for t in found.targets]}))
    multi.commit()
    assert r.kind == "done" and [t.id for t in r.targets] == [3]
    assert _status(multi, 3) == "done" and _status(multi, 4) == "pending"  # 업무 4(메일 3)는 그대로


def test_mail_with_two_tasks_confirms(multi):
    # 메일 1통에 업무 2개면 메일 id로 고르면 2건 → 확인 카드(체크를 풀어 하나만 할 수 있다)
    r = executor.run(multi, 1, _plan("T03", {"mail_ids": [1]}))
    assert r.kind == "confirm" and [(t.id, t.mail_id) for t in r.targets] == [(1, 1), (2, 1)]


def test_second_undo_asks_instead_of_undoing_older(box):
    # 리뷰 2: 완료 A → 완료 B → "취소해"(B) → "취소해" 다시 → A를 조용히 되돌리지 않고 되묻는다
    executor.run(box, 1, _plan("T03", {"mail_ids": [1]}))
    executor.run(box, 1, _plan("T03", {"mail_ids": [2]}))
    box.commit()
    first = executor.run(box, 1, _plan("T04"))
    box.commit()
    assert first.kind == "done" and _status(box, 2) == "pending"
    second = executor.run(box, 1, _plan("T04"))
    assert second.kind == "ask" and "다시 할까요" in second.title
    assert _status(box, 1) == "done"  # A는 그대로


def test_snoozed_tasks_are_targets(box):
    # 리뷰 3: '나중에' 업무도 끝나지 않은 일이라 T02 · T03 · T05 대상이다. 조회에는 미룬 시각을 같이 싣는다
    executor.run(box, 1, _plan("T05", {"keyword": "견적"}, {"until": "2099-11-14T09:00:00"}))
    box.commit()
    listed = executor.run(box, 1, _plan("T02"))
    snoozed = [t for t in listed.targets if t.id == 3][0]
    assert snoozed.status == "snoozed" and snoozed.snoozed_until.isoformat().startswith("2099-11-14T09:00:00")
    assert "연기 1건" in listed.title
    done = executor.run(box, 1, _plan("T03", {"keyword": "견적"}))
    box.commit()
    assert done.kind == "done" and _status(box, 3) == "done"


def test_snooze_to_past_asks(box):
    # 리뷰 4: 지난 시각으로는 미루지 않는다
    r = executor.run(box, 1, _plan("T05", {"keyword": "견적"}, {"until": "2020-01-01T00:00:00"}))
    assert r.kind == "ask" and box.query(ActionLog).count() == 0


@pytest.mark.parametrize("phrase, kind, ids", [
    ("민", "empty", []),  # 한 글자는 찾지 않는다(후보 1명이면 확인 없이 실행되므로)
    ("e", "empty", []),
    ("팀장님", "query", [1, 2, 3]),  # 직급만 말해도 그 직급이 한 명이면 찾는다
])
def test_contact_phrase_rules(box, phrase, kind, ids):
    r = executor.run(box, 1, _plan("T02", {"sender": phrase}))
    assert r.kind == kind and [t.id for t in r.targets] == ids


@pytest.mark.parametrize("plan", [
    _plan("T03", {"mail_ids": ["abc"]}),  # 메일 id가 숫자가 아님
    _plan("T02", {"date_range": {"start": "2026-11-03", "end": None}}),  # 기간 끝이 없음
    _plan("T05", {"keyword": "견적"}, {"until": "금요일"}),  # 시각을 못 읽음
])
def test_malformed_plan_asks_not_500(box, plan):
    # #28 리뷰(규남): ai 값이 형식에 안 맞아도 500이 아니라 되묻는다. 상태 · 기록은 그대로
    r = executor.run(box, 1, plan)
    assert r.kind == "ask"
    assert box.query(ActionLog).count() == 0 and box.query(ActionPreview).count() == 0


def test_until_with_timezone_saved_as_kst_naive(box):
    # #28 리뷰(규남): 시간대가 붙은 until도 D47대로 시간대 없는 KST로 저장한다(비교 · 저장 오류 없이)
    r = executor.run(box, 1, _plan("T05", {"keyword": "견적"}, {"until": "2099-11-14T00:00:00Z"}))
    box.commit()
    assert r.kind == "done" and r.title == "1건을 11/14 09:00까지 연기했습니다"
    box.expire_all()
    assert box.get(Task, 3).snoozed_until == datetime(2099, 11, 14, 9, 0)


# ---- T17 사람 조회 (11-17 결정) ----

def test_person_by_sender_with_facts_and_done_tasks(box):
    from app.models import ContactFact
    lead = box.query(Contact).filter_by(email="lead@example.com").one()
    box.add(ContactFact(user_id=1, contact_id=lead.id, kind="org", value="한빛은행 IT기획부",
                        evidence="저는 한빛은행 IT기획부 김민준입니다.", mail_id=1))
    box.get(Task, 1).status = "done"  # 끝난 업무도 보인다
    box.commit()
    r = executor.run(box, 1, _plan("T17", {"sender": "김 팀장"}))
    assert r.kind == "person" and r.person.name == "김민준" and r.person.is_superior
    assert [(f.kind, f.value) for f in r.person.facts] == [("org", "한빛은행 IT기획부")] and not r.person.learn_off
    assert r.person.mail_total == 3 and [m.mail_id for m in r.person.mails] == [3, 2, 1]  # 최근 순
    assert {t.id for t in r.targets} == {1, 2, 3} and _status(box, 1) == "done"  # 조회는 아무것도 바꾸지 않는다


def test_person_learn_off_hides_facts(box):
    from app.models import ContactFact
    from app.services import learn
    lead = box.query(Contact).filter_by(email="lead@example.com").one()
    box.add(ContactFact(user_id=1, contact_id=lead.id, kind="works_on", value="계약", evidence="계약 담당입니다.", mail_id=1))
    learn.set_enabled(box, 1, False)
    box.commit()
    r = executor.run(box, 1, _plan("T17", {"sender": "김민준"}))
    assert r.kind == "person" and r.person.facts == [] and r.person.learn_off and r.notes


def test_person_by_selected_mail(box):
    r = executor.run(box, 1, _plan("T17", {"mail_ids": ["4"]}))
    assert r.kind == "person" and r.person.email == "park@example.com" and [t.id for t in r.targets] == [4]


@pytest.mark.parametrize("target, kind", [
    ({"sender": "없는 사람"}, "empty"),
    ({"mail_ids": ["1", "4"]}, "ask"),  # 보낸 사람이 둘 → 되묻기
    ({}, "ask"),
])
def test_person_needs_one_person(box, target, kind):
    assert executor.run(box, 1, _plan("T17", target)).kind == kind


@pytest.mark.parametrize("aid", ["T07", "T12"])
def test_drafts_point_to_mail_reply(box, aid):
    """11-17: 초안은 캐치봇에서 만들지 않고 메일 답장 칸 [다듬기]로 안내한다."""
    r = executor.run(box, 1, _plan(aid))
    assert r.kind == "unsupported" and "다듬기" in r.title


# ---- T18 메일 내용 질문 (11-18) ----

def test_ask_mail_answers_with_body_sentence(box, monkeypatch):
    from app.agent import ask
    bodies = {"M-1": "안녕하세요, 김민준 팀장입니다.\n계약서 검토 회의 장소가 본사 3층 회의실로 변경되었습니다.\n시간은 10시입니다.\n"
                     "****************\n김민준 팀장"}
    monkeypatch.setattr(ask, "fetch_body", lambda db, m: bodies.get(m.source_id, ""))
    r = executor.run(box, 1, _plan("T18", {"keyword": "계약서 검토"}), text="계약서 검토 회의 어디서 해")
    assert r.kind == "query" and r.title == "계약서 검토 회의 장소가 본사 3층 회의실로 변경되었습니다."
    assert [t.id for t in r.targets] == [1] and "계약서 수정본 검토" in r.notes[0]
    r = executor.run(box, 1, _plan("T18", {"keyword": "계약서"}), text="계약서 검토 회의 몇 시야")
    assert r.title == "시간은 10시입니다."


def test_ask_mail_without_matching_sentence_asks_with_closest(box, monkeypatch):
    """11-19: 본문을 읽었는데 질문 낱말이 든 문장이 없으면 '본문을 읽지 못해'가 아니라 가장 비슷한 문장을 되묻는다."""
    from app.agent import ask
    body = "일정은 다음 주로 미뤄졌습니다.\n첨부 문서는 공유 폴더에 올렸습니다."
    monkeypatch.setattr(ask, "fetch_body", lambda db, m: body if m.source_id == "M-1" else "")
    r = executor.run(box, 1, _plan("T18", {"keyword": "계약서"}), text="계약서 검토 첨부파일 어디 있어")
    assert r.kind == "query" and r.title == "이 문장을 말씀하시는 걸까요? “첨부 문서는 공유 폴더에 올렸습니다.”"
    assert not any("본문을 읽지 못해" in n for n in r.notes) and any("가장 비슷한" in n for n in r.notes)


def test_closest_picks_most_overlapping_line():
    from app.agent.ask import closest
    assert closest("킥오프 장소 알려줘", ["회의 자료는 내일 드립니다.", "킥오프 미팅은 본사 3층에서 합니다."]) == "킥오프 미팅은 본사 3층에서 합니다."
    assert closest("아무거나", []) is None


@pytest.mark.parametrize("text, kind", [("어디야", "ask"), ("우주선 발사 장소 어디야", "empty")])
def test_ask_mail_needs_words_and_a_mail(box, text, kind):
    assert executor.run(box, 1, _plan("T18"), text=text).kind == kind


def test_keyword_words_need_not_be_adjacent(box):
    # 11-18: '계약서 검토'는 '계약서 수정본 검토'에도 맞는다(낱말마다 업무 문장 · 제목 어딘가에 있으면 된다)
    r = executor.run(box, 1, _plan("T02", {"keyword": "계약서 검토"}))
    assert r.kind == "query" and [t.id for t in r.targets] == [1]



# ---- 11-18 사용자 목적별 확장: T02 끝낸 · 미룬 업무 · T08 근거 · T10 제외 · T13 일정 · T16 기한 변경 · T19 메일 찾기 · T20 요약 ----

def test_done_and_snoozed_task_lookup(box):
    box.get(Task, 1).status, box.get(Task, 1).done_at = "done", datetime(2026, 11, 3, 12)
    t2 = box.get(Task, 2)
    t2.status, t2.snoozed_until = "snoozed", datetime(2099, 1, 1, 9)
    box.commit()
    r = executor.run(box, 1, _plan("T02", {"status": "done"}))
    assert r.kind == "query" and [t.id for t in r.targets] == [1] and r.title.startswith("끝낸 업무 1건")
    r = executor.run(box, 1, _plan("T02", {"status": "done", "date_range": {"start": "2026-11-03", "end": "2026-11-03"}}))
    assert [t.id for t in r.targets] == [1]  # '이번 주에 끝낸 거'는 끝낸 날로 거른다
    assert [t.id for t in executor.run(box, 1, _plan("T02", {"status": "snoozed"})).targets] == [2]


def test_evidence_uses_stored_sentence_then_body(box, monkeypatch):
    from app.agent import ask
    box.get(Task, 1).evidence_text = "계약서 수정본 검토 부탁드립니다."
    box.commit()
    r = executor.run(box, 1, _plan("T08", {"mail_ids": ["1"]}))
    assert r.kind == "query" and r.lines == ["계약서 수정본 검토 ← \u201c계약서 수정본 검토 부탁드립니다.\u201d"]
    monkeypatch.setattr(ask, "fetch_body", lambda db, m: "안녕하세요.\n협력사 평가표 작성해서 금요일까지 주세요.\n")
    r = executor.run(box, 1, _plan("T08", {"mail_ids": ["2"]}))
    assert "협력사 평가표 작성해서 금요일까지 주세요." in r.lines[0]
    assert executor.run(box, 1, _plan("T08")).kind == "ask"


def test_exclude_is_ready(box):
    r = executor.run(box, 1, _plan("T10", {"mail_ids": ["4"]}))
    assert r.kind == "done" and _status(box, 4) == "excluded" and r.action_id


def test_schedule_lists_due_and_events(box):
    from app.core.clock import now as clock_now
    day = clock_now().date()
    box.get(Task, 3).due_at = datetime.combine(day, datetime.min.time()).replace(hour=15)
    box.commit()
    r = executor.run(box, 1, _plan("T13", {"date_range": {"start": day.isoformat(), "end": day.isoformat()}}))
    assert r.kind == "query" and len(r.lines) == 1 and "[마감] 견적 회신" in r.lines[0] and [t.id for t in r.targets] == [3]


def test_change_due_by_voice_and_undo(box):
    r = executor.run(box, 1, _plan("T16", {"mail_ids": ["3"]}, {"due_at": "2099-01-09T18:00:00"}))
    assert r.kind == "done" and r.action_id
    box.expire_all()
    assert box.get(Task, 3).due_at == datetime(2099, 1, 9, 18)
    executor.run(box, 1, _plan("T04", params={"action_id": r.action_id}))
    box.expire_all()
    assert box.get(Task, 3).due_at == datetime(2026, 11, 10, 18)  # 되돌리면 이전 기한
    r = executor.run(box, 1, _plan("T16", {"sender": "김 팀장"}, {"due_at": "2099-01-09T18:00:00"}))
    assert r.kind == "ask" and len(r.targets) == 3  # 여러 건이면 하나를 고르게 한다
    assert executor.run(box, 1, _plan("T16", {"mail_ids": ["3"]}, {"due_at": None})).kind == "ask"


def test_find_mails_by_word_sender_and_sent(box):
    box.add(Mail(id=9, account_id=1, source_id="S-9", direction="sent", sender="me@example.com",
                 recipients=["lead@example.com"], subject="RE: 견적 회신", sent_at=datetime(2026, 11, 2, 15)))
    box.get(Task, 2).status = "done"
    box.commit()
    r = executor.run(box, 1, _plan("T19", {"keyword": "평가표"}))
    assert r.kind == "query" and [m.mail_id for m in r.mails] == [2] and r.title == "받은 메일 1통입니다"  # 끝난 업무의 메일도
    r = executor.run(box, 1, _plan("T19", {"sender": "김 팀장"}))
    assert [m.mail_id for m in r.mails] == [3, 2, 1] and r.mails[0].who == "김민준 팀장"
    r = executor.run(box, 1, _plan("T19", {"sender": "김 팀장"}, {"sent": True}))
    assert [m.mail_id for m in r.mails] == [9] and r.mails[0].direction == "sent"
    assert executor.run(box, 1, _plan("T19", {"sender": "박 책임"}, {"sent": True})).kind == "empty"
    r = executor.run(box, 1, _plan("T19", {"date_range": {"start": "2026-11-02", "end": "2026-11-02"}}))
    assert r.title == "받은 메일 4통입니다"


def test_summarize_mail_masks_body_and_restores(box, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(executor, "fetch_body", lambda db, m: "김민준 팀장입니다. 계약서 검토 부탁합니다.")
    seen = {}

    class AI:
        def summarize(self, payload):
            seen.update(payload)
            return SimpleNamespace(mail_summary=SimpleNamespace(gist="계약서 검토 요청", asks=["계약서 검토"], due_text=None))

    r = executor.run(box, 1, _plan("T20", {"mail_ids": ["1"]}), ai=AI())
    assert r.kind == "query" and r.title == "계약서 검토 요청" and r.lines == ["요청: 계약서 검토"] and r.mails[0].mail_id == 1
    assert seen["mode"] == "mail" and "김민준" not in seen["mail"]["body"]  # 이름은 가려서 보낸다
    assert executor.run(box, 1, _plan("T20", {"mail_ids": ["1", "2"]}), ai=AI()).kind == "ask"
