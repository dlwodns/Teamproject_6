"""AI-15 근거 문장: 할 일마다 본문에 글자 그대로 있는 문장을 붙인다(화면 UX-D16 형광펜)."""
from app.core.config import Settings
from app.pipeline.classify import classify
from app.pipeline.evidence import attach, body_sentences
from app.schemas.classify import ClassifyRequest, OwnerProfile, TaskOut
from tests.conftest import FakeLLM

ME = "junho.lee@corp.example"
OWNER = OwnerProfile(email=ME, name="이준호", position="팀장", team="클라우드전환1팀", member_of=[])
SIGN = "\n\n감사합니다.\n\n**********\n박지영 팀장 / Jiyoung Park\n"
SET = Settings()


def req(body, subject="[요청] 자료 요청", **kw):
    return ClassifyRequest(**{"from": "jiyoung.park@corp.example"}, mail_id="M-1", to=[ME], subject=subject,
                           body=body, received_at="2026-11-02T09:00", owner=OWNER, **kw)


def lines_in_body(ev: str, body: str) -> bool:
    return all(x in body for x in ev.split("\n"))


def test_model_task_gets_evidence():
    # 할 일 문구는 모델 것이다 → 문구와 가장 닮은 본문 문장(기한 글자가 든 문장을 조금 더 쳐 준다)
    body = "사업단 월간 실적 보고를 위해 자료를 취합하고 있습니다.\n첨부 양식에 팀별 실적을 작성하신 뒤 엑셀 파일로 수요일까지 회신 부탁드립니다." + SIGN
    llm = FakeLLM([{"mail_type": "요청", "tasks": [{"type": "자료제출요청", "action": "팀별 실적 엑셀로 회신", "due_raw": "수요일까지",
                                                  "format": "xlsx", "to": "요청자"}]}])
    r = classify(req(body, attachments=["실적양식.xlsx"]), llm, SET)
    assert r.source == "exaone" and len(r.tasks) == 1
    assert r.tasks[0].evidence == "첨부 양식에 팀별 실적을 작성하신 뒤 엑셀 파일로 수요일까지 회신 부탁드립니다."


def test_meeting_attend_does_not_take_other_request():
    # dev2 M-0027: 회의 초대 속 다른 부탁('요약본 훑어봐 주세요')을 회의 참석 근거로 칠하지 않는다. 회의를 여는 문장 + 일시 줄
    body = "제안 준비를 위해 팀 킥오프 회의를 엽니다.\n일시: 11/3(화) 14:00~15:00\n장소: 11층 소회의실\n요약본 첨부드리니 미리 한번 훑어봐 주세요." + SIGN
    t = TaskOut(text="제안 킥오프 회의 참석", due_raw="11/3(화) 14:00~15:00")
    attach([t], req(body, subject="[회의] 제안 킥오프"))
    assert t.evidence == "제안 준비를 위해 팀 킥오프 회의를 엽니다.\n일시: 11/3(화) 14:00~15:00"


def test_subject_only_evidence_is_dropped():
    # 제목은 본문에서 칠할 데가 없다. 본문 문장을 쓰고, 닮은 문장이 없으면 None
    body = "주간 회의 일정을 안내드립니다." + SIGN
    t = TaskOut(text="1팀 주간 회의 참석", evidence="[회의] 1팀 주간 회의 (11/4 수)")
    attach([t], req(body, subject="[회의] 1팀 주간 회의 (11/4 수)"))
    assert t.evidence == "주간 회의 일정을 안내드립니다."
    t2 = TaskOut(text="장애 보고서 작성", evidence="[회의] 1팀 주간 회의 (11/4 수)")
    attach([t2], req(body))
    assert t2.evidence is None  # 닮은 문장이 없으면 칠하지 않는다(틀린 곳을 칠하지 않는 것이 먼저)


def test_no_body_no_evidence():
    # 본문 읽기 꺼짐: 본문이 비어 오면 근거도 없다
    t = TaskOut(text="자료 회신", evidence="자료를 회신해 주세요.")
    attach([t], req(""))
    assert t.evidence is None


def test_body_sentences_skip_greeting_and_signature():
    body = "안녕하세요 사업기획팀 박지영 팀장입니다.\n\n자료를 회신해 주세요. 수요일까지입니다." + SIGN
    assert body_sentences(body) == ["자료를 회신해 주세요.", "수요일까지입니다."]


