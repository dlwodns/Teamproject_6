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


def test_notice_with_undirected_request_goes_to_check_lane(fake_llm):
    # 나를 향했는지 못 정한 당부(규칙 0.7)라도 kind가 '대상자 당부 공지'(칸: 확인)를 확신하면 엑사원에 묻지 않고
    # 확인 칸에 '해당 여부 확인'으로 띄운다(v3.2 문지기). 라벨 관례상 할 일은 아니지만 사용자가 볼 수 있게 한다
    body = "장기 미사용 서버를 회수합니다.\n해당 서버를 쓰는 팀은 11/6까지 계속 사용 여부를 회신해 주십시오."
    r = classify(mail(body, to=["all@corp.example"], subject="[IT운영] 자원 회수 안내"), fake_llm, SET)
    assert r.confidence < SET.router_threshold and fake_llm.calls == []
    assert r.kind == "K18" and r.tasks == [] and r.lane == "확인" and r.checks[0].reason == "해당 여부 확인"


def test_undirected_request_in_reference_lane_still_routes():
    # 지목 불확실한 요청이 있는데 kind 칸이 '참고'면 확인 칸에도 안 뜨므로 엑사원에 묻는다(보수적, D15)
    from types import SimpleNamespace
    from app.pipeline.classify import route
    k = SimpleNamespace(kind=SimpleNamespace(lane="참고"), needs_model=False, signals=SimpleNamespace(on=set()))
    r = SimpleNamespace(confidence=0.7, reasons=["지목 불확실한 요청"])
    assert route(r, k, 0.8)
    assert not route(SimpleNamespace(confidence=0.7, reasons=["단체 수신"]), k, 0.8)


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
    r = classify(mail("시간 되실 때 내일까지 한번 봐주시면 감사하겠습니다.", subject="발표자료"), fake_llm, SET)
    assert r.source == "exaone" and r.prompt_version == "classify_v3" and len(fake_llm.calls) == 1
    assert r.tasks[0].due_at.isoformat() == "2026-11-03T18:00:00"  # 날짜 환산은 코드


def test_model_due_not_in_mail_is_dropped(fake_llm):
    # 모델이 낸 기한 글자가 메일에 없으면 지어낸 것이다(근거 검증) — 할 일은 남기고 기한만 비운다
    fake_llm.replies = [{"action_types": ["검토승인요청"], "tasks": [{"action": "발표자료 검토", "due_raw": "금요일까지", "format": None}]}]
    r = classify(mail("시간 되실 때 한번 봐주시면 감사하겠습니다.", subject="발표자료"), fake_llm, SET)
    assert len(r.tasks) == 1 and r.tasks[0].due_raw is None and r.tasks[0].due_at is None


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


def test_file_format_request_is_submission(fake_llm):
    # '엑셀로 공유' · 'CSV로 내려받아'는 자료 제출. '공유 바랍니다'만 있으면 회신
    r = classify(mail("이번 달 장비 반납 계획을 다음 주 월요일까지 엑셀로 공유 부탁드립니다.", subject="장비 반납"), fake_llm, SET)
    assert r.action_types == ["자료제출요청"] and r.tasks[0].format == "xlsx"
    r = classify(mail("접속 로그를 CSV로 내려받아 주실 수 있을까요?", subject="로그"), fake_llm, SET)
    assert r.action_types == ["자료제출요청"] and r.tasks[0].format == "csv"
    r = classify(mail("교육 일정 변경 사항을 내일까지 정리해서 보고해 주세요.", subject="교육"), fake_llm, SET)
    assert r.action_types == ["회신요청"]


def test_resend_subject_makes_send_request_resend(fake_llm):
    r = classify(mail("발표 자료의 표가 그림으로 들어가 있습니다. 편집할 수 있게 엑셀로 보내주세요.", subject="[요청] 발표 자료 표 원본"),
                 fake_llm, SET)
    assert r.action_types == ["수정재전송요청"]


def test_reply_word_beats_review_subject(fake_llm):
    r = classify(mail("1팀 의견도 금요일까지 함께 부탁드립니다.", subject="[검토] 보안 예외 신청"), fake_llm, SET)
    assert r.action_types == ["회신요청"]
    r = classify(mail("검토 후 의견을 금요일까지 부탁드립니다.", subject="[검토] 보안 예외 신청"), fake_llm, SET)
    assert r.action_types == ["검토승인요청"]


