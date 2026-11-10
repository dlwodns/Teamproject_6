"""AI-20 · D50: 일정 시각이 메일에 적혀 있었나(보정 전 원래 값) · 끝 시각. 캘린더 자동 등록 조건이다."""
from datetime import datetime

import pytest

from app.pipeline.dates import parse_deadline, parse_due_plain, parse_event_at, parse_event_end
from tests.test_classify import mail, run, task

BASE = datetime(2026, 11, 10, 9, 0)  # 화요일


@pytest.mark.parametrize("text, at, stated", [
    ("11/12(목) 14:00 회의", "2026-11-12 14:00", True),
    ("11/12(목) 오후 2시 반 회의", "2026-11-12 14:30", True),
    ("내일 10시 점검", "2026-11-11 10:00", True),
    ("11/12(목) 회의", "2026-11-12 18:00", False),  # 날짜만 → 18:00은 보정값
    ("내일 오전 회의", "2026-11-11 12:00", False),  # '오전'은 때일 뿐 시각이 아니다
    ("다음 주 초 회의", "2026-11-17 18:00", False),
])
def test_time_stated_is_raw_not_default(text, at, stated):
    p = parse_due_plain(text, BASE)
    assert p.due_at.strftime("%Y-%m-%d %H:%M") == at and p.time_stated is stated


@pytest.mark.parametrize("text, stated", [
    ("내일 오후 3시까지 보내 주세요", True),
    ("금요일까지 보내 주세요", False),
    ("오전 중에 알려 주세요", False),
    ("3시까지 회신 부탁드립니다", True),
])
def test_deadline_time_stated(text, stated):
    assert parse_deadline(text, BASE).time_stated is stated


def test_asap_has_no_stated_time():
    p = parse_deadline("최대한 빨리 회신 부탁드립니다", BASE)
    assert p.due_at is None and p.time_stated is False


@pytest.mark.parametrize("text, end", [
    ("11/12(목) 14:00~15:30 회의실 A", "15:30"),
    ("11/12(목) 오후 2시 - 4시", "16:00"),
    ("11/12(목) 10시부터 12시까지", "12:00"),
    ("11/12(목) 11시~1시", "13:00"),  # 정오를 넘는 범위
    ("11/12(목) 14:00 회의", None),  # 끝 시각을 지어내지 않는다(1시간은 backend 기본값)
])
def test_event_end(text, end):
    start = parse_due_plain(text, BASE).due_at
    got = parse_event_end(text, start)
    assert (got.strftime("%H:%M") if got else None) == end


def test_event_end_must_start_at_same_time():
    # 다른 일정의 범위('점심 12:00~13:00')를 끝 시각으로 쓰지 않는다
    assert parse_event_end("14:00 회의, 점심 12:00~13:00", datetime(2026, 11, 12, 14, 0)) is None


def test_classify_meeting_with_time_and_range():
    r, _ = run(mail("일시: 11/4(수) 14:00~15:30\n장소: 3층 회의실\n주간 점검 회의에 참석 부탁드립니다."), "요청",
               task("일정참석", "주간 점검 회의 참석"))
    t = r.tasks[0]
    assert t.due_at.isoformat() == "2026-11-04T14:00:00" and t.due_time_stated is True
    assert t.end_at.isoformat() == "2026-11-04T15:30:00"


def test_classify_meeting_date_only_is_not_stated():
    # 날짜만 있는 회의: 18:00으로 채우지만 시각이 적힌 것은 아니다 → backend는 자동 등록하지 않고 카드로 넘긴다
    r, _ = run(mail("11/5(목)에 분기 리뷰 회의를 엽니다. 참석 부탁드립니다."), "요청",
               task("일정참석", "분기 리뷰 회의 참석", "11/5(목)"))
    t = r.tasks[0]
    assert t.due_at is not None and t.due_at.hour == 18
    assert t.due_time_stated is False and t.end_at is None


def test_classify_deadline_task_has_flag_but_no_end():
    r, _ = run(mail("실적 표를 내일 오후 3시까지 보내 주세요."), "요청", task("자료제출요청", "실적 표 제출", "내일 오후 3시까지"))
    t = r.tasks[0]
    assert t.due_time_stated is True and t.end_at is None  # 끝 시각은 일정참석만


def test_classify_without_due():
    r, _ = run(mail("자료 검토 부탁드립니다."), "요청", task("검토승인요청", "자료 검토"))
    assert r.tasks[0].due_at is None and r.tasks[0].due_time_stated is False


