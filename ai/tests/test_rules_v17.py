"""규칙 v1.6 · v1.7 (AI-18 · DE-9 놓친 메일 6묶음 · 11/5 규칙 허점). 개발 세트 문장을 베끼지 않고 같은 원리의 새 문장으로 확인한다."""
from app.pipeline.rules.mail_rules_v1 import judge
from app.schemas.classify import ClassifyRequest, OwnerProfile, SenderFlags

ME = "me@corp.example"
OWNER = OwnerProfile(email=ME, name="김나래", position="팀장", team="데이터1팀", member_of=["all@corp.example"])


def mail(body, *, to=(ME,), cc=(), subject="문의", frm="a@corp.example"):
    return ClassifyRequest(**{"from": frm}, mail_id="X-1", to=list(to), cc=list(cc), subject=subject, body=body,
                           attachments=[], received_at="2026-11-02T10:00", owner=OWNER, sender=SenderFlags())


def test_conditional_request_is_request():
    # ① '~해 주시면 ~하겠습니다' 조건형 부탁
    r = judge(mail("팀장님, 예산안 수정본 올렸습니다. 목요일까지 승인해 주시면 바로 집행하겠습니다."))
    assert len(r.tasks) == 1 and r.tasks[0].action_type == "검토승인요청" and r.tasks[0].due


def test_review_then_opinion_is_one_task():
    # ① 검토 요청 바로 뒤 '의견 주시면 반영하겠습니다'는 같은 검토다
    r = judge(mail("팀장님, 제안서 초안입니다.\n3장 일정표가 맞는지 봐주셨으면 합니다.\n수요일까지 의견 주시면 반영하겠습니다."))
    assert len(r.tasks) == 1 and r.tasks[0].action_type == "검토승인요청"


def test_bare_result_clause_is_not_request():
    # '정해지면 알려주시면 됩니다'처럼 뒤에 결과가 없는 허락 표현은 요청이 아니다
    r = judge(mail("회의 가능하다고 하셔서 확인했습니다.\n참석자는 정해지면 알려주시면 됩니다.", subject="RE: 회의 건"))
    assert r.tasks == []


def test_role_designation_in_notice():
    # ② 공지 속 '각 팀장은 ~' 직급 지목
    r = judge(mail("연말 자산 실사를 실시합니다.\n각 팀장은 팀 자산 목록을 11/9까지 제출해 주시기 바랍니다.",
                   to=["all@corp.example"], subject="[안내] 자산 실사"))
    assert r.tasks and r.action_types[0] == "공지" and r.mentioned_me


def test_named_target_then_request():
    # ② 바로 앞 문장이 나를 대상으로 지목하고 다음 문장이 요청
    body = "보안 교육 재수강 대상은 데이터1팀 김나래 팀장님입니다.\n가능한 날짜를 금요일까지 회신 부탁드립니다."
    r = judge(mail(body, to=["all@corp.example"], subject="[인사] 교육 안내"))
    assert len(r.tasks) == 1 and r.mentioned_me


def test_named_other_then_request_is_not_mine():
    body = "보안 교육 재수강 대상은 운영2팀 박지훈 팀장님입니다.\n가능한 날짜를 금요일까지 회신 부탁드립니다."
    r = judge(mail(body, to=["all@corp.example"], subject="[인사] 교육 안내"))
    assert r.tasks == []


def test_follow_up_need_and_deadline_change():
    # ③ RE: 재요청 · 마감 변경
    r = judge(mail("요청드린 견적서를 아직 받지 못했습니다.\n목요일 오전까지는 꼭 받아야 품의를 올릴 수 있습니다.",
                   subject="RE: 견적서 자료 요청", frm="b@vendor.example"))
    assert len(r.tasks) == 1 and r.is_follow_up and r.tasks[0].due
    r = judge(mail("일정이 당겨져 제출 마감을 11/6(금) 정오로 당깁니다.", to=["all@corp.example"], subject="RE: 명단 요청"))
    assert len(r.tasks) == 1 and r.tasks[0].due


def test_optional_offer_is_not_request():
    # ⑥ 받는 사람이 고르는 선택('관심 있으시면 · 필요하시면 · 원치 않으시면')
    for body in ("신규 상품을 소개합니다. 관심 있으시면 아래 링크에서 신청해 주세요.",
                 "계약이 다음 달 만료됩니다. 연장이 필요하시면 언제든 연락 주세요.",
                 "수신을 원치 않으시면 하단 링크를 눌러주세요."):
        assert judge(mail(body, frm="sales@vendor.example")).tasks == []


def test_internal_event_block_is_attend_task():
    # ⑤ 사내 단체 메일의 '일시: · 장소:' 블록은 참석 할 일, 사외 행사 안내는 아니다
    body = "분기 마무리 모임을 엽니다.\n일시: 11/12(목) 17:00\n장소: 본관 3층 대회의실\n편하게 오시면 됩니다."
    r = judge(mail(body, to=["all@corp.example"], subject="[담당] 분기 모임"))
    assert r.action_types == ["일정참석"] and r.tasks[0].due.due_at.isoformat() == "2026-11-12T17:00:00"
    r = judge(mail(body, to=["all@corp.example"], subject="[담당] 분기 모임", frm="event@vendor.example"))
    assert r.tasks == []


