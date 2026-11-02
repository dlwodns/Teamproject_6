from app.core.config import Settings
from app.llm.client import LLMError
from app.pipeline.classify import classify
from app.schemas.classify import ClassifyRequest, OwnerProfile, SenderFlags

ME = "me@corp.example"
OWNER = OwnerProfile(email=ME, name="김나래", position="팀장", team="데이터1팀", member_of=["all@corp.example"])
SET = Settings()


def mail(body, *, to=(ME,), cc=(), subject="문의", sender=SenderFlags(), attachments=()):
    return ClassifyRequest(**{"from": "a@corp.example"}, mail_id="X-1", to=list(to), cc=list(cc), subject=subject,
                           body=body, attachments=list(attachments), received_at="2026-11-02T10:00", owner=OWNER, sender=sender)


def test_direct_request_rule_only(fake_llm):
    r = classify(mail("팀장님, 분기 실적표를 엑셀로 수요일까지 보내 주세요."), fake_llm, SET)
    assert r.source == "rule" and fake_llm.calls == []
    assert r.action_types == ["자료제출요청"] and r.category == "요청"
    assert r.tasks[0].due_at.isoformat() == "2026-11-04T18:00:00" and r.tasks[0].format == "xlsx"
    assert r.mentioned_me and r.priority in ("P2", "P3")


def test_cc_without_mention_is_reference(fake_llm):
    r = classify(mail("박 책임님, 결과 공유드립니다.", to=["b@corp.example"], cc=[ME]), fake_llm, SET)
    assert r.action_types == ["참조"] and r.tasks == [] and r.category == "기타"


def test_notice_without_mention_has_no_task(fake_llm):
    r = classify(mail("11/7(토) 시스템 점검이 진행됩니다. 업무에 참고 부탁드립니다.", to=["all@corp.example"],
                      subject="[안내] 정기 점검"), fake_llm, SET)
    assert r.action_types == ["공지"] and r.tasks == []


def test_notice_naming_my_team_creates_request(fake_llm):
    body = "보안 점검을 실시합니다.\n아래 팀은 결과표를 11/6까지 제출 바랍니다.\n- 데이터1팀\n- 운영2팀"
    r = classify(mail(body, to=["all@corp.example"], subject="[정보보안] 점검 안내"), fake_llm, SET)
    assert r.action_types[:2] == ["공지", "자료제출요청"] and r.category == "요청" and len(r.tasks) == 1
    assert r.mentioned_me


def test_meeting_change_creates_attend_task(fake_llm):
    r = classify(mail("내일 회의를 14:00에서 16:00로 변경합니다.", subject="[회의] 주간 점검 시간 변경"), fake_llm, SET)
    assert r.action_types == ["일정참석"] and r.tasks[0].due_at.isoformat() == "2026-11-03T16:00:00"


def test_notice_with_undirected_request_routes_to_exaone(fake_llm):
    # 요청 문장이 있는데 나를 향했는지 못 정한 공지는 '할 일 없음'을 믿지 않고 엑사원에게 묻는다(D15)
    body = "장기 미사용 서버를 회수합니다.\n해당 서버를 쓰는 팀은 11/6까지 계속 사용 여부를 회신해 주십시오."
    r = classify(mail(body, to=["all@corp.example"], subject="[IT운영] 자원 회수 안내"), fake_llm, SET)
    assert r.confidence < SET.router_threshold and len(fake_llm.calls) == 1


def test_completion_reply_is_answer_without_exaone(fake_llm):
    # 내 요청에 대한 완료 · 확정 회신은 할 일이 아니다. 엑사원은 여기에 '~ 확인' 할 일을 만들었다(AI-T5)
    r = classify(mail("요청하신 개발 서버 증설 작업이 완료되었습니다.", subject="RE: [요청] 서버 증설"), fake_llm, SET)
    assert r.action_types == ["회신"] and r.tasks == [] and fake_llm.calls == []


def test_mentioned_only_with_task(fake_llm):
    fake_llm.replies = [{"action_types": ["공지"], "mentioned_me": True, "urgent": False, "is_follow_up": False, "tasks": []}]
    r = classify(mail("웨비나 일정을 안내드립니다.", subject="11월 웨비나"), fake_llm, SET)
    assert r.source == "exaone" and r.tasks == [] and not r.mentioned_me


def test_two_requests_in_one_sentence(fake_llm):
    r = classify(mail("진행 현황을 금요일까지 회신해 주시고, 다음 회의 안건도 함께 보내주세요."), fake_llm, SET)
    assert len(r.tasks) == 2


def test_low_confidence_routes_to_exaone(fake_llm):
    fake_llm.replies = [{"action_types": ["검토승인요청"], "mentioned_me": True, "urgent": False, "is_follow_up": False,
                         "tasks": [{"action": "발표자료 검토", "due_raw": "내일까지", "format": "없음"}]}]
    r = classify(mail("시간 되실 때 한번 봐주시면 감사하겠습니다.", subject="발표자료"), fake_llm, SET)
    assert r.source == "exaone" and r.prompt_version == "classify_v1" and len(fake_llm.calls) == 1
    assert r.tasks[0].due_at.isoformat() == "2026-11-03T18:00:00"  # 날짜 환산은 코드


def test_exaone_failure_falls_back_to_rules(fake_llm):
    fake_llm.replies = [LLMError("ollama 호출 실패: ConnectError")]
    r = classify(mail("시간 되실 때 한번 봐주시면 감사하겠습니다."), fake_llm, SET)
    assert r.source == "rule" and r.fallback and len(r.tasks) == 1  # 규칙이 찾은 업무는 남는다


def test_model_dropping_task_keeps_rule_task(fake_llm):
    fake_llm.replies = [{"action_types": ["기타"], "mentioned_me": False, "urgent": False, "is_follow_up": False, "tasks": []}]
    r = classify(mail("혹시 원본 파일로 다시 보내주실 수 있을까요?"), fake_llm, SET)
    assert r.source == "exaone" and len(r.tasks) == 1  # 누락 방지(D15)


def test_priority_by_code(fake_llm):
    r = classify(mail("[긴급] 오늘 17시까지 장애 보고서 제출 부탁드립니다.", sender=SenderFlags(is_superior=True)), fake_llm, SET)
    assert r.urgent and r.priority == "P1"  # 상급자 30 + 24h 30 + 긴급 15 + TO 10


def test_classify_endpoint(client):
    body = {"mail_id": "X-2", "from": "a@corp.example", "to": [ME], "subject": "요청", "received_at": "2026-11-02T10:00",
            "body": "자료를 내일까지 제출 부탁드립니다.", "owner": OWNER.model_dump()}
    r = client.post("/classify", json=body)
    assert r.status_code == 200 and r.json()["tasks"][0]["due_at"] == "2026-11-03T18:00:00"
