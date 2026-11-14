from datetime import datetime

import pytest

from app.pipeline.dates import parse_date_range, parse_due

MON = datetime(2026, 11, 2, 9, 0)  # 월요일


@pytest.mark.parametrize("text, expected", [
    ("수요일까지 보내 주세요", "2026-11-04 18:00"),
    ("다음 주 수요일까지", "2026-11-11 18:00"),
    ("이번 주 금요일까지", "2026-11-06 18:00"),
    ("이번 주 내로 회신", "2026-11-06 18:00"),
    ("다음 주 초까지", "2026-11-10 18:00"),
    ("다음 주 중으로 주셔도 됩니다", "2026-11-13 18:00"),
    ("차주 내 회신", "2026-11-13 18:00"),
    ("내일 오전까지", "2026-11-03 12:00"),
    ("내일 오후 3시까지", "2026-11-03 15:00"),
    ("오늘 중으로", "2026-11-02 18:00"),
    ("점심 전에 부탁드립니다", "2026-11-02 12:00"),
    ("11/20(금)까지", "2026-11-20 18:00"),
    ("1월 5일까지", "2027-01-05 18:00"),  # 연도 없고 지난 날짜 → 다음 해
    ("10/30까지", "2027-10-30 18:00"),
    ("즉시 확인 부탁", "2026-11-02 10:00"),
    ("목요일 보고 전까지", "2026-11-05 09:00"),
    ("내일 아침 8시 30분 전에", "2026-11-03 08:30"),
])
def test_parse_due(text, expected):
    assert parse_due(text, MON).due_at.strftime("%Y-%m-%d %H:%M") == expected


def test_deadline_nearest_marker_wins():
    # 회의 날짜(목요일)가 아니라 마감 표지 앞의 '내일 오전'
    p = parse_due("목요일 회의에 올릴 안건을 내일 오전까지 회신 바랍니다", MON)
    assert p.due_at == datetime(2026, 11, 3, 12, 0)
    p = parse_due("고객이 내일 오전까지 원해서 오늘 중으로 받을 수 있을까요", MON)
    assert p.due_at == datetime(2026, 11, 2, 18, 0)


def test_no_deadline_is_not_invented():
    assert parse_due("자료 공유드립니다", MON) is None
    assert parse_due("소요 시간이 4시간 10분입니다", MON) is None


def test_time_change_takes_new_time():
    assert parse_due("11/4(수) 회의가 10:00에서 15:00로 변경", MON).due_at == datetime(2026, 11, 4, 15, 0)


def test_date_range():
    assert parse_date_range("이번 주 기한", MON) == (datetime(2026, 11, 2).date(), datetime(2026, 11, 8).date())
    assert parse_date_range("다음 주", MON)[0] == datetime(2026, 11, 9).date()
    assert parse_date_range("견적 건", MON) is None


@pytest.mark.parametrize("text, expected", [
    ("모레 정오까지 회신 바랍니다", "2026-11-04 12:00"),  # '정오' → 12:00
    ("목요일 14시 회의 전까지 정리", "2026-11-05 14:00"),  # 'N시 회의 전' → 그 시각
    ("내일 10시 미팅 전까지 보내주세요", "2026-11-03 10:00"),
    ("11시까지 확인 부탁", "2026-11-02 11:00"),  # 날짜 없이 시각만 → 오늘
    ("오후 2시 반까지", "2026-11-02 14:30"),
])
def test_parse_due_clock_time(text, expected):
    assert parse_due(text, MON).due_at.strftime("%Y-%m-%d %H:%M") == expected


def test_proposed_event_date_is_not_deadline():
    # 일정을 제안하는 날짜는 행사 날짜다. 응답 기한을 지어내지 않는다
    assert parse_due("다음 주 수요일에 워크숍을 진행하려고 하는데 참석 가능 여부 회신 부탁드립니다", MON) is None
    assert parse_due("금요일 오후에 점검 회의를 잡고 싶은데 가능한 시간 알려주세요", MON) is None
    # 제안 뒤에 따로 적은 기한은 그대로 본다
    p = parse_due("다음 주 월요일 교육을 진행할 예정이라 목요일까지 명단 회신 부탁드립니다", MON)
    assert p.due_at == datetime(2026, 11, 5, 18, 0)


def test_date_a_few_words_before_time_and_mark():
    # 마감 표지 앞 네 어절에 시각만 있으면 날짜를 조금 더 앞에서 찾는다(MON = 11/2 월)
    assert parse_due("목요일 오후 4시 주간 점검 전까지 정리 부탁드립니다", MON).due_at == datetime(2026, 11, 5, 16, 0)
    assert parse_due("모레 오전 11시 고객 보고 전까지 보내주세요", MON).due_at == datetime(2026, 11, 4, 11, 0)
    assert parse_due("오후 3시 회의 전까지 보내주세요", MON).due_at == datetime(2026, 11, 2, 15, 0)  # 날짜가 없으면 오늘
