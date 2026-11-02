"""날짜 · 시각 표현 해석 (AI-5). 기준 시각(메일 받은 시각 또는 명령 시각)으로 환산한다.

규칙 (data/dummy/README.md 5절 '마감 해석 기준', 구조도 4절):
- 연도가 없으면 기준 연도, 기준보다 앞선 날짜면 다음 해
- 시각이 없으면 18:00. '오전(중)' · '점심 전' · '정오' 12:00, '오후' · '퇴근 전' · '중(으로)' 18:00, '즉시' 기준 + 1시간(정시)
- '다음 주 초' 다음 주 화요일, '이번 주 내' 이번 주 금요일
- 요일만 있으면 기준일 이후 가장 가까운 그 요일(오늘 제외)
- 'OO 전에'처럼 시각 없이 일의 시작 전을 뜻하면 09:00 `[제안]`
- 마감 표지 앞 네 어절에 시각만 있으면 일곱 어절까지 넓혀 날짜를 찾는다('수요일 오전 10시 내부 리뷰 전까지')
- 기한을 지어내지 않는다: 날짜 표현이 없으면 None
- 마감 표지 없이 일정을 제안하는 날짜('다음 주 화요일에 진행하려고 하는데')는 행사 날짜라 기한이 아니다
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

WEEKDAYS = "월화수목금토일"
DEFAULT_TIME = time(18, 0)

_WD = r"([월화수목금토일])요일"
_PAREN_WD = r"(?:\s*\([월화수목금토일]\))?"
_DATE_PATTERNS = [
    ("ymd", re.compile(r"(\d{4})\s*[년.\-/]\s*(\d{1,2})\s*[월.\-/]\s*(\d{1,2})\s*일?" + _PAREN_WD)),
    ("md", re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일" + _PAREN_WD)),
    ("md", re.compile(r"(?<![\d.:])(\d{1,2})/(\d{1,2})(?![\d/])" + _PAREN_WD)),
    ("rel", re.compile(r"오늘|금일|내일|명일|모레|글피")),
    ("next_week_start", re.compile(r"다음\s*주\s*초|차주\s*초")),
    ("this_week_end", re.compile(r"(?:이번\s*주|금주)\s*(?:내|중|안)|주중으로")),
    ("week_wd", re.compile(r"(이번\s*주|금주|다음\s*주|차주|다다음\s*주)\s*" + _WD)),
    ("wd", re.compile(_WD)),
    ("d", re.compile(r"(?<![\d/월])(?<!월\s)(\d{1,2})\s*일(?=\s*(?:까지|전|에|\(|$))")),
]
_TIME = re.compile(r"(오전|오후|아침|저녁|밤)?\s*(\d{1,2})\s*(?:시(?!간)\s*(?:(\d{1,2})\s*분|(반))?|:(\d{2}))")
# '10:00에서 15:00로 변경' → 바뀐 뒤 시각
_TIME_CHANGE = re.compile(r"(\d{1,2}(?::\d{2}|시))\s*에서\s*(\d{1,2}(?::\d{2}|시))\s*(?:으)?로")
_DEADLINE_MARK = re.compile(r"까지|전에|전까지|중으로|내로|이내")
# '~에 리뷰를 진행하려고 하는데' · '~ 미팅을 하고 싶은데' · '~에 진행할 예정' (날짜 뒤에 오는 일정 제안)
_EVENT_PROPOSAL = re.compile(r"(?:하|진행하|잡으|열)\s*려고|하고\s*싶|진행할\s*(?:예정|계획)|잡고\s*싶")
_REL_DAYS = {"오늘": 0, "금일": 0, "내일": 1, "명일": 1, "모레": 2, "글피": 3}


@dataclass
class DueParse:
    raw: str
    due_at: datetime


def _weekday_after(base: date, wd: int, strictly_after: bool = True) -> date:
    delta = (wd - base.weekday()) % 7
    if delta == 0 and strictly_after:
        delta = 7
    return base + timedelta(days=delta)


def _week_start(base: date) -> date:
    return base - timedelta(days=base.weekday())


def _fix_year(d: date, base: date, has_year: bool) -> date:
    if not has_year and d < base:
        try:
            return d.replace(year=d.year + 1)
        except ValueError:
            return d
    return d


def _resolve(kind: str, m: re.Match, base: date) -> date:
    if kind == "ymd":
        return date(int(m[1]), int(m[2]), int(m[3]))
    if kind == "md":
        return _fix_year(date(base.year, int(m[1]), int(m[2])), base, False)
    if kind == "rel":
        return base + timedelta(days=_REL_DAYS[m[0]])
    if kind == "next_week_start":
        return _week_start(base) + timedelta(days=8)  # 다음 주 화요일
    if kind == "this_week_end":
        return max(_week_start(base) + timedelta(days=4), base)
    if kind == "week_wd":
        offset = 2 if "다다음" in m[1] else 1 if ("다음" in m[1] or "차주" in m[1]) else 0
        return _week_start(base) + timedelta(days=7 * offset + WEEKDAYS.index(m[2]))
    if kind == "wd":
        return _weekday_after(base, WEEKDAYS.index(m[1]))
    d = date(base.year, base.month, int(m[1]))  # 'd': 이번 달 D일, 지났으면 다음 달
    return d if d >= base else date(base.year + (base.month == 12), base.month % 12 + 1, int(m[1]))


def _find_date(text: str, base: date) -> tuple[date, re.Match] | None:
    best = None
    for kind, pat in _DATE_PATTERNS:
        for m in pat.finditer(text):
            try:
                d = _resolve(kind, m, base)
            except ValueError:
                continue
            # 마감 표지에 가장 가까운(뒤에 끝나는) 표현, 끝이 같으면 긴 표현('다음 주 수요일' > '수요일')
            if best is None or (m.end(), len(m[0])) > (best[1].end(), len(best[1][0])):
                best = (d, m)
    return best


def _find_time(text: str) -> time | None:
    ch = _TIME_CHANGE.search(text)
    if ch:
        text = ch.group(2)
    for m in _TIME.finditer(text):
        h = int(m[2])
        mi = int(m[3] or m[5] or (30 if m[4] else 0))
        if h > 24 or mi > 59:
            continue
        ampm = m[1]
        if ampm in ("오후", "저녁", "밤") and h < 12:
            h += 12
        elif ampm is None and 1 <= h <= 7:  # '3시까지'는 업무 시간 기준 오후로 본다
            h += 12
        if h == 24:
            h = 23
        return time(h, mi)
    return None


def _vague_time(text: str) -> time | None:
    # 일의 시작 전이 가장 이르므로 먼저 본다 ('오전 미팅 전에' → 09:00)
    if re.search(r"(?:작업|업무|보고|미팅|회의|출근)\s*(?:시작\s*)?전(?:에|까지)?|(?:요일|일)\s*전에", text):
        return time(9, 0)
    if re.search(r"점심\s*(?:전|까지)|정오|오전\s*(?:중|까지|내)?", text) and not re.search(r"오전\s*\d", text):
        return time(12, 0)
    if re.search(r"퇴근\s*전|오후\s*(?:중|까지|내)?|중(?:으로)?|EOD", text) and not re.search(r"오후\s*\d", text):
        return DEFAULT_TIME
    return None


def parse_due(text: str, base: datetime) -> DueParse | None:
    """문장에서 기한을 찾아 datetime으로 환산한다. 없으면 None (기한을 만들지 않는다)."""
    if not text:
        return None
    if re.search(r"즉시|지금\s*바로|ASAP|asap", text):
        at = (base + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        return DueParse("즉시", at)
    # 마감 표지('까지' · '전에' · '중으로' · '내로') 바로 앞 표현을 먼저 본다.
    # '목요일 회의에 올릴 안건을 내일 오전까지 회신' → 목요일이 아니라 내일 오전
    for mk in reversed(list(_DEADLINE_MARK.finditer(text))):  # 요청 동사에 가까운 마지막 표지
        window = " ".join(text[: mk.start()].split()[-4:]) + mk[0]  # 표지 앞 네 어절
        hit = parse_due_plain(window, base)
        if hit is not None and _find_date(window, base.date()) is None:
            # 시각만 잡혔으면 날짜가 조금 앞에 있을 수 있다('수요일 오전 10시 내부 리뷰 전까지' · '내일 오후 2시 고객 공유 전까지')
            wide = " ".join(text[: mk.start()].split()[-7:]) + mk[0]
            if _find_date(wide, base.date()) is not None:
                hit = parse_due_plain(wide, base) or hit
        if hit is not None:
            return hit
    ev = _EVENT_PROPOSAL.search(text)
    if ev:  # 제안 앞의 날짜는 행사 날짜다. 제안 뒤('..하고 싶은데, 내일 회신 주세요')에서만 기한을 찾는다
        return parse_due_plain(text[ev.end():], base)
    return parse_due_plain(text, base)


def parse_due_plain(text: str, base: datetime) -> DueParse | None:
    found = _find_date(text, base.date())
    if found is None:
        # 날짜 없이 '점심 전에' · '퇴근 전'처럼 오늘 안의 시각만 있는 경우
        t = _find_time(text) if re.search(r"까지|전에|전까지", text) else None
        t = t or (_vague_time(text) if re.search(r"점심|정오|퇴근|오늘|금일", text) else None)
        if t is None:
            return None
        return DueParse(text.strip(), datetime.combine(base.date(), t))
    d, m = found
    tail = text[m.start():]
    t = _find_time(tail) or _vague_time(tail) or DEFAULT_TIME
    return DueParse(tail[: max(len(m[0]), 1) + 12].strip(), datetime.combine(d, t))


def parse_date_range(text: str, base: datetime) -> tuple[date, date] | None:
    """명령용 기간 표현: '이번 주' · '다음 주' · '오늘' · '내일' → (시작일, 끝일)."""
    b = base.date()
    ws = _week_start(b)
    if re.search(r"다음\s*주|차주", text):
        return ws + timedelta(days=7), ws + timedelta(days=13)
    if re.search(r"이번\s*주|금주", text):
        return ws, ws + timedelta(days=6)
    if "오늘" in text:
        return b, b
    if "내일" in text:
        return b + timedelta(days=1), b + timedelta(days=1)
    if re.search(r"이번\s*달|이달", text):
        nxt = date(b.year + (b.month == 12), b.month % 12 + 1, 1)
        return date(b.year, b.month, 1), nxt - timedelta(days=1)
    return None
