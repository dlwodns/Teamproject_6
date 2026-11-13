"""오늘 요약 v3(AI-D18): 코드가 세고 묶고, 모델은 문장만 — 모델 문장은 코드가 센 사실과 대조한다.
자료는 시연 시드(dummy_mails.json, 시각 B 2026-10-20 09:00)의 오늘까지 기한 18건 그대로다(11/13 실측 입력)."""
from datetime import datetime

from app.agent.assist import check_briefing, code_briefing, model_input, summarize, today_facts
from app.schemas.assist import SummarizeRequest, SummaryItem

NOW = datetime(2026, 10, 20, 9, 0)
ROWS = [  # (보낸 사람, 상급자, 업무, 기한)
    ("장민호 차장", False, "2단계 전환 대상 시스템 목록과 이관 일정 초안 공유", "2026-10-19T18:00"),
    ("정태성 담당", True, "2단계 일정 리스크 현황과 대응 방안 보고", "2026-10-19T18:00"),
    ("최유진 선임", False, "아키텍처 다이어그램을 수정 가능한 원본 파일로 재전송", "2026-10-19T18:00"),
    ("한상우 사업단장", True, "장애 고객 대응 현황 공유", "2026-10-20T08:30"),
    ("강도윤 책임", False, "고객 보고 장표의 리허설 소요 시간 수정 후 재전송", "2026-10-19T12:00"),
    ("배수민 책임", False, "이관 결과 보고서 외부 반출 승인", "2026-10-19T15:00"),
    ("임소희 책임", False, "팀 주간보고를 양식에 작성해 회신", "2026-10-19T17:00"),
    ("백승현 과장", False, "킥오프 미팅 참석자 명단 회신", "2026-10-19T18:00"),
    ("강도윤 책임", False, "장애 경위서 초안 작성 담당 회신", "2026-10-19T18:00"),
    ("정태성 담당", True, "팀별 4분기 수주 전망 PPT 1장 작성", "2026-10-20T10:00"),
    ("백승현 과장", False, "누리물류 킥오프 미팅 참석(장소 변경)", "2026-10-20T10:00"),
    ("한상우 사업단장", True, "목요일 사업단 회의 안건 회신", "2026-10-20T12:00"),
    ("김민석 팀장", False, "1팀-2팀 이관 일정 조율 회의 참석", "2026-10-20T14:00"),
    ("장민호 차장", False, "개발계 접속 장애 경위서 제출", "2026-10-20T15:00"),
    ("김민석 팀장", False, "1팀-2팀 이관 일정 조율 회의 참석(변경)", "2026-10-20T16:00"),
    ("장민호 차장", False, "2단계 전환 대상 시스템 목록과 이관 일정 초안 공유", "2026-10-20T18:00"),
    ("임소희 책임", False, "월간 보고회 팀 발표자 지정 회신", "2026-10-20T18:00"),
    ("강도윤 책임", False, "이관 결과 보고서 요약 표 엑셀 원본 재전송", "2026-10-20T18:00"),
]
ITEMS = [SummaryItem(task_id=n, text=t, sender=w, is_superior=sup, due_at=datetime.fromisoformat(d), priority="P2")
         for n, (w, sup, t, d) in enumerate(ROWS, 1)]
# 기한이 먼 업무 · 나중에 · 기한 없음은 숫자 줄에만 들어가고 문장에는 나오지 않는다
ITEMS += [SummaryItem(task_id=90, text="11월 교육 신청", sender="오지훈 책임", due_at=datetime(2026, 10, 24, 18, 0)),
          SummaryItem(task_id=91, text="견적 재확인", sender="오지훈 책임", status="snoozed"),
          SummaryItem(task_id=92, text="자료 검토", sender="오지훈 책임")]
REQ = SummarizeRequest(mode="today", now=NOW, items=ITEMS)

# 11/13 K-EXAONE 2.5(중간 강도)가 같은 사실로 쓴 문장(v5 실측). 사람이 하나하나 대조해 모두 맞았다 → 통과해야 한다
MODEL_OK = ("기한 지남 중 상급자 발송은 정태성 담당의 '2단계 일정 리스크 현황·대응 보고', 한상우 사업단장의 '장애 고객 대응 현황 공유'이고, "
            "그 밖에 7건은 장민호 차장·최유진 선임·강도윤 책임 2건·배수민 책임·임소희 책임·백승현 과장입니다. "
            "오늘은 10:00 백승현 과장 누리물류 킥오프 미팅 참석(장소 변경), 14:00·16:00 김민석 팀장 이관 일정 조율 회의 참석(16:00 변경)이 일정이고, "
            "나머지 마감은 정태성 담당 1건, 한상우 사업단장 1건, 장민호 차장 2건, 임소희 책임 1건, 강도윤 책임 1건입니다. "
            "같은 업무가 두 번 보이는 건 장민호 차장의 2단계 전환 목록·이관 일정 초안 공유와 김민석 팀장의 이관 일정 조율 회의이며, "
            "장민호 차장·강도윤 책임은 각각 3건입니다.")


