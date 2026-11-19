"""분류 파이프라인 (AI-19 · AI-D15 · AI-D19): 판단은 모두 모델, 규칙은 구조 · 틀만. 모델 답을 규칙이 바꾸지 않는다(예외 없음)."""
from app.core.config import Settings
from app.llm.client import LLMError
from app.pipeline.classify import classify
from app.pipeline.conditions import read
import pytest

from app.pipeline.classify import ModelOutputError
from app.prompts.classify_v8 import render_user, trim_body
from app.schemas.classify import ClassifyRequest, OwnerProfile, SenderFlags
from tests.conftest import FakeLLM

ME = "me@corp.example"
OWNER = OwnerProfile(email=ME, name="김나래", position="팀장", team="데이터1팀", member_of=["all@corp.example"])
SET = Settings()


def mail(body, *, to=(ME,), cc=(), subject="문의", sender=SenderFlags(), attachments=(), frm="a@corp.example"):
    return ClassifyRequest(**{"from": frm}, mail_id="X-1", to=list(to), cc=list(cc), subject=subject,
                           body=body, attachments=list(attachments), received_at="2026-11-02T10:00", owner=OWNER, sender=sender)


def task(kind, action, due="없음", fmt="없음", to="요청자"):
    return {"type": kind, "action": action, "due_raw": due, "format": fmt, "to": to}


def run(m, mail_type, *tasks):
    llm = FakeLLM([{"mail_type": mail_type, "tasks": list(tasks)}])
    return classify(m, llm, SET), llm


def test_model_type_is_not_overwritten_by_rules():
    # DE-9 수정안 A · B: 초안을 보내며 '의견 주시면'은 검토다. 예전에는 규칙이 회신요청으로 덮어썼다
    r, llm = run(mail("설계서 초안 보내드립니다. 금요일까지 의견 주시면 반영하겠습니다."), "요청",
                 task("검토승인요청", "설계서 초안 검토 의견 회신", "금요일까지"))
    assert r.action_types == ["검토승인요청"] and r.category == "검토" and r.source == "exaone"
    assert r.tasks[0].type == "검토승인요청" and r.tasks[0].due_at.isoformat() == "2026-11-06T18:00:00"
    assert r.prompt_version == "classify_v8.2" and r.rules_version == "conditions_v1" and len(llm.calls) == 1


def test_each_task_keeps_its_type_and_deliver_to():
    r, _ = run(mail("월요일 10시 점검 회의에 참석해 주시고, 실적 표는 금요일까지 PMO 공유 폴더에 올려 주세요."), "요청",
               task("일정참석", "점검 회의 참석", "월요일 10시"), task("자료제출요청", "실적 표 업로드", "금요일까지", "xlsx", "PMO 공유 폴더"))
    assert r.action_types == ["일정참석", "자료제출요청"] and r.category == "요청"
    assert [t.type for t in r.tasks] == ["일정참석", "자료제출요청"]
    assert r.tasks[0].due_at.isoformat() == "2026-11-02T10:00:00" or r.tasks[0].due_at.hour == 10  # 회의 일시(마감 표지 없음)
    assert r.tasks[0].deliver_to is None and r.tasks[1].deliver_to == "PMO 공유 폴더" and r.tasks[1].format == "xlsx"


def test_action_request_is_new_type():
    r, _ = run(mail("보안 포털에서 관리자 계정 2단계 인증을 이번 주 안에 설정해 주세요."), "요청",
               task("조치요청", "관리자 계정 2단계 인증 설정", "이번 주 안에"))
    assert r.action_types == ["조치요청"] and r.category == "요청" and r.lane == "할 일"


def test_task_types_come_before_notice():
    # 공지 속 지목 요청: 해야 하는 것을 먼저 본다(11/7). 5분류는 할 일 유형으로 묶는다
    r, _ = run(mail("각 팀장님은 화요일까지 교육 계획을 제출해 주세요.", to=["all@corp.example"]), "공지",
               task("자료제출요청", "교육 계획 제출", "화요일까지"))
    assert r.action_types == ["자료제출요청", "공지"] and r.category == "요청" and r.mentioned_me