def test_forwarded_capture_takes_inner_request(fake_llm):
    body = "팀장님, 고객 문자 내용 전달드립니다. 확인 부탁드립니다.\n[캡처 내용: \"장애 보고서를 11/9까지 워드 파일로 받을 수 있을까요?\"]"
    r = classify(mail(body, subject="[전달] 고객 문자"), fake_llm, SET)
    assert len(r.tasks) == 1 and r.action_types == ["자료제출요청"]
    assert r.tasks[0].due_at.isoformat() == "2026-11-09T18:00:00" and r.tasks[0].format == "docx"


def test_request_list_header_is_not_task(fake_llm):
    body = "분기 마감을 위해 세 가지 요청드립니다.\n1) 비용 내역을 양식에 작성해 수요일까지 회신 부탁드립니다.\n2) 담당자를 정해 내일까지 알려주세요."
    r = classify(mail(body, subject="분기 마감"), fake_llm, SET)
    assert len(r.tasks) == 2 and r.action_types == ["자료제출요청", "회신요청"]


def test_heavier_type_comes_first(fake_llm):
    r = classify(mail("진행 상황을 금요일까지 회신해 주시고, 다음 주 계획서도 함께 보내주세요.", subject="후속"), fake_llm, SET)
    assert r.action_types == ["자료제출요청", "회신요청"]
    assert [t.due_at.isoformat() for t in r.tasks] == ["2026-11-06T18:00:00"] * 2  # 뒤 요청도 앞 기한을 따른다


def test_due_from_following_courtesy_sentence(fake_llm):
    r = classify(mail("지난주 요청한 설문 결과가 아직 오지 않아 다시 요청드립니다. 목요일까지 어려우시면 말씀 부탁드립니다.",
                      subject="RE: 설문 결과"), fake_llm, SET)
    assert r.is_follow_up and r.tasks[0].due_at.isoformat() == "2026-11-05T18:00:00"


def test_reply_with_again_is_not_follow_up(fake_llm):
    r = classify(mail("검토해 보니 일정을 다시 잡아야 할지 의견 부탁드립니다.", subject="RE: 일정"), fake_llm, SET)
    assert not r.is_follow_up


def test_proposed_meeting_date_has_no_due(fake_llm):
    r = classify(mail("다음 주 목요일에 회고를 진행하려고 하는데 1팀 가능 여부 회신 부탁드립니다.", subject="회고"), fake_llm, SET)
    assert r.tasks and r.tasks[0].due_at is None


def test_mention_as_object_is_not_directed(fake_llm):
    r = classify(mail("본부장님, 하반기 계획 공유합니다. 팀장들과 내용 공유 부탁합니다.", to=["b@corp.example"], cc=[ME]), fake_llm, SET)
    assert r.tasks == [] and not r.mentioned_me


def test_also_me_takes_previous_request(fake_llm):
    body = "박 책임님, 오류 원인과 재발 방지 대책을 이번 주 내로 회신 부탁드립니다.\n김나래 팀장님께서도 한번 확인 부탁드립니다."
    r = classify(mail(body, to=["b@corp.example"], cc=[ME]), fake_llm, SET)
    assert r.tasks and r.tasks[0].due_at.isoformat() == "2026-11-06T18:00:00"



def test_name_marked_as_reference_is_not_mention(fake_llm):
    # '(김나래 팀장님 참조)'는 참고로 넣었다는 표시다. 참조 메일에서 지목으로 보지 않는다
    r = classify(mail("박 책임님, 점검 결과 공유드립니다.\n(김나래 팀장님 참조)", to=["b@corp.example"], cc=[ME]), fake_llm, SET)
    assert r.action_types == ["참조"] and r.tasks == [] and fake_llm.calls == []


def test_general_audience_notice_skips_model(fake_llm):
    # '미이수자는'처럼 내가 해당하는지 메일만으로 알 수 없는 공지 당부는 할 일이 아니고 엑사원에 묻지 않는다
    r = classify(mail("하반기 안전 교육 미이수자는 11/20까지 이수해 주시기 바랍니다.", to=["all@corp.example"],
                      subject="[인사] 안전 교육 안내"), fake_llm, SET)
    assert r.action_types == ["공지"] and r.tasks == [] and fake_llm.calls == []