def test_facts_group_like_a_person_would():
    f = today_facts(REQ)
    assert f.counts.model_dump() == {"pending": 20, "due_today": 18, "overdue": 9, "awaiting_reply": 0}
    assert [i.text for i in f.overdue_superior] == ["2단계 일정 리스크 현황과 대응 방안 보고", "장애 고객 대응 현황 공유"]
    assert sum(n for _, n in f.overdue_other) == 7 and ("강도윤 책임", 2) in f.overdue_other
    assert [(f"{i.due_at:%H:%M}", i.sender) for i in f.today_events] == [
        ("10:00", "백승현 과장"), ("14:00", "김민석 팀장"), ("16:00", "김민석 팀장")]
    assert dict(f.today_other) == {"정태성 담당": 1, "한상우 사업단장": 1, "장민호 차장": 2, "임소희 책임": 1, "강도윤 책임": 1}
    assert f.heavy == [("강도윤 책임", 3), ("장민호 차장", 3)]
    assert len(f.listed) == 18 and all("오지훈" not in (i.sender or "") for i in f.listed)


def test_code_briefing_is_three_sentences_without_advice():
    text = code_briefing(today_facts(REQ))
    assert text.startswith("기한이 지난 업무 가운데 상급자가 보낸 건은 정태성 담당의 '2단계 일정 리스크 현황과 대응 방안 보고', "
                           "한상우 사업단장의 '장애 고객 대응 현황 공유'이고, 그 밖에 7건이 있습니다.")
    assert "오늘은 10:00 백승현 과장 '누리물류 킥오프 미팅 참석(장소 변경)'" in text and "그 밖 마감이 6건 있습니다." in text
    assert text.endswith("강도윤 책임에게 3건, 장민호 차장에게 3건이 걸려 있습니다.")  # 같은 건수면 기한이 이른 업무의 사람부터
    assert check_briefing(text, today_facts(REQ), model_input(today_facts(REQ))) is None  # 코드 문장도 같은 검사를 통과한다


def test_model_input_has_sections_named_in_prompt():
    src = model_input(today_facts(REQ))
    for section in ("[기한 지남 · 상급자]", "[기한 지남 · 그 밖] 7건", "[오늘 · 일정]", "[오늘 · 그 밖 마감] 6건",
                    "[3건 이상인 사람] 강도윤 책임 3건, 장민호 차장 3건", "[전체 업무 목록]"):
        assert section in src
    assert "배수민" not in src.split("[전체 업무 목록]")[0]  # '그 밖'은 사람별로 넘기지 않는다(길어지지 않게)
    assert "- 강도윤 책임 · 이관 결과 보고서 요약 표 엑셀 원본 재전송 · 10/20 18:00" in src


def test_real_model_sentence_passes_check():
    f = today_facts(REQ)
    assert check_briefing(MODEL_OK, f, model_input(f)) is None


def test_check_rejects_advice_invented_numbers_and_people():
    f = today_facts(REQ)
    src = model_input(f)
    assert check_briefing("가장 먼저 장애 고객 대응 현황 공유를 처리해 주세요.", f, src).startswith("권유 표현")
    assert check_briefing("오늘 마감은 강도윤 책임 1건, 일정은 11:00입니다.", f, src) == "입력에 없는 숫자(11)"
    assert check_briefing("기한이 지난 업무는 그 밖에 15건입니다.", f, src) == "맞지 않는 건수(15)"  # 15는 15:00으로 입력에 있지만 건수가 아니다
    assert check_briefing("박지성 부장에게 1건이 있습니다.", f, src) == "입력에 없는 사람(박지성 부장)"
    assert check_briefing("", f, src) == "빈 문장"


def test_model_sentence_is_used_or_replaced(fake_llm):
    fake_llm.replies = [MODEL_OK, "먼저 정태성 담당 건을 처리하는 게 좋겠습니다."]
    r = summarize(REQ, fake_llm)
    assert r.source == "exaone" and r.text == MODEL_OK and r.counts.overdue == 9
    r = summarize(REQ, fake_llm)
    assert r.source == "code" and r.fallback.startswith("검증 실패: 권유 표현") and r.text.startswith("기한이 지난 업무 가운데")


def test_no_due_today_does_not_call_model(fake_llm):
    req = SummarizeRequest(mode="today", now=NOW, items=ITEMS[-3:])
    r = summarize(req, fake_llm)
    assert fake_llm.calls == [] and r.text == "오늘까지 기한인 업무는 없습니다." and r.counts.pending == 2


def test_event_flag_overrides_keywords():
    items = [SummaryItem(task_id=1, text="고객사 방문", sender="김민석 팀장", due_at=datetime(2026, 10, 20, 15, 0), is_event=True),
             SummaryItem(task_id=2, text="회의록 정리", sender="김민석 팀장", due_at=datetime(2026, 10, 20, 17, 0), is_event=False)]
    f = today_facts(SummarizeRequest(mode="today", now=NOW, items=items))
    assert [i.text for i in f.today_events] == ["고객사 방문"] and f.today_other == [("김민석 팀장", 1)]
