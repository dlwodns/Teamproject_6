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