def test_cc_type_is_model_answer():
    # AI-D19: 참조는 모델이 정한다. 할 일이 있으면 할 일 유형 뒤에 모델의 '참조'를 붙인다(v7은 CC면 코드가 참조로 바꿈)
    cc = dict(to=["b@corp.example"], cc=[ME])
    r, _ = run(mail("팀장님께서 A안 B안 중 정해 주셔야 합니다. 목요일까지 알려 주세요.", **cc), "참조",
               task("회신요청", "A안 B안 중 결정 회신", "목요일까지"))
    assert r.action_types == ["회신요청", "참조"] and r.category == "회신"
    r, _ = run(mail("결과 공유드립니다.", **cc), "참조")
    assert r.action_types == ["참조"] and r.lane == "참고" and r.checks == []
    r, _ = run(mail("결과 공유드립니다.", **cc), "공유")  # 모델이 공유라고 하면 공유다(코드가 참조로 바꾸지 않는다)
    assert r.action_types == ["공유"] and r.checks == []  # 칸 배치(구조): 나에게 직접 온 메일만 확인 칸


def test_reply_is_reply_whatever_the_status():
    # 회신은 완료 · 진행 중 · 어렵다는 답 모두 회신이다. 안의 내용은 열어서 본다(11/7). 나에게 온 회신은 확인 칸
    for body in ("요청하신 서버 발주를 마쳤습니다.", "요청하신 서버는 다음 주 입고 예정입니다.", "요청하신 증원은 이번 분기에는 어렵겠습니다."):
        r, _ = run(mail(body, subject="RE: 서버 증설 요청"), "회신")
        assert r.action_types == ["회신"] and r.tasks == [] and r.lane == "확인" and r.checks[0].reason == "회신"


def test_shared_info_and_notice_lanes():
    r, _ = run(mail("어제 고객사 미팅 메모 공유드립니다."), "공유")
    assert r.action_types == ["공유"] and r.category == "기타" and r.lane == "확인" and r.checks[0].reason == "공유"
    r, _ = run(mail("토요일 메일 서버 점검이 있습니다.", to=["all@corp.example"]), "공지")
    assert r.action_types == ["공지"] and r.lane == "참고" and r.checks == []  # 단체 메일은 참고 칸
    r, _ = run(mail("보안 세미나에 초대합니다.", frm="news@vendor.example"), "기타")
    assert r.action_types == ["기타"] and r.lane == "참고"


def test_said_not_needed_is_model_judgment():
    # AI-D19: '참석하지 않으셔도 됩니다'를 읽고 할 일을 비우는 것은 모델이다. 코드는 모델 할 일을 옮기지 않는다(v7은 정규식으로 옮김)
    m = mail("미팅 메모 공유드립니다. 내일 회의에는 저희만 들어가니 참석하지 않으셔도 됩니다.")
    r, _ = run(m, "공유", task("일정참석", "내일 회의 참석"))
    assert [t.type for t in r.tasks] == ["일정참석"] and r.lane == "할 일"
    r, _ = run(m, "공유")
    assert r.tasks == [] and r.action_types == ["공유"] and r.checks[0].reason == "공유"


def test_conditional_no_reply_still_needs_check():
    # '이상 없으면 회신 안 하셔도 됩니다'는 이상 없는지 확인해야 하므로 할 일이다(11/7)
    m = mail("정산 내역 첨부합니다. 이상 없으시면 따로 회신 안 하셔도 됩니다.")
    assert read(m).no_action == {}
    r, _ = run(m, "공유", task("검토승인요청", "정산 내역 확인"))
    assert r.action_types == ["검토승인요청"] and r.lane == "할 일"


def test_model_failure_is_not_filled_by_rules():
    # AI-D19: 모델 호출이 실패하면 규칙으로 유형 · 확인 칸을 만들지 않고 실패를 올린다(backend가 다시 부른다)
    with pytest.raises(LLMError, match="연결 실패"):
        classify(mail("자료 보내 주세요."), FakeLLM([LLMError("연결 실패")]), SET)


