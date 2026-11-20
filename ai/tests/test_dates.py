from datetime import datetime

import pytest

from app.pipeline.dates import parse_date_range, parse_deadline, parse_due

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


# 11/20 dev9 실제 메일 시험(받은 날 목요일 밤)에서 틀리거나 비었던 기한. 상대 표현 계산표(dates.py 머리말)와 같은 규칙
THU = datetime(2026, 11, 19, 23, 53)  # 목요일


@pytest.mark.parametrize("text, expected", [
    ("차주 화요일까지 회신 부탁드립니다", "2026-11-24 18:00"),  # 다음 주(월~일)의 화요일 = 5일 뒤
    ("다음 주 화요일까지", "2026-11-24 18:00"),
    ("가능한 일자를 익일 오전까지 회신 주시면", "2026-11-20 12:00"),  # '익일'을 못 읽어 오늘 12:00이 됐다
    ("명일 중으로 보내 주세요", "2026-11-20 18:00"),
    ("오늘 중 결재 부탁드립니다", "2026-11-19 18:00"),
    ("금주 중 회신", "2026-11-20 18:00"),
    ("주말 전까지 보내 주세요", "2026-11-20 18:00"),  # 이번 주 금요일
    ("내일 아침까지 보내 주세요", "2026-11-20 09:00"),  # 아침 = 09:00(예전 18:00)
    ("목요일까지 보내 주세요", "2026-11-26 18:00"),  # 요일만이면 오늘 제외 가장 가까운 그 요일
    # 회의 시각과 제출 기한이 한 문장에: 제출 기한은 '까지'가 붙은 쪽
    ("11/20(금) 09:30 회의 전에 분석 자료를 오늘 18시까지 보내 주십시오", "2026-11-19 18:00"),
    # 고를 날짜 목록의 '중'은 기한이 아니다 → 뒤의 '익일 오전까지'(예전 12/6)
    ("11/29 · 12/6 중 가능한 일자를 익일 오전까지 회신", "2026-11-20 12:00"),
    # 영문 기한(예전 None): 표지 뒤에 날짜 · 시각
    ("could you confirm which option works (or let us know if neither does) by EOD Thursday?", "2026-11-19 18:00"),  # 11-20 결정: 목요일에 받은 EOD Thursday는 그날,
    ("share the updated runbook before our Friday sync at 10:00 AM KST.", "2026-11-20 10:00"),
    ("please send it by Nov 24 6pm", "2026-11-24 18:00"),
    ("by tomorrow morning", "2026-11-20 12:00"),
    ("no later than next Tuesday", "2026-11-24 18:00"),
    ("by 3 PM", "2026-11-19 15:00"),
])
def test_parse_deadline_relative_table(text, expected):
    assert parse_deadline(text, THU).due_at.strftime("%Y-%m-%d %H:%M") == expected


def test_choice_dates_and_unknown_event_are_not_invented():
    assert parse_deadline("11/29(토) 또는 12/6(토) 중 하루를 골라 회신 부탁드립니다", THU) is None
    p = parse_deadline("please share it before the Friday sync", THU)  # 회의 시각을 모른다 → 시각을 비운다
    assert p is not None and p.due_at is None


def test_eod_weekday_same_day_is_today_not_next_week():
    # 11-20 사용자 결정: 목요일 밤에 받은 'by EOD Thursday'는 그날(지난 기한). 예전에는 다음 주 목요일로 갔다
    thu_night = datetime(2026, 11, 19, 21, 30)
    assert parse_deadline("by EOD Thursday", thu_night).due_at == datetime(2026, 11, 19, 18, 0)
    # 금요일에 받은 'EOD Thursday'는 다음 주 목요일
    assert parse_deadline("by EOD Thursday", datetime(2026, 11, 20, 9, 0)).due_at == datetime(2026, 11, 26, 18, 0)
    # EOD가 없는 요일만은 그대로(오늘 제외)
    assert parse_deadline("목요일까지", thu_night).due_at == datetime(2026, 11, 26, 18, 0)
