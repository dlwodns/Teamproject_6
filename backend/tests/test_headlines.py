"""요약 · 회고 묶음(ai io_spec 3.2~3.4절)과 머리 문장 미리 만들기(AI-29, app/reminders/headlines.py)."""
from datetime import date, datetime, timedelta

import pytest

from app.ai_client.client import AIError
from app.models import BriefingHeadline, Contact, Task
from app.reminders import briefings, headlines
from app.schemas.ai import SummarizeResult
from tests.clock_util import move_to
from tests.test_reminders import _base, _mail, _task

FRI = datetime(2026, 11, 13, 17, 30)  # 금요일 회고 시각


@pytest.fixture(autouse=True)
def clock():
    move_to(FRI)
    yield
    move_to(None)


class FakeAI:
    def __init__(self, text="머리 문장입니다.", error: AIError | None = None):
        self.text, self.error, self.payloads = text, error, []

    def summarize(self, payload):
        self.payloads.append(payload)
        if self.error:
            raise self.error
        return SummarizeResult(text=self.text, source="exaone", prompt_version="assist_v4")


def _sections(b):
    return {s["id"]: s for s in b["sections"]}


def test_morning_splits_by_time_of_day(db):
    _base(db)
    for i, (h, stated) in enumerate(((10, True), (15, True), (18, False)), start=1):
        _mail(db, i)
        _task(db, i, i, due=datetime(2026, 11, 16, h, 0))
        db.get(Task, i).due_time_stated, db.get(Task, i).type = stated, "회신요청"
    db.commit()
    s = _sections(briefings.build(db, 1, "morning", date(2026, 11, 16), datetime(2026, 11, 16, 8, 30)))
    assert [x["task_id"] for x in s["due_today_am"]["items"]] == [1]
    assert [x["task_id"] for x in s["due_today_pm"]["items"]] == [2]
    assert [x["task_id"] for x in s["due_today_allday"]["items"]] == [3]  # 시각 없는 마감은 따로(오늘 중)
    assert s["due_today_am"]["items"][0]["title"] == "[회신요청] 견적 회신"
    assert s["due_today_am"]["items"][0]["reason"].startswith("10:00 · ")


def test_weekly_four_sections(db):
    _base(db)
    db.add(Contact(user_id=1, email="boss@cne.com", name="한상우", position="사업단장", is_superior=True))
    _mail(db, 1); _task(db, 1, 1, due=datetime(2026, 11, 10, 18), status="done")  # 기한 후 완료
    db.get(Task, 1).done_at = datetime(2026, 11, 11, 9)
    _mail(db, 2, sender="boss@cne.com"); _task(db, 2, 2, due=datetime(2026, 11, 12, 18))  # 넘어가는 일(기한 지남)
    _mail(db, 3); _task(db, 3, 3, due=datetime(2026, 11, 17, 10))  # 차주 화요일
    _mail(db, 4); _task(db, 4, 4, due=datetime(2026, 11, 23, 10))  # 다다음 주 — 빠진다
    db.commit()
    s = _sections(briefings.build(db, 1, "weekly", date(2026, 11, 13)))
    assert s["done_week"]["items"][0]["reason"].endswith("기한 후 완료")
    assert [x["task_id"] for x in s["carry_over"]["items"]] == [2] and "한상우 사업단장" in s["carry_over"]["items"][0]["reason"]
    assert [x["task_id"] for x in s["due_next_week"]["items"]] == [3]