def test_classify_endpoint_reports_failure_kind(client, fake_llm):
    from app.llm.client import LLMAuthError, LLMQuotaError
    body = {"mail_id": "M-1", "from": "a@corp.example", "to": [ME], "subject": "요청", "received_at": "2026-11-02T10:00:00",
            "body": "비밀 본문", "owner": {"email": ME, "name": "김나래"}}
    for err, code, kind in ((LLMQuotaError("한도 소진"), 503, "quota"), (LLMAuthError("키 없음"), 503, "auth"), (LLMError("엑사원 API 호출 실패: HTTP 429"), 503, "model_failed"),
                            ({"mail_type": "요청", "tasks": []}, 502, "bad_output")):
        fake_llm.replies.append(err)
        r = client.post("/classify", json=body)
        assert r.status_code == code and r.json()["detail"]["kind"] == kind and "비밀" not in r.text


def test_request_sentence_flag_when_model_finds_no_task():
    # 누락 안전망(11/13 유지): 나 혼자 받은 메일에 요청 어미 문장이 있는데 모델이 할 일을 비우면 확인 칸에 표시만 한다
    # 할 일을 만들지 않고 모델 유형도 그대로다
    r, _ = run(mail("주간 보고서 첨부합니다. 검토 부탁드립니다."), "공유")
    assert r.tasks == [] and r.action_types == ["공유"] and r.checks[0].reason == "요청 문장 있음"
    assert r.checks[0].evidence == "검토 부탁드립니다."
    r, _ = run(mail("주간 보고서 첨부합니다. 검토 부탁드립니다.", to=[ME, "b@corp.example"]), "공유")
    assert r.checks[0].reason == "공유"  # 여럿이 받은 메일은 표시하지 않는다


def test_request_without_task_is_inconsistent_model_answer():
    # 모델이 '요청'이라 하고 할 일을 비웠다 → v7은 코드가 공지 · 공유로 메웠다. 지금은 맞지 않는 답으로 올려 다시 부른다
    with pytest.raises(ModelOutputError):
        run(mail("자료 보내 주세요."), "요청")


def test_model_due_not_in_mail_is_dropped():
    r, _ = run(mail("자료 보내 주세요."), "요청", task("자료제출요청", "자료 제출", "내일까지"))
    assert r.tasks[0].due_raw is None and r.tasks[0].due_at is None


def test_model_decides_what_the_deadline_is():
    # 무엇이 기한인지는 모델이 판단한다(11/7). 마감 표지가 없어도 모델이 기한으로 고르면 코드는 날짜만 계산한다
    m = mail("다음 주 초에 운영회의에서 이관 상황을 보고합니다. 거기에 1팀 일정표가 한 장 들어가야 합니다.")
    r, _ = run(m, "요청", task("자료제출요청", "1팀 이관 일정표 작성", "다음 주 초"))
    assert r.tasks[0].due_at.isoformat() == "2026-11-10T18:00:00"  # 다음 주 초 = 다음 주 화요일 18시(라벨 가이드 4절)
    r, _ = run(m, "요청", task("자료제출요청", "1팀 이관 일정표 작성"))  # 모델이 기한을 비우면 코드도 만들지 않는다
    assert r.tasks[0].due_raw is None and r.tasks[0].due_at is None


def test_unknown_event_time_keeps_short_phrase():
    # '내일 고객 보고 들어가기 전에'는 보고 시각을 모른다 → 줄인 문구는 남기고 시각은 비운다(계산기에 안 맞는다고 버리지 않는다)
    m = mail("제안서 최종본입니다. 내일 고객 보고 들어가기 전에 기술 범위가 맞는지 한 번만 봐 주세요.")
    r, _ = run(m, "요청", task("검토승인요청", "제안서 기술 범위 확인", "내일 고객 보고 전"))
    assert r.tasks[0].due_raw == "내일 고객 보고 전" and r.tasks[0].due_at is None


def test_meeting_task_gets_meeting_time():
    r, _ = run(mail("주간 회의를 엽니다.\n일시: 11/5(수) 15:00\n장소: 3층", subject="[회의] 주간 회의"), "요청",
               task("일정참석", "주간 회의 참석"))
    assert r.tasks[0].due_at.isoformat() == "2026-11-05T15:00:00"


def test_bad_model_values_fall_back():
    llm = FakeLLM([{"mail_type": "모름", "tasks": [{"type": "이상한유형", "action": "자료 회신", "due_raw": "없음", "format": "없음", "to": ""},
                                                {"type": "회신요청", "action": " ", "due_raw": "없음", "format": "없음", "to": ""}]}])
    r = classify(mail("자료 회신 부탁드립니다."), llm, SET)
    assert [t.type for t in r.tasks] == ["회신요청"] and r.action_types == ["회신요청"]


