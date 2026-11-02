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