def test_short_sentence_inside_longer_one_is_not_added():
    # '확인 부탁드립니다.'만 있는 줄이 긴 요청 문장 안에 글자로 들어 있어도 근거로 붙이지 않는다(#37에서 고친 경우, 여기서는 닮은 문장 하나만 고른다)
    body = "확인 부탁드립니다.\n보고서를 수정해서 금요일까지 다시 보내 주시기 바랍니다. 자료 확인 부탁드립니다." + SIGN
    t = TaskOut(text="보고서 수정해서 다시 보내기")
    attach([t], req(body))
    assert t.evidence == "보고서를 수정해서 금요일까지 다시 보내 주시기 바랍니다."


# 11/20 dev9 실제 메일 시험: 근거가 비었거나(영문) 나를 지목하지 않은 문장(안건 · 본문 주제)을 골랐다 → 모델 인용(classify_v8.2 evidence)
MINUTES = ("주간회의 회의록입니다.\n"
           "11/26(목) 14:00 운영위원회에서 사업단 보고는 진행 현황 → 품질 대응 → 인력 순서로 진행.\n"
           "| 8 | 운영위원회 통합 자료 확정 · 고객사 송부 | PMO 임소희 | 11/24(화) |\n"
           "| 9 | 운영위원회 2단계 진행 현황 보고(10분) | 1팀 이준호 | 11/26(목) 14:00 |" + SIGN)


def test_model_quote_picks_my_table_row():
    # 예전: 할 일 문구와 닮은 안건 문장(나를 부르지 않음)을 골랐다. 모델이 옮긴 내 행을 쓴다
    t = TaskOut(text="운영위원회에서 2단계 진행 현황 10분 보고", due_raw="11/26(목) 14:00",
                evidence="| 9 | 운영위원회 2단계 진행 현황 보고(10분) | 1팀 이준호 | 11/26(목) 14:00 |")
    attach([t], req(MINUTES))
    assert t.evidence == "| 9 | 운영위원회 2단계 진행 현황 보고(10분) | 1팀 이준호 | 11/26(목) 14:00 |"


def test_without_quote_row_naming_me_wins():
    # 모델 인용이 없거나 본문에 없으면(바꿔 씀) 닮음으로 고르되, 내 이름이 든 행을 더 쳐 준다
    t = TaskOut(text="운영위원회에서 2단계 진행 현황 10분 보고", due_raw="11/26(목) 14:00", evidence="운영위원회 보고 담당은 이준호 팀장")
    attach([t], req(MINUTES))
    assert t.evidence.startswith("| 9 |")


def test_english_mail_evidence_is_filled():
    # 예전: 한글 bigram만 봐서 영문 문장은 닮음 0 → 근거 없음
    body = ("Thank you for the review sessions.\n"
            "Could you confirm which option works by EOD Thursday?\n"
            "We would also appreciate it if you could share the updated cutover runbook before our Friday sync at 10:00 AM KST." + SIGN)
    quoted = TaskOut(text="갱신 cutover runbook 공유", evidence="We would also appreciate it if you could share the updated cutover runbook "
                                                             "before our Friday sync at 10:00 AM KST.")
    unquoted = TaskOut(text="updated cutover runbook 엑셀 공유")  # 인용이 없어도 영문 낱말로 닮음을 잰다
    attach([quoted, unquoted], req(body))
    assert quoted.evidence == unquoted.evidence and quoted.evidence.startswith("We would also appreciate")


def test_soft_request_quote_is_the_ask_not_the_topic():
    # dev9 M-0020: '~가 궁금해요 · 시간 될 때 읽어 보고 생각 들려줘요' → 근거는 부탁 문장이다(본문 주제 문장이 아니라)
    body = ("넷 다 하기엔 사람이 모자랍니다. 특히 1안을 하면 1팀 인력 운용이 가능한지, 놓친 리스크는 없는지.\n"
            "급한 건 아니니 시간 될 때 한번 읽어 보고 생각 들려줘요." + SIGN)
    t = TaskOut(text="사업 방향 메모 읽고 의견 전달", evidence="급한 건 아니니 시간 될 때 한번 읽어 보고 생각 들려줘요.")
    attach([t], req(body))
    assert t.evidence == "급한 건 아니니 시간 될 때 한번 읽어 보고 생각 들려줘요."