def test_mentioned_only_with_task():
    # 지목 = 나에게 맡긴 일이 있다(11/7). 이름이 불려도 할 일이 없으면 지목이 아니다
    r, _ = run(mail("김나래 팀장님, 결과 공유드립니다."), "공유")
    assert not r.mentioned_me
    r, _ = run(mail("팀장 회의를 14시로 변경합니다. 변경된 시간에 맞춰 참석해 주십시오.", to=["leaders@corp.example"]), "공지",
               task("일정참석", "팀장 회의 참석"))
    assert r.mentioned_me


def test_hurry_word_grounds_asap():
    # '급히'처럼 서두르는 말도 ASAP다(11/7). 모델이 'ASAP'로 적으면 근거가 있다고 본다
    r, _ = run(mail("급히 사양표를 보내 주세요."), "요청", task("자료제출요청", "사양표 제출", "ASAP"))
    assert r.tasks[0].due_raw == "ASAP" and r.tasks[0].due_at is None


def test_priority_and_flags_from_model():
    llm = FakeLLM([{"mail_type": "요청", "urgent": True, "follow_up": True, "tasks": [task("자료제출요청", "장애 보고서 제출", "오늘 중으로")]}])
    r = classify(mail("[긴급] 재요청드립니다. 장애 보고서를 오늘 중으로 보내 주세요.", sender=SenderFlags(is_superior=True)), llm, SET)
    assert r.urgent and r.is_follow_up and r.priority == "P1"  # 우선순위는 코드 공식(구조), 긴급 · 재요청은 모델 값
    llm = FakeLLM([{"mail_type": "회신", "urgent": False, "follow_up": False, "tasks": []}])
    r = classify(mail("요청하신 자료 보내드립니다.", subject="RE: [긴급] 자료 요청"), llm, SET)
    assert not r.urgent


def test_render_user_passes_conditions_only():
    m = mail("결과 공유드립니다.\n수신을 원치 않으시면 여기를 누르세요.", to=["b@corp.example"], cc=[ME], frm="news@vendor.example")
    u = render_user(m, read(m))
    assert "받는사람: 다른 사람 (나는 참조)" in u and "보낸 곳: 사외 · 자동 발송" in u


def test_signature_trimmed_for_model():
    body = "안녕하세요.\n자료 부탁드립니다.\n\n*****************\n홍길동 책임 / Gildong Hong\n사업부 / 데이터1팀\nE-Mail : a@b\nPhone : 1\n*****************"
    assert trim_body(body) == "안녕하세요.\n자료 부탁드립니다.\n(보낸사람: 홍길동 책임 / 데이터1팀)"
    assert trim_body("서명 없는 본문") == "서명 없는 본문"


def test_signature_in_quote_keeps_rest():
    """인용 속 서명란에서 자르지 않는다. 본문 끝 서명란만 줄인다(v8.1, dev9 M-0004)."""
    def sig(n):
        return f"\n*****************\n{n} 책임 / X\n사업부 / {n}팀\nE-Mail : a@b\n*****************"
    body = ("다시 요청드립니다.\n\n-----Original Message-----\n원래 요청입니다." + sig("임소희")
            + "\n\n보낸 사람: 문가영\n품질 점검 결과입니다." + sig("문가영") + "\n\n감사합니다.\n" + sig("홍길동"))
    out = trim_body(body)
    assert "품질 점검 결과입니다." in out and "문가영 책임" in out  # 인용은 남는다
    assert out.endswith("감사합니다.\n(보낸사람: 홍길동 책임 / 홍길동팀)")


def test_classify_endpoint(client, fake_llm):
    fake_llm.replies.append({"mail_type": "요청", "tasks": [task("자료제출요청", "실적표 제출", "수요일까지", "xlsx")]})
    r = client.post("/classify", json={"mail_id": "M-1", "from": "a@corp.example", "to": [ME], "subject": "요청",
                                       "received_at": "2026-11-02T10:00:00", "body": "실적표를 수요일까지 엑셀로 보내 주세요.",
                                       "owner": {"email": ME, "name": "김나래", "position": "팀장", "team": "데이터1팀"}})
    j = r.json()
    assert r.status_code == 200 and j["tasks"][0]["type"] == "자료제출요청" and j["tasks"][0]["evidence"]
    assert "kind" not in j and j["confidence"] is None