def test_enumerated_requests_stay_separate():
    # 한 메일 여러 업무: '두 가지 여쭙니다' 머리말은 업무가 아니고 '첫째 · 둘째'는 따로 센다
    body = ("팀장님, 두 가지 여쭙니다.\n첫째, 출장 계획서를 수요일까지 검토 부탁드립니다.\n"
            "둘째, 장비 구매를 이번 달에 할지 이번 주 중으로 의견 주시면 발주하겠습니다.")
    r = judge(mail(body, subject="[요청] 출장 계획서 검토 및 구매 문의"))
    assert [t.action_type for t in r.tasks] == ["검토승인요청", "회신요청"]


# ---------- v1.7 (11/5: 기한 · 일정 날짜 구분, 규칙 허점 한 번에, 전부 엑사원 + 상호보완) ----------
from datetime import datetime  # noqa: E402

from app.pipeline.dates import parse_deadline  # noqa: E402

BASE = datetime(2026, 11, 2, 9, 0)


def test_unknown_event_deadline_keeps_text_only():
    # '내일 미팅 전에': 미팅 시각은 사용자만 안다 → 문구 그대로, 시각은 비운다
    d = parse_deadline("내일 고객 미팅 전에 보내 주세요", BASE)
    assert d.raw == "내일 고객 미팅 전에" and d.due_at is None


def test_dates_without_deadline_marker_are_not_deadlines():
    for text in ("다음 주 화요일(10/27)에 개인 사정이 있어 재택 근무가 가능할지 여쭙니다",  # 그 밖의 날짜
                 "금요일에 보내드린 계획서 건 다시 여쭙니다",  # 지난 일
                 "11/5(목) 16:00에 리허설을 합니다"):  # 일정
        assert parse_deadline(text, BASE) is None


def test_deadline_markers_and_last_clause():
    assert parse_deadline("오늘 오후 1시에 보낼 예정이라 오전 중에 의견 부탁드립니다", BASE).due_at.isoformat() == "2026-11-02T12:00:00"
    assert parse_deadline("명단 마감을 11/4(수) 오후 3시로 당깁니다", BASE).due_at.isoformat() == "2026-11-04T15:00:00"
    assert parse_deadline("금주 중에 결재해 주시면", BASE).due_at.isoformat() == "2026-11-06T18:00:00"


def test_restated_request_is_one_task_with_later_deadline():
    body = "팀장님, 보안서약서 결재 올렸습니다. 확인 부탁드립니다.\n\n대상: 5명\n\n다시 말씀드리면 제출이 목요일이라, 수요일까지 서명 부탁드립니다."
    r = judge(mail(body, subject="[요청] 보안서약서 확인"))
    assert len(r.tasks) == 1 and r.tasks[0].due and r.tasks[0].due.due_at.isoformat() == "2026-11-04T18:00:00"


def test_meeting_contingency_is_attend_task():
    body = "11/6(금) 10:00 화상으로 설계 리뷰 회의를 엽니다.\n참석이 어려우시면 대리 참석자를 미리 알려주세요."
    r = judge(mail(body, subject="[리뷰] 설계 리뷰 회의 초대"))
    assert r.action_types == ["일정참석"] and r.tasks[0].due.due_at.isoformat() == "2026-11-06T10:00:00"


def test_closing_inquiry_line_is_not_task_and_must_send_is():
    body = "구매 현황을 공유드립니다.\n갱신에는 확인서가 필요하니 11/10(화)까지 확인서를 보내주셔야 합니다.\n그 외 문의 사항은 구매팀으로 연락 주세요."
    r = judge(mail(body, subject="[구매] 현황"))
    assert len(r.tasks) == 1 and r.tasks[0].due.due_at.isoformat() == "2026-11-10T18:00:00"


def test_apology_is_not_urgent_and_not_yet_is_follow_up():
    r = judge(mail("일정이 당겨져 마감을 11/4(수) 오후 3시로 당깁니다. 급하게 변경드려 죄송합니다.", to=["all@corp.example"],
                   subject="RE: 명단 요청"))
    assert not r.urgent and r.tasks
    assert judge(mail("부탁한 자료가 아직 안 왔습니다. 오늘 퇴근 전까지는 꼭 보내 주세요.", subject="RE: 자료")).is_follow_up


def test_permission_phrase_is_not_request():
    assert judge(mail("회의 가능하다고 하셔서 확인했습니다. 명단은 확정되면 알려주시면 됩니다.", subject="RE: 회의")).tasks == []