def test_response_json_has_fields():
    r, _ = run(mail("일시: 11/4(수) 14:00\n회의 참석 부탁드립니다."), "요청", task("일정참석", "회의 참석"))
    d = r.model_dump(mode="json")["tasks"][0]
    assert d["due_time_stated"] is True and d["end_at"] is None


# ── 엣지 케이스 (11/10 사용자 점검) ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text, at, stated", [
    # 1. 마감 표지가 붙은 시각은 회의 시각이 아니다
    ("참석 여부는 11/12(목) 18:00까지 회신", "2026-11-12 18:00", False),
    ("11/12(목) 회의, 자료는 15시 전에 공유", "2026-11-12 18:00", False),
    ("11/12(목) 회의 17시 마감", "2026-11-12 18:00", False),
    ("11/12(목) 14:00 회의, 참석 여부 17시까지", "2026-11-12 14:00", True),  # 회의 시각은 그대로, 뒤 마감 시각은 무시
    ("11/12(목) 10:00에서 14:00로 변경된 회의", "2026-11-12 14:00", True),  # 바뀐 뒤 시각
])
def test_event_time_skips_deadline_time(text, at, stated):
    p = parse_event_at(text, BASE)
    assert p.due_at.strftime("%Y-%m-%d %H:%M") == at and p.time_stated is stated


def test_classify_meeting_rsvp_deadline_is_not_meeting_time():
    # 1. '참석 여부를 18:00까지 회신'의 18:00은 기한이다. 회의 할 일에는 시각이 적힌 것으로 보지 않는다(자동 등록 안 함)
    body = "주간 회의 참석 여부를 11/12(목) 18:00까지 회신 부탁드립니다."
    r, _ = run(mail(body), "요청", task("일정참석", "주간 회의 참석", "11/12(목) 18:00까지"),
               task("회신요청", "참석 여부 회신", "11/12(목) 18:00까지"))
    meet, reply = r.tasks
    assert meet.type == "일정참석" and meet.due_time_stated is False and meet.end_at is None
    # 같은 글자라도 회신 기한으로는 시각이 적혀 있다(true). 자동 등록은 일정참석만 보므로 기한이 캘린더에 들어가지 않는다
    assert reply.type == "회신요청" and reply.due_at.isoformat() == "2026-11-12T18:00:00" and reply.due_time_stated is True


@pytest.mark.parametrize("text, start, end", [
    # 2. 자정을 넘는 끝 시각은 다음 날
    ("11/12 23:30~00:30 야간 점검", "2026-11-12 23:30", "2026-11-13 00:30"),
    ("11/12 밤 11시~1시 작업", "2026-11-12 23:00", "2026-11-13 01:00"),
    ("11/12 22:00~24:00 배포", "2026-11-12 22:00", "2026-11-13 00:00"),
    ("11/12 오후 11시 - 새벽 2시 점검", "2026-11-12 23:00", "2026-11-13 02:00"),
    ("11/12 10:00~9:00", "2026-11-12 10:00", None),  # 콜론 시각은 24시간제 → 23시간 범위는 버린다
    ("11/12 9시~10시", "2026-11-12 09:00", "2026-11-12 10:00"),
])
def test_event_end_crosses_midnight(text, start, end):
    s = parse_event_at(text, BASE).due_at
    got = parse_event_end(text, s)
    assert s.strftime("%Y-%m-%d %H:%M") == start and (got.strftime("%Y-%m-%d %H:%M") if got else None) == end


def test_classify_overnight_meeting_end_is_next_day():
    r, _ = run(mail("일시: 11/4(수) 23:30~00:30\n야간 배포 점검에 참석 부탁드립니다."), "요청", task("일정참석", "야간 배포 점검 참석"))
    t = r.tasks[0]
    assert t.due_at.isoformat() == "2026-11-04T23:30:00" and t.end_at.isoformat() == "2026-11-05T00:30:00"


@pytest.mark.parametrize("text", ["3일 뒤 오후 2시", "다음 주에 2시", "주말에 10시", "2주 후 3시"])
def test_relative_when_is_not_today(text):
    # 4. 날짜로 못 읽는 상대 시점은 오늘로 두지 않는다(명령은 되묻는다)
    assert parse_event_at(text, BASE, roll_forward=True) is None


def test_mail_time_without_date_makes_no_event():
    # 메일 분류는 날짜 없는 시각으로 일정을 만들지 않는다(이전 동작과 같다). 명령만 오늘 · 내일로 굴린다
    assert parse_event_at("14시 회의", BASE) is None
    assert parse_event_at("14시 회의", BASE, roll_forward=True).due_at == datetime(2026, 11, 10, 14, 0)