def test_paraphrased_due_with_same_meaning_is_kept():
    # 모델이 본문 글자를 바꿔 써도 날짜 조각이 모두 본문에 있으면 같은 뜻이다(전에는 글자가 달라 지어낸 기한으로 버렸다)
    m = mail("법인카드 정산이 11/5(목) 마감됩니다. 미정산 건은 마감 전까지 처리 부탁드립니다.")
    r, _ = run(m, "요청", task("조치요청", "미정산 비용 처리", "11/5(목) 마감 전까지"))
    assert r.tasks[0].due_at.isoformat() == "2026-11-05T18:00:00"
    r, _ = run(m, "요청", task("조치요청", "미정산 비용 처리", "11/6(금)까지"))  # 본문에 없는 날짜는 여전히 버린다
    assert r.tasks[0].due_at is None and r.tasks[0].due_raw is None


def test_urgent_and_follow_up_are_model_judgment():
    # AI-D19: 긴급 · 재요청은 모델 값 그대로다. v7은 정해진 단어가 없으면 모델이 true라 해도 false였다
    llm = FakeLLM([{"mail_type": "요청", "urgent": False, "follow_up": False, "tasks": [task("검토승인요청", "계획서 결재")]}])
    r = classify(mail("결재 올려 두었습니다. 다시 연락드리겠습니다.", subject="[긴급 아님] 고객 미팅 관련"), llm, SET)
    assert not r.urgent and not r.is_follow_up
    llm = FakeLLM([{"mail_type": "요청", "urgent": True, "follow_up": True, "tasks": [task("자료제출요청", "장비 목록 제출")]}])
    r = classify(mail("지난주 말씀드린 장비 목록, 오늘 안에 꼭 받아야 합니다."), llm, SET)  # 정해진 단어가 없어도 모델 판단
    assert r.urgent and r.is_follow_up
    llm = FakeLLM([{"mail_type": "요청", "tasks": [task("자료제출요청", "장비 목록 제출")]}])
    r = classify(mail("급히 보내 주세요."), llm, SET)  # 모델이 칸을 내지 않으면 false(단어로 메우지 않는다)
    assert not r.urgent and not r.is_follow_up


def test_cc_tasks_are_model_judgment():
    # AI-D19: 참조로 받은 메일의 할 일은 모델이 정한다(정의: 나를 불러 맡긴 일만). v7은 이름 글자가 없으면 코드가 옮겼다
    cc = dict(to=["b@corp.example"], cc=[ME])
    r, _ = run(mail("박 책임님, 반납 일정을 금요일까지 회신 부탁드립니다.", **cc), "참조")
    assert r.tasks == [] and r.action_types == ["참조"] and r.checks == []
    r, _ = run(mail("박 책임님, 일정 공유드립니다. 팀장님께서 A안 B안 중 정해 주셔야 합니다.", **cc), "참조", task("회신요청", "A안 B안 결정"))
    assert [t.type for t in r.tasks] == ["회신요청"] and r.action_types == ["회신요청", "참조"]


def test_role_and_team_lists_are_addressed_to_me():
    owner = OwnerProfile(email=ME, name="김나래", position="책임", team="데이터1팀",
                         member_of=["all@corp.example", "seniors@corp.example", "data1@corp.example"],
                         role_lists=["seniors@corp.example"], team_lists=["data1@corp.example"])
    for to, want in ((["seniors@corp.example"], "내 직책(책임) 배포 목록"), (["data1@corp.example"], "우리 팀 배포 목록"),
                     (["all@corp.example"], "전사·단체 배포 목록")):
        m = ClassifyRequest(**{"from": "a@corp.example"}, mail_id="X", to=to, subject="안내", body="안내드립니다.",
                            received_at="2026-11-02T10:00", owner=owner)
        assert f"받는사람: {want}" in render_user(m, read(m))