def test_all_mode_moves_model_task_from_general_sentence(fake_llm):
    # 상호보완: 규칙이 '나를 향하지 않았다'고 본 요청('기한 내 정산을 완료해 주십시오')으로 모델이 만든 할 일은 확인 칸으로
    from app.core.config import Settings
    from app.pipeline.classify import classify
    fake_llm.replies = [{"action_types": ["자료제출요청"], "tasks": [
        {"action": "사유서 작성 제출", "due_raw": "11/6(금)까지", "format": "없음"},
        {"action": "법인카드 정산 완료", "due_raw": "없음", "format": "없음"}]}]
    body = ("법인카드 정산 마감 안내입니다. 기한 내 정산을 완료해 주십시오.\n"
            "아울러 미정산 건이 많은 아래 팀은 사유서를 11/6(금)까지 제출해 주시기 바랍니다.\n- 데이터1팀\n- 운영2팀")
    r = classify(mail(body, to=["all@corp.example"], subject="[재무] 정산 마감 안내"), fake_llm, Settings())
    assert [t.text for t in r.tasks] == ["사유서 작성 제출"] and r.source == "exaone"


# ---------- v1.8 (11/5: 칸별 원인 분석 — 할 일 여부 · 유형 · 마감 · 지목 · 긴급 · 재요청) ----------
def test_no_action_and_auto_reply_and_optional():
    assert judge(mail("중간 결과 공유드립니다. 판단이 필요한 사항은 아직 없습니다. 참고만 해 주세요.", subject="[공유] 결과")).tasks == []
    r = judge(mail("11/2~11/3 휴가로 부재중입니다. 급한 건은 박 책임에게 연락 부탁드립니다.", subject="[자동회신] 부재중: 김OO"))
    assert r.tasks == [] and r.action_types == ["기타"] and not r.urgent
    r = judge(mail("가이드 초안 공유드립니다. 의견 있으신 분은 11/6까지 댓글로 남겨주세요.", to=["all@corp.example"], subject="[안내] 가이드"))
    assert r.tasks == [] and r.optional


def test_anaphoric_deadlines():
    r = judge(mail("내일 10시 고객 보고 때 이 자료로 갈 예정인데, 혹시 보완할 점 있으면 그 전에 말씀 주세요.", subject="PoC 결과"))
    assert r.tasks[0].due.due_at.isoformat() == "2026-11-03T10:00:00" and r.tasks[0].action_type == "검토승인요청"
    r = judge(mail("정산이 11/5(목) 마감됩니다.\n데이터1팀은 미정산 2건이 남아 있으니 마감 전까지 처리 부탁드립니다.", to=["all@corp.example"],
                   subject="[재무] 정산"))
    assert r.tasks[0].due.due_at.isoformat() == "2026-11-05T18:00:00" and r.mentioned_me


def test_question_date_and_sender_action_are_not_deadlines():
    r = judge(mail("점검을 내일로 미뤄도 되는지 오후 2시까지 판단 부탁드립니다.", subject="[급함] 점검 시간"))
    assert r.tasks[0].due.due_at.isoformat() == "2026-11-02T14:00:00" and r.urgent
    r = judge(mail("오전 중에 맞는 번호를 알려 주시면 오늘 발주 마감 전에 처리하겠습니다.", subject="[구매] 승인번호"))
    assert r.tasks[0].due.due_at.isoformat() == "2026-11-02T12:00:00"


def test_asap_label():
    d = parse_deadline("ASAP 승인 부탁드립니다.", datetime(2026, 11, 2, 10, 53))
    assert d.raw == "ASAP" and d.due_at.isoformat() == "2026-11-02T11:53:00"


def test_meeting_invite_with_material_request_has_two_tasks():
    body = "월간 보고회를 진행합니다.\n일시: 11/6(금) 16:00\n장소: 12층 대회의실\n팀별 발표 자료는 11/5(목) 12시까지 PMO로 보내주십시오."
    r = judge(mail(body, to=["all@corp.example"], subject="[PMO] 월간 보고회"))
    assert [t.action_type for t in r.tasks] == ["일정참석", "자료제출요청"]


def test_follow_up_and_restatement():
    assert judge(mail("지난주 요청드린 체크리스트 진행 상황 여쭙니다. 모레까지 받아볼 수 있을지요?", subject="RE: 체크리스트 작성 요청")).is_follow_up
    assert judge(mail("금요일에 드린 제안서 건 다시 말씀드립니다. 내일 오전 중으로 의견 주시면 반영하겠습니다.",
                      subject="RE: [검토 요청] 제안서")).is_follow_up
    assert not judge(mail("확인 부탁드립니다.\n\n다시 말씀드리면 수요일까지 서명 부탁드립니다.", subject="[요청] 서명")).is_follow_up


def test_specific_type_cues():
    r = judge(mail("PM 1명을 지정해서 내일 오후 2시 회의 전까지 이름만 보내 주세요. 일정이 촉박하니 서둘러 주시기 바랍니다.", subject="[사업단] PM 지정"))
    assert r.action_types[0] == "회신요청" and r.tasks[0].specific and r.urgent
    r = judge(mail("내일 오전 11시에 제 방으로 와 주세요.", subject="[담당] 전략 논의"))
    assert r.action_types == ["일정참석"] and r.tasks[0].due.due_at.isoformat() == "2026-11-03T11:00:00"


def test_short_team_name_is_mention():
    r = judge(mail("휴가 신청이 몰렸습니다. 1팀에 조정이 필요한 인원이 있으면 11/11까지 알려 주세요.", to=["all@corp.example"], subject="RE: 휴가"))
    assert r.tasks and r.mentioned_me