# --- 엑사원 출력 합치기 (AI-5, 11/3 dev · dev2 엑사원 경로 오답 기준) ---

def _reply(types, tasks=(), **flags):
    return {"action_types": types, "tasks": [{"action": a, "due_raw": d, "format": "없음"} for a, d in tasks], **flags}


def test_external_notice_from_model_becomes_misc(fake_llm):
    # 사외 발신 메일을 모델이 공지로 고르면 홍보 · 초청이다. 할 일도 만들지 않는다
    fake_llm.replies = [_reply(["공지", "일정참석"], [("사전 등록", "금요일까지")])]
    req = mail("클라우드 포럼 사전 등록이 이번 주 마감됩니다.", subject="[안내] 포럼 등록").model_copy(update={"from_": "info@forum.example"})
    r = classify(req, fake_llm, SET)
    # v3.2: kind가 사외 홍보(K19)를 확신해 엑사원에 묻지 않아도 같은 결론이어야 한다
    assert r.action_types == ["기타"] and r.tasks == [] and r.kind == "K19"


def test_model_flags_are_not_trusted(fake_llm):
    # 긴급 · 재요청 · 지목은 규칙이 정한다. 모델은 거의 늘 true를 냈다
    fake_llm.replies = [_reply(["공지"], [], urgent=True, is_follow_up=True, mentioned_me=True)]
    r = classify(mail("사칭 메일이 돌고 있습니다. 링크를 누르지 마시고 신고해 주십시오.", to=["all@corp.example"],
                      subject="[정보보안] 주의 안내"), fake_llm, SET)
    assert not r.urgent and not r.is_follow_up and not r.mentioned_me


def test_generic_split_task_dropped_when_another_exists(fake_llm):
    fake_llm.replies = [_reply(["회신요청"], [("장애 원인과 재발 방지 대책 회신", "금요일까지"), ("결과 검토", "없음")])]
    r = classify(mail("시간 되실 때 장애 원인과 재발 방지 대책을 금요일까지 회신 부탁드립니다."), fake_llm, SET)
    assert r.source == "exaone" and [t.text for t in r.tasks] == ["장애 원인과 재발 방지 대책 회신"]


def test_meeting_task_gets_meeting_time(fake_llm):
    # 회의 참석은 회의 일시가 기한이다. 모델이 비운 기한은 규칙이 읽은 회의 시각으로 채운다
    fake_llm.replies = [_reply(["일정참석"], [("팀장 간담회 참석", "없음")])]
    r = classify(mail("팀장 간담회를 아래와 같이 엽니다.\n일시: 11/5(수) 15:00\n혹시 어려우시면 말씀해 주세요.",
                      to=["leaders@corp.example"], subject="[담당] 팀장 간담회"), fake_llm, SET)
    assert r.source == "exaone" and r.tasks[0].due_at.isoformat() == "2026-11-05T15:00:00"


def test_signature_trimmed_for_model():
    from app.prompts.classify_v3 import trim_body
    body = "안녕하세요.\n자료 부탁드립니다.\n\n*****************\n홍길동 책임 / Gildong Hong\n사업부 / 데이터1팀\nE-Mail : a@b\nPhone : 1\n*****************"
    assert trim_body(body) == "안녕하세요.\n자료 부탁드립니다.\n(보낸사람: 홍길동 책임 / 데이터1팀)"
    assert trim_body("서명 없는 본문") == "서명 없는 본문"


def test_meeting_invite_with_unmarked_request_is_attendance(fake_llm):
    # 회의 초대의 '미리 훑어봐 주세요'는 유형 단어 없는 당부 → 회의 참석, 기한은 회의 일시(규칙 v1.3 약한 유형)
    r = classify(mail("다온증권 제안 킥오프 회의를 엽니다.\n일시: 11/04(수) 14:00~15:00\n요약본 첨부드리니 미리 한번 훑어봐 주세요.",
                      subject="[회의] 제안 킥오프 (11/04 수 14:00)"), fake_llm, SET)
    assert r.action_types == ["일정참석"] and r.tasks[0].due_at.isoformat() == "2026-11-04T14:00:00"