def test_auto_sent_type_is_model_answer():
    # AI-D19: 자동 발송은 사실로만 넘기고(보낸 곳: 자동 발송), 기타인지는 모델이 정한다(v7은 코드가 기타로 바꿈)
    m = mail("[자동발송] 야간 백업 결과입니다. 이 메일은 발신 전용입니다.", frm="noreply-backup@corp.example")
    assert "자동 발송" in render_user(m, read(m))
    assert run(m, "기타")[0].action_types == ["기타"]
    assert run(m, "공지")[0].action_types == ["공지"]


def test_notice_or_share_is_model_answer():
    # AI-D19: 공지 · 공유는 모델이 정의(받는 방식)대로 정한다. 코드는 모델 답을 바꾸지 않는다(v7은 받는 방식으로 코드가 바꿈)
    owner = OWNER.model_copy(update={"member_of": ["all@corp.example", "leads@corp.example"], "role_lists": ["leads@corp.example"]})
    m = mail("10월 실적을 공유드립니다. 자세한 수치는 첨부를 참고해 주세요.", to=["leads@corp.example"]).model_copy(update={"owner": owner})
    assert "받는사람: 내 직책(팀장) 배포 목록" in render_user(m, read(m))  # 받는 방식은 사실로 넘긴다
    assert run(m, "공지")[0].action_types == ["공지"] and run(m, "공유")[0].action_types == ["공유"]


def test_due_raw_shows_model_phrase_not_context_window():
    # 11/11: 회의 시각 계산용 문맥 조각이 '오전 9시 7층 대회'처럼 잘려 보였다. 날짜는 같고 보이는 문구만 모델 문구로
    r, _ = run(mail("이번 주 주간회의는 11/4(수) 오전 9시 7층 대회의실입니다. 진행 상황을 10분 정도 공유해 주세요."), "요청",
               task("일정참석", "주간회의 참석 및 진행 상황 공유", "11/4(수) 오전 9시"))
    assert r.tasks[0].due_raw == "11/4(수) 오전 9시" and r.tasks[0].due_at.isoformat() == "2026-11-04T09:00:00"


def test_alias_counts_as_me_for_recipient():
    """BE-7: 별칭(owner.aliases)으로 받은 메일도 '나에게 온 메일'(to · cc)로 본다."""
    from app.pipeline.conditions import recipient
    m = mail("검토 부탁드립니다.", to=("me@outlook.kr",))
    assert recipient(m) == "list"
    m = m.model_copy(update={"owner": OWNER.model_copy(update={"aliases": ["me@outlook.kr"]})})
    assert recipient(m) == "to"
    m = m.model_copy(update={"to": ["x@corp.example"], "cc": ["ME@outlook.kr"]})
    assert recipient(m) == "cc"


def test_english_deadlines_and_quoted_evidence():
    # 11/20 dev9 M-0011(영문): 기한 둘이 비고(2개 누락) 두 번째 근거가 '근거 문장 없음'이었다.
    # 모델은 본문 글자 그대로(by EOD Thursday) 옮기고, 날짜는 코드가 받은 날(목요일) 기준으로 계산한다
    body = ("Thank you for your time at last week's review sessions.\n"
            "Kim, could you kindly confirm which option works for your team by EOD Thursday?\n"
            "Kim, we would also appreciate it if you could share the updated runbook before our Friday sync at 10:00 AM KST.")
    m = ClassifyRequest(**{"from": "e@partner.example"}, mail_id="X-2", to=[ME], subject="Cutover window", body=body,
                        received_at="2026-11-19T23:53", owner=OWNER)
    q1 = "Kim, could you kindly confirm which option works for your team by EOD Thursday?"
    q2 = "Kim, we would also appreciate it if you could share the updated runbook before our Friday sync at 10:00 AM KST."
    r, _ = run(m, "요청", {**task("회신요청", "컷오버 옵션 회신", "by EOD Thursday"), "evidence": q1},
               {**task("자료제출요청", "갱신 런북 공유", "before our Friday sync at 10:00 AM KST", "xlsx"), "evidence": q2})
    assert [t.due_at.isoformat() for t in r.tasks] == ["2026-11-26T18:00:00", "2026-11-20T10:00:00"]
    assert [t.evidence for t in r.tasks] == [q1, q2] and r.tasks[1].due_time_stated