def test_headline_made_once_masked_and_shown(db, monkeypatch):
    monkeypatch.setenv("PII_MASK", "1")
    _base(db)
    db.add(Contact(user_id=1, email="boss@cne.com", name="한상우", position="사업단장", is_superior=True))
    _mail(db, 1, sender="boss@cne.com"); _task(db, 1, 1, due=FRI + timedelta(days=4))
    db.commit()
    ai = FakeAI(text="다음 주 기한인 업무는 1건입니다.")
    assert headlines.due(db, 1, FRI) == ["evening", "weekly"]
    assert headlines.run(db, ai, FRI) == 2 and headlines.run(db, ai, FRI) == 0  # 한 번만
    weekly = next(p for p in ai.payloads if p["mode"] == "weekly")
    line = weekly["sections"][3]["items"][0]
    assert weekly["sections"][3]["id"] == "due_next_week" and line["is_superior"] is True
    assert "한상우" not in str(weekly) and line["sender"].startswith("한◯◯")  # 개인정보를 가려 보낸다(BE-6)
    b = briefings.build(db, 1, "weekly", date(2026, 11, 10))  # 그 주 어느 날로 열어도
    assert b["headline"] == "다음 주 기한인 업무는 1건입니다." and b["headline_at"] == FRI
    assert b["summary"].endswith("이 있습니다.")  # summary는 지금 건수 문장 그대로(머리 문장과 섞지 않는다)
    row = db.query(BriefingHeadline).filter_by(kind="weekly").one()
    assert (row.day, row.source, row.prompt_version) == (date(2026, 11, 13), "exaone", "assist_v4")


def test_headline_ai_down_retries_and_window(db):
    _base(db)
    _mail(db, 1); _task(db, 1, 1, due=FRI - timedelta(hours=1))
    db.commit()
    assert headlines.run(db, FakeAI(error=AIError("unavailable", "x")), FRI) == 0
    assert db.query(BriefingHeadline).count() == 0  # 저장하지 않고 다음 틱에 다시
    assert headlines.due(db, 1, FRI + timedelta(hours=1)) == []  # 1시간이 지나면 만들지 않는다
    assert briefings.build(db, 1, "evening", FRI.date())["headline"] is None


def test_morning_payload_is_today_mode(db):
    _base(db)
    _mail(db, 1); _task(db, 1, 1, due=datetime(2026, 11, 16, 9))
    db.get(Task, 1).type = "일정참석"
    db.commit()
    b = briefings.build(db, 1, "morning", date(2026, 11, 16), datetime(2026, 11, 16, 8, 30))
    p = headlines.payload(db, 1, b)
    assert p["mode"] == "today" and p["items"][0]["is_event"] is True and p["items"][0]["status"] == "pending"


def test_review_fixes(db, monkeypatch):
    """#리뷰: 미룬 다음 주 업무 두 번 세지 않음 · 연락처 없는 주소는 통째로 가림 · 코드 문장은 20분 뒤 다시 · 부재 중엔 만들지 않음."""
    monkeypatch.setenv("PII_MASK", "1")
    _base(db)
    _mail(db, 1, sender="gildong.hong@ext.com"); _task(db, 1, 1, due=datetime(2026, 11, 17, 10), status="snoozed", until=datetime(2026, 11, 16, 9))
    db.get(Task, 1).status_changed_at = datetime(2026, 11, 11, 9)
    db.commit()
    s = _sections(briefings.build(db, 1, "weekly", date(2026, 11, 13)))
    assert s["carry_over"]["count"] == 1 and s["due_next_week"]["count"] == 0
    code = FakeAI()
    code.summarize = lambda p: (code.payloads.append(p), SummarizeResult(text="코드 문장", source="code", fallback="한도"))[1]
    assert headlines.make(db, 1, "weekly", FRI.date(), code, FRI) is not None
    assert "gildong.hong" not in str(code.payloads[0])  # 주소 앞부분도 밖으로 나가지 않는다
    ai = FakeAI(text="모델 문장입니다.")
    assert headlines.make(db, 1, "weekly", FRI.date(), ai, FRI + timedelta(minutes=5)) is None and not ai.payloads
    assert headlines.make(db, 1, "weekly", FRI.date(), code, FRI + timedelta(minutes=21)) is not None  # 또 코드 문장 → 시각 갱신
    n = len(code.payloads)
    assert headlines.make(db, 1, "weekly", FRI.date(), code, FRI + timedelta(minutes=22)) is None and len(code.payloads) == n
    assert headlines.make(db, 1, "weekly", FRI.date(), ai, FRI + timedelta(minutes=45)).text == "모델 문장입니다."
    assert db.query(BriefingHeadline).count() == 1
    from app.models import UserSettings
    db.get(UserSettings, 1).away_until = FRI + timedelta(days=1)
    db.commit()
    assert headlines.due(db, 1, FRI) == []