def test_general_audience_without_notice_subject_is_notice(fake_llm):
    # 공지 표지가 없는 단체 메일이어도 '전 직원은 ~ 바랍니다'는 할 일이 아니라 확인할 공지다(11/3 사용자 확인)
    r = classify(mail("전 직원은 이번 주 안에 비밀번호를 변경해 주시기 바랍니다.", to=["all@corp.example"], subject="비밀번호 변경"),
                 fake_llm, SET)
    assert r.action_types == ["공지"] and r.tasks == [] and fake_llm.calls == []



def test_audience_notice_with_position_info_skips_model(fake_llm):
    # 요청은 '미이수자는' 당부뿐이고 내 직급은 안내 문장에만 나온다 → 확인할 공지, 엑사원에 묻지 않는다(규칙 v1.5)
    r = classify(mail("법정 교육 미이수자는 11/20까지 이수해 주십시오.\n팀장님들께서는 포털에서 팀원 이수 여부를 확인하실 수 있습니다.",
                      to=["all@corp.example"], subject="[정보보안] 법정 교육 미이수자 안내"), fake_llm, SET)
    assert r.action_types == ["공지"] and r.tasks == [] and not r.mentioned_me and fake_llm.calls == []


# --- 확인 칸 (사용자 항목 2, 11/3): 할 일 없는 회신 · 완료 보고 · 대상자 당부는 할 일 대신 확인 칸으로 ---

def test_completion_reply_goes_to_checks(fake_llm):
    r = classify(mail("요청하신 개발 서버 증설 작업이 완료되었습니다.", subject="RE: [요청] 서버 증설"), fake_llm, SET)
    assert r.tasks == [] and len(r.checks) == 1
    c = r.checks[0]
    assert c.reason == "완료 보고" and c.text == "서버 증설" and c.source == "rule" and "완료" in c.evidence


def test_answer_reply_goes_to_checks(fake_llm):
    r = classify(mail("요청하신 견적서를 첨부드립니다.", subject="RE: [견적요청] 2단계 견적"), fake_llm, SET)
    assert r.tasks == [] and [(c.reason, c.text) for c in r.checks] == [("결과 회신", "2단계 견적")]


def test_completion_report_without_reply_subject(fake_llm):
    # 회신 제목이 아니어도 나에게 온 완료 알림은 확인 칸이다(유형은 그대로)
    fake_llm.replies = [_reply(["회신"])]
    r = classify(mail("지난주 말씀하신 방화벽 정책 반영 끝났습니다.\n접속 테스트도 통과했습니다.", subject="[보고] 방화벽 정책 반영 완료"),
                 fake_llm, SET)
    assert r.tasks == [] and r.checks[0].reason == "완료 보고" and r.checks[0].text == "방화벽 정책 반영 완료"


def test_audience_notice_goes_to_checks(fake_llm):
    r = classify(mail("하반기 안전 교육 미이수자는 11/20까지 이수해 주시기 바랍니다.", to=["all@corp.example"],
                      subject="[인사] 안전 교육 안내"), fake_llm, SET)
    assert r.tasks == [] and r.checks[0].reason == "해당 여부 확인" and "미이수자" in r.checks[0].evidence


def test_plain_notice_and_reference_have_no_check(fake_llm):
    # 일반 공지 · 참조 수신은 참고만 하면 된다. 확인 칸이 넓으면 의미가 없다
    r = classify(mail("11/7(토) 시스템 점검이 진행됩니다. 업무에 참고 부탁드립니다.", to=["all@corp.example"],
                      subject="[안내] 정기 점검"), fake_llm, SET)
    assert r.checks == []
    r = classify(mail("박 책임님, 결과 공유드립니다.", to=["b@corp.example"], cc=[ME]), fake_llm, SET)
    assert r.checks == []


def test_task_mail_has_no_check(fake_llm):
    r = classify(mail("팀장님, 분기 실적표를 엑셀로 수요일까지 보내 주세요."), fake_llm, SET)
    assert r.tasks and r.checks == []


def test_model_read_only_task_moves_to_checks(fake_llm):
    # 규칙이 요청을 못 찾았고 모델 할 일이 기한 없는 '~ 확인'뿐이면 할 일이 아니라 확인 칸이다(AI-T5). 버리지 않는다
    fake_llm.replies = [_reply(["회신요청"], [("리허설 결과 확인", "없음")])]
    r = classify(mail("리허설 결과 전달합니다.", subject="리허설 결과"), fake_llm, SET)  # kind 맞는 형식 없음 → 엑사원행
    assert r.source == "exaone" and r.tasks == [] and not r.mentioned_me
    assert [(c.text, c.reason, c.source) for c in r.checks] == [("리허설 결과 확인", "읽고 확인", "exaone")]


def test_model_task_with_due_is_not_moved(fake_llm):
    # 기한이 있으면 '~ 확인'이어도 할 일로 둔다(D15)
    fake_llm.replies = [_reply(["회신요청"], [("리허설 결과 확인", "금요일까지")])]
    r = classify(mail("리허설 결과 전달합니다. 금요일까지 반영 예정입니다.", subject="리허설 결과"), fake_llm, SET)
    assert len(r.tasks) == 1 and r.checks == []


def test_model_task_with_other_verb_is_not_moved(fake_llm):
    # '확인 및 회신' · '준비'처럼 읽기 말고 다른 동사가 있으면 할 일로 둔다
    fake_llm.replies = [_reply(["회신요청"], [("참석자 명단 확인 및 회신", "없음")])]
    r = classify(mail("리허설 결과 전달합니다.", subject="리허설 결과"), fake_llm, SET)
    assert len(r.tasks) == 1 and r.checks == []


def test_model_task_kept_when_rule_found_request(fake_llm):
    # 규칙이 나를 향한 요청 문장을 찾았으면 기한 없는 '확인'도 할 일이다(D15)
    fake_llm.replies = [_reply(["검토승인요청"], [("결과 확인", "없음")])]
    r = classify(mail("시간 되실 때 결과 한번 확인 부탁드립니다."), fake_llm, SET)
    assert r.source == "exaone" and len(r.tasks) == 1 and r.checks == []


def test_reply_head_task_moves_instead_of_dropped(fake_llm):
    # '회신'을 맨 앞에 둔 모델 할 일은 전에는 버렸다. 이제 확인 칸으로 옮긴다
    fake_llm.replies = [_reply(["회신"], [("계정 발급 결과 확인", "오늘 오후")])]
    r = classify(mail("계정은 오늘 오후에 발급될 예정입니다.", subject="RE: 계정 발급"), fake_llm, SET)
    assert r.source == "exaone" and r.tasks == [] and r.action_types == ["회신"]
    assert [(c.text, c.reason, c.source) for c in r.checks] == [("계정 발급 결과 확인", "결과 회신", "exaone")]


def test_read_only_split():
    from app.pipeline.checks import read_only
    from app.schemas.classify import TaskOut
    yes = ["반영 결과 확인", "공지 내용 숙지", "변경 사항 확인 및 참고", "결과 확인 필요"]
    no = ["참석자 명단 확인 및 회신", "조직 개편 방향 참고 및 의견 수렴 준비", "보고서 검토", "확인 후 회신", "업데이트 확인 및 완료"]
    assert all(read_only(TaskOut(text=t)) for t in yes)
    assert not any(read_only(TaskOut(text=t)) for t in no)
    assert not read_only(TaskOut(text="결과 확인", due_raw="금요일까지"))


def test_v5_prompt_restricts_kind_to_candidates(fake_llm, monkeypatch):
    # v5(후보안): 시스템 프롬프트는 메일과 무관하게 같고(프리픽스 캐시), kind enum은 형식 후보로 좁힌다
    from app.pipeline import classify as C, kinds
    from app.prompts import classify_v5
    req = mail("리허설 결과 전달합니다.", subject="리허설 결과")  # 맞는 형식 없음 → 엑사원행
    k = kinds.classify_kind(req)
    assert classify_v5.schema_for(k)["properties"]["kind"]["enum"] == classify_v5.candidates(k)
    assert "리허설" not in classify_v5.SYSTEM and "형식 후보" in classify_v5.render_user(req, "to", k, [])
    monkeypatch.setattr(C, "PROMPT", classify_v5)
    fake_llm.replies = [{"kind": "K12", "tasks": [{"action": "리허설 결과 확인", "due_raw": "없음", "format": "없음"}]}]
    r = C.classify(req, fake_llm, SET)
    assert r.source == "exaone" and r.prompt_version == "classify_v5"
    assert r.action_types[0] == "회신" and r.tasks == [] and r.checks  # 완료 보고 형식의 '~ 확인'은 확인 칸
