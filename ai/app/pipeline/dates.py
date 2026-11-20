"""날짜 · 시각 표현 해석 (AI-5). 기준 시각(메일 받은 시각 또는 명령 시각)으로 환산한다.

규칙 (data/dummy/README.md 5절 '마감 해석 기준', 구조도 4절):
- 연도가 없으면 기준 연도, 기준보다 앞선 날짜면 다음 해
- 시각이 없으면 18:00. '오전(중)' · '점심 전' · '정오' 12:00, '오후' · '퇴근 전' · '중(으로)' 18:00, '즉시' 기준 + 1시간(정시)
- '다음 주 초' 다음 주 화요일, '이번 주 내' 이번 주 금요일, '다음 주 중 · 차주 내' 다음 주 금요일(#83 검수)
- 요일만 있으면 기준일 이후 가장 가까운 그 요일(오늘 제외)
- 'OO 전에'처럼 시각 없이 일의 시작 전을 뜻하면 09:00 `[제안]`
- 마감 표지 앞 네 어절에 시각만 있으면 일곱 어절까지 넓혀 날짜를 찾는다('수요일 오전 10시 내부 리뷰 전까지')
- 기한을 지어내지 않는다: 날짜 표현이 없으면 None

상대 표현 계산표(11/20, dev9 실제 메일 시험 뒤 정리. 모델은 기한 글자만 옮기고 계산은 이 표로만 한다 — 프롬프트에 표를 넣으면 날짜 많은 메일에서 추론이 2배로 늘었다). 기준일 = 받은 날, 주는 월~일:
| 표현 | 날짜 | 시각(글자가 없을 때) |
| 오늘 · 금일 · 오늘 중 · today | 기준일 | 18:00 |
| 내일 · 익일 · 명일 · tomorrow | 기준일 + 1 | 18:00 |
| 모레 · 글피 | + 2 · + 3 | 18:00 |
| 요일만(화요일 · Tuesday) | 기준일 다음 날부터 가장 가까운 그 요일(오늘 제외) | 18:00 |
| EOD · COB + 요일('EOD Thursday') | 받은 날이 그 요일이면 그날(밤에 받으면 지난 기한), 아니면 가장 가까운 그 요일 | 18:00 |
| 이번 주 · 금주 · this + 요일 | 기준일이 든 주의 그 요일(지났어도 그 날) | 18:00 |
| 다음 주 · 차주 · next + 요일 | 다음 주(월~일)의 그 요일. 목요일에 받은 '차주 화요일'은 5일 뒤 | 18:00 |
| 다다음 주 + 요일 | 2주 뒤 주의 그 요일 | 18:00 |
| 이번 주 내 · 금주 중 · 주중으로 · 주말 전 · 주말까지 | 이번 주 금요일(이미 지났으면 기준일) | 18:00 |
| 다음 주 초 · 차주 초 | 다음 주 화요일 | 18:00 |
| 다음 주 중 · 차주 내 | 다음 주 금요일 | 18:00 |
| 11/24 · 11월 24일 · Nov 24 | 그 날(연도가 없고 지났으면 다음 해) | 18:00 |
시각: 오전 · 정오 · 점심 전 · morning · noon 12:00, 아침 · 업무 시작 전 09:00, 오후 · 퇴근 전 · EOD · COB 18:00,
'3시'처럼 오전 · 오후가 없는 1~7시는 오후, 'AM · PM'을 적었으면 그대로. 시각을 모르는 행사 앞('내일 고객 미팅 전')은 시각을 비운다.
고를 날짜가 여럿인 '중'('11/29 · 12/6 중 가능한 날')은 고를 대상이지 기한이 아니다.
영문 기한 표지: by · before · no later than · until · prior to · due — 날짜가 표지 뒤에 온다('by EOD Thursday',
'before our Friday sync at 10:00 AM' → 금요일 10:00).
- 마감 표지 없이 일정을 제안하는 날짜('다음 주 화요일에 진행하려고 하는데')는 행사 날짜라 기한이 아니다

메일 할 일의 기한은 `parse_deadline`(11/5, AI-18)으로만 읽는다. 메일 속 날짜는 역할이 넷이다:
- 기한: 마감 표지('까지 · 전에 · 중(으로) · 내로 · 이내', '마감을 ~로')가 붙은 날짜 → 기한
- 일정: 회의 · 행사 일시('일시:', '~에 회의를 엽니다') → 기한이 아니다. 회의 참석 할 일만 이 시각을 쓴다(event_due)
- 지난 일: '금요일에 보내드린' · '지난주 요청한' → 기한이 아니다
- 그 밖의 날짜: '10/27에 개인 사정이 있어' · '11/6 결정 예정' → 기한이 아니다
즉 마감 표지가 없는 날짜는 기한으로 쓰지 않는다. `parse_due`(표지 없으면 아무 날짜나 읽음)는 명령 해석(다시 알림 시각)용이다.
- 시각을 모르는 일의 '전'('내일 고객 미팅 전에')은 시각을 지어내지 않는다: 문구는 그대로 두고 due_at은 비운다(11/5 사용자 결정)

시각이 메일에 적혀 있었나(AI-20 · D50, 11/10): 위 기본 시각(18:00 · 12:00 · 09:00 · 즉시 + 1시간)은 보정값이다.
`DueParse.time_stated`는 '14시 · 14:00 · 오후 2시 반'처럼 시각 글자가 있어서 그 시각을 쓴 경우에만 True다.
캘린더 자동 등록은 이 값이 True인 일정만 넣는다(날짜만 있는 회의가 18:00으로 들어가지 않게).

일정 시각(`parse_event_at`, AI-20 · AI-D16): 회의 참석 할 일의 시각과 T15 명령의 시작 시각은 이 함수 하나로 읽는다.
- 마감 표지가 붙은 시각('18:00까지 · 15시 전에 · 17시 마감')은 회의 시각이 아니라 기한이다 → 회의 시각으로 쓰지 않는다
- 날짜를 못 읽는 상대 시점('3일 뒤 · 다음 주에 · 주말에')만 있으면 오늘로 두지 않고 None(명령은 되묻는다)
- 끝 시각(`parse_event_end`)은 시작보다 늦은 가장 이른 시각이고, 자정을 넘으면 다음 날이다('23:30~00:30'). 12시간을 넘으면 버린다
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

WEEKDAYS = "월화수목금토일"
DEFAULT_TIME = time(18, 0)

_WD = r"([월화수목금토일])요일"
_WD_EN = r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)(?:day|sday|nesday|rsday|urday|s|r|rs)?\b"
_EN_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_EN_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_PAREN_WD = r"(?:\s*\([월화수목금토일]\))?"
_DATE_PATTERNS = [
    ("ymd", re.compile(r"(\d{4})\s*[년.\-/]\s*(\d{1,2})\s*[월.\-/]\s*(\d{1,2})\s*일?" + _PAREN_WD)),
    ("md", re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일" + _PAREN_WD)),
    ("md", re.compile(r"(?<![\d.:])(\d{1,2})/(\d{1,2})(?![\d/])" + _PAREN_WD)),
    ("rel", re.compile(r"오늘|금일|내일|익일|명일|모레|글피")),
    ("rel", re.compile(r"\b(?:[Tt]oday|[Tt]omorrow)\b")),
    ("next_week_start", re.compile(r"다음\s*주\s*초|차주\s*초")),
    ("this_week_end", re.compile(r"(?:이번\s*주|금주)\s*(?:내|중|안)|주중으로|주말\s*(?:전|까지)")),
    ("next_week_end", re.compile(r"(?:다음\s*주|차주)\s*(?:내|중|안)(?:으로)?")),  # '으로'까지: '주중으로'(이번 주)보다 길게
    ("week_wd", re.compile(r"(이번\s*주|금주|다음\s*주|차주|다다음\s*주)\s*" + _WD)),
    ("wd", re.compile(_WD)),
    ("md_en", re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b")),
    ("week_wd_en", re.compile(r"\b([Tt]his|[Nn]ext)\s+" + _WD_EN)),
    ("wd_en", re.compile(_WD_EN)),
    ("d", re.compile(r"(?<![\d/월])(?<!월\s)(\d{1,2})\s*일(?=\s*(?:까지|전|에|\(|$))")),
]
# 6번째 묶음: 영문 AM · PM('10:00 AM' · '6pm')
_TIME = re.compile(r"(오전|오후|아침|저녁|밤|새벽)?\s*(\d{1,2})\s*(?:시(?!간)\s*(?:(\d{1,2})\s*분|(반))?|:(\d{2})|(?=\s*[AaPp]\.?[Mm]\b))"
                   r"(?:\s*([AaPp])\.?[Mm]\b\.?)?")
# '10:00에서 15:00로 변경' → 바뀐 뒤 시각
_TIME_CHANGE = re.compile(r"(\d{1,2}(?::\d{2}|시))\s*(?:에서|(?:\S+\s+){0,3}?\S*(?:을|를))\s*(\d{1,2}(?::\d{2}|시))\s*(?:으)?로")  # v1.8 '10:00 회의를 14:00으로' 
_DEADLINE_MARK = re.compile(r"까지|전에|전까지|중으로|내로|이내")
# '~에 리뷰를 진행하려고 하는데' · '~ 미팅을 하고 싶은데' · '~에 진행할 예정' (날짜 뒤에 오는 일정 제안)
_EVENT_PROPOSAL = re.compile(r"(?:하|진행하|잡으|열)\s*려고|하고\s*싶|진행할\s*(?:예정|계획)|잡고\s*싶")
_REL_DAYS = {"오늘": 0, "금일": 0, "today": 0, "내일": 1, "익일": 1, "명일": 1, "tomorrow": 1, "모레": 2, "글피": 3}


@dataclass
class DueParse:
    raw: str
    due_at: datetime | None  # None: 기한 문구는 있는데 시각을 정할 수 없음('내일 미팅 전에')
    time_stated: bool = False  # 시각 글자가 메일 · 명령에 있었다(보정 전 원래 값 기준). 기본 시각으로 채웠으면 False


def _weekday_after(base: date, wd: int, strictly_after: bool = True) -> date:
    delta = (wd - base.weekday()) % 7
    if delta == 0 and strictly_after:
        delta = 7
    return base + timedelta(days=delta)


_EOD = r"(?:EOD|COB|end of (?:the )?day|close of business)"


def _eod_today(m: re.Match) -> bool:
    """'EOD Thursday' · 'Thursday EOD'처럼 그날 업무 끝을 붙인 요일(11-20 사용자 결정, AI-31 남은 일).
    받은 날이 그 요일이면 그날이다(목요일에 보낸 'EOD Thursday'는 오늘 퇴근 전 — 밤에 받았으면 이미 지난 기한).
    지난 요일(금요일에 받은 'EOD Thursday')은 다음 주 그 요일로 그대로 간다."""
    return bool(re.search(_EOD + r"\s*(?:on\s+)?$", m.string[:m.start()], re.I)
                or re.match(r"\s*" + _EOD, m.string[m.end():], re.I))


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
        return base + timedelta(days=_REL_DAYS[m[0].lower()])
    if kind == "md_en":
        return _fix_year(date(base.year, _EN_MONTHS.index(m[1]) + 1, int(m[2])), base, False)
    if kind == "week_wd_en":
        return _week_start(base) + timedelta(days=7 * (m[1].lower() == "next") + _EN_DAYS.index(m[2]))
    if kind == "wd_en":
        return _weekday_after(base, _EN_DAYS.index(m[1]), not _eod_today(m))
    if kind == "next_week_start":
        return _week_start(base) + timedelta(days=8)  # 다음 주 화요일
    if kind == "next_week_end":
        return _week_start(base) + timedelta(days=11)  # 다음 주 금요일
    if kind == "this_week_end":
        return max(_week_start(base) + timedelta(days=4), base)
    if kind == "week_wd":
        offset = 2 if "다다음" in m[1] else 1 if ("다음" in m[1] or "차주" in m[1]) else 0
        return _week_start(base) + timedelta(days=7 * offset + WEEKDAYS.index(m[2]))
    if kind == "wd":
        return _weekday_after(base, WEEKDAYS.index(m[1]), not _eod_today(m))
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
        ampm, en = m[1], (m[6] or "").lower()
        if en:  # 'PM'을 적었으면 그대로(1~7시 오후 보정을 하지 않는다)
            h = h + 12 if en == "p" and h < 12 else 0 if en == "a" and h == 12 else h
        elif ampm in ("오후", "저녁", "밤") and h < 12:
            h += 12
        elif ampm is None and 1 <= h <= 7:  # '3시까지'는 업무 시간 기준 오후로 본다. '새벽 2시'는 그대로(AI-20)
            h += 12
        if h == 24:
            h = 23
        return time(h, mi)
    return None


# 시각 바로 뒤에 마감 표지가 붙으면 그 시각은 기한이다('참석 여부를 18:00까지 회신') — 회의 시각으로 쓰지 않는다
_DEADLINE_AFTER = re.compile(r"\s*(?:까지|전에|전까지|이전|이내|내로|마감)")
# 날짜 꼴 글자('11/31' · '2월 30일'). _find_date가 못 읽었는데 이것이 있으면 없는 날짜를 말한 것이다
_DATE_LIKE = re.compile(r"(?<![\d.:])\d{1,2}\s*/\s*\d{1,2}(?![\d:])|\d{1,2}\s*월\s*\d{1,2}\s*일")
# 날짜 표현으로 못 읽는 상대 시점. 이것만 있으면 '오늘'로 두지 않는다
RELATIVE_WHEN = re.compile(r"\d+\s*(?:일|주|달|개월)\s*(?:반\s*)?(?:뒤|후|있다가|지나서)|다음\s*(?:주|달)|차주|다다음\s*주|내달|주말|월말|연말")


def _find_event_time(text: str) -> time | None:
    """일정 시각. _find_time과 같은 변환(오전 · 오후 · '3시'는 오후 · 바뀐 뒤 시각)을 쓰되, 마감 표지가 붙은 시각은 건너뛴다."""
    ch = _TIME_CHANGE.search(text)
    if ch:
        return _find_time(ch.group(2))
    for m in _TIME.finditer(text):
        if _DEADLINE_AFTER.match(text, m.end()):
            continue
        t = _find_time(m.group(0))
        if t is not None:
            return t
    return None


def _vague_time(text: str) -> time | None:
    # 일의 시작 전이 가장 이르므로 먼저 본다 ('오전 미팅 전에' → 09:00)
    if re.search(r"(?:작업|업무|보고|미팅|회의|출근)\s*(?:시작\s*)?전(?:에|까지)?|(?:요일|일)\s*전에", text) or \
            (re.search(r"아침", text) and not re.search(r"아침\s*\d", text)):
        return time(9, 0)
    if (re.search(r"점심\s*(?:전|까지)|정오|오전\s*(?:중|까지|내)?", text) and not re.search(r"오전\s*\d", text)) or \
            re.search(r"\b(?:morning|noon)\b", text, re.I):
        return time(12, 0)
    if re.search(r"퇴근\s*전|오후\s*(?:중|까지|내)?|중(?:으로)?|EOD|COB|end of (?:the )?day|close of business", text, re.I) \
            and not re.search(r"오후\s*\d", text):
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
        stated = _find_time(text) if re.search(r"까지|전에|전까지", text) else None
        t = stated or (_vague_time(text) if re.search(r"점심|정오|퇴근|오늘|금일", text) else None)
        if t is None:
            return None
        return DueParse(text.strip(), datetime.combine(base.date(), t), stated is not None)
    d, m = found
    tail = text[m.start():]
    stated = _find_time(tail)
    t = stated or _vague_time(tail) or DEFAULT_TIME
    return DueParse(tail[: max(len(m[0]), 1) + 12].strip(), datetime.combine(d, t), stated is not None)


def parse_event_at(text: str, base: datetime, *, roll_forward: bool = False) -> DueParse | None:
    """회의 · 일정 시작 시각(AI-20). 날짜는 parse_due_plain과 같이 읽고, 시각은 마감 표지가 붙지 않은 시각 글자만 쓴다.
    시각 글자가 없으면 parse_due_plain과 같은 보정(때 · 18:00)을 하되 time_stated=False다.
    roll_forward(명령용): 날짜 없이 시각만 있으면 오늘, 지났으면 내일. 날짜로 못 읽는 상대 시점('3일 뒤')이 있으면 None.
    메일 분류는 roll_forward를 쓰지 않는다(날짜 없는 시각으로 일정을 만들지 않는다, 이전 동작과 같다)."""
    if not text:
        return None
    found = _find_date(text, base.date())
    if found is None:
        # 날짜 꼴 글자가 있는데 못 읽었으면('11/31' · '13/5' · '2월 30일') 시각만 보고 오늘 · 내일로 두지 않는다(명령은 되묻는다)
        if not roll_forward or RELATIVE_WHEN.search(text) or _DATE_LIKE.search(text):
            return None
        t = _find_event_time(text)
        if t is None:
            return None
        at = datetime.combine(base.date(), t)
        return DueParse(text.strip(), at if at > base else at + timedelta(days=1), True)
    d, m = found
    tail = text[m.start():]
    raw = tail[: max(len(m[0]), 1) + 12].strip()
    t = _find_event_time(tail)
    if t is not None:
        return DueParse(raw, datetime.combine(d, t), True)
    return DueParse(raw, datetime.combine(d, _vague_time(tail) or DEFAULT_TIME), False)


# 기한 표지(할 일 기한 전용). '오늘 중 · 오전 중에 · 금주 중'의 '중'도 표지다('검토 중이며'는 아니다)
_DEADLINE_MARK_TASK = re.compile(r"까지|전에|전까지|중으로|내로|이내|이전|안으로|안에|(?<=\s)(?:중(?:에)?|전|내)(?![가-힣])|"
                                 r"때(?=\s+(?:\S+\s+){0,2}?\S*(?:얘기|말씀|보고|공유|알려|전달|회신))")  # v1.8 '회의 때 구두로 얘기해 줘도 됩니다' 
_DEADLINE_SHIFT = re.compile(r"(?:마감|기한|제출일)\S*\s+(.{1,30}?)(?:으)?로\s*(?:당|앞당|변경|연장|조정|늦)")
# '회신 기한: 11/6(금)' · '마감일은 10/23입니다' 같은 기한 표시 줄
_DEADLINE_LABEL = re.compile(r"(?:기한|마감일?|제출일|회신일|due)\s*(?:[:：]|은|는|이|:)\s*(.{1,30})", re.I)
# '11/9(월) 오전에 보내 주세요' — 날짜 + '에' 바로 뒤가 요청 동사면 그 날 하라는 기한이다('10/27에 개인 사정이 있어'는 아니다)
_ON_DAY_REQUEST = re.compile(r"(\S+(?:\s+\S+){0,2})에\s+(?:\S+\s+){0,2}?\S*(?:주세요|주십시오|주시기|부탁드|바랍니다)")
# 시각을 모르는 일의 '전' — 언제인지는 사용자만 안다
# 시각을 모르는 행사 앞 기한('내일 고객 미팅 전에'). 행사 말과 '전' 사이에 낱말이 두 개까지 끼어도 같다('보고 들어가기 전에', 11/7)
_UNKNOWN_EVENT = re.compile(r"(?:미팅|회의|보고|발표|리뷰|작업|업무|공유|통화)\S*\s*(?:\S+\s+){0,2}?(?:시작\s*)?전(?:에|까지)?(?![가-힣])")


ASAP = re.compile(r"즉시|지금\s*바로|ASAP|asap|최대한\s*빨리|가능한\s*(?:한\s*)?빨리|빠른\s*시일\s*(?:내|안)|조속히")


def _tail(text: str, end: int, n: int) -> str:
    """text[:end]의 마지막 n어절을 원문 그대로(띄어쓰기 유지) 돌려준다."""
    starts = [m.start() for m in re.finditer(r"\S+", text[:end])]
    return text[starts[-n] if len(starts) >= n else (starts[0] if starts else 0): end]


# v1.8 '그 전에 · 그때까지 · 마감 전까지'는 앞에 나온 일시를 가리킨다
_ANAPHOR = re.compile(r"그\s*(?:전|때)|마감(?:일)?\s*전")
# v1.8 '점검을 내일로 미뤄도 되는지'의 '내일'은 바꿀 내용이지 기한이 아니다
_CHANGE_TARGET = re.compile(r"\S+?(?:으)?로\s+(?=(?:미뤄|미루|옮|변경|연기|당겨|당기|바꿔|바꾸))")
_EVENT_WORD = re.compile(r"미팅|회의|보고|발표|리뷰|설명회|점검|시연")


def _resolve_anaphor(ctx: str, base: datetime) -> DueParse | None:
    """앞 글(ctx)에서 마지막으로 나온 일시를 찾아 기한으로. 일의 시각을 모르면('화요일 오전 미팅') 문구만 둔다."""
    found = _find_date(ctx, base.date())
    if found is None:
        return None
    phrase = re.split(r"[.,]|(?<=이라|라서|어서|아서|니까|는데|지만)\s", ctx[found[1].start():])[0].strip()[:30]
    words = []
    for w in phrase.split():  # '내일 10시 고객 보고 때 이 자료로 …' → '내일 10시 고객 보고'
        words.append(re.sub(r"(?:에|때|이|가|을|를|은|는|이며|됩니다|합니다|입니다)$", "", w) or w)
        if _EVENT_WORD.search(w) or "마감" in w:
            break
    raw = " ".join(words) + " 전"
    if _EVENT_WORD.search(phrase) and not _find_time(phrase):
        return DueParse(raw, None)
    hit = parse_due_plain(phrase, base)
    if hit is not None:
        hit.raw = raw
    return hit


def parse_deadline(text: str, base: datetime, prior: str = "") -> DueParse | None:
    """할 일 기한. 마감 표지가 붙은 날짜만 기한이다(표지 없는 날짜는 일정 · 지난 일 · 참고 날짜라 None).
    prior: 이 문장 앞의 본문('그 전에 · 마감 전까지'가 가리키는 일시를 찾을 때만 쓴다)."""
    if not text:
        return None
    if ASAP.search(text):
        # v1.8(11/6 사용자 결정): 즉시 · 최대한 빨리 · ASAP는 'ASAP'로만 띄운다. 시각은 지어내지 않는다(due_at 비움)
        return DueParse("ASAP", None)
    text = _CHANGE_TARGET.sub(" ", text)
    # v1.8 '오전 중에 알려 주시면 오늘 발주 마감 전에 처리하겠습니다': '~주시면' 뒤는 보낸 사람이 할 일이라 그 기한이 아니다
    if (cond := re.search(r"주시면\s+(?!감사|좋겠)", text)):  # '빠듯하시면 · 가능하시면'은 조건일 뿐 요청이 아니다
        text = text[: cond.end()]
    if (sh := _DEADLINE_SHIFT.search(text)):  # '명단 마감을 10/20(화) 오후 3시로 당깁니다'
        hit = parse_due_plain(sh.group(1), base)
        if hit is not None:
            return hit
    if (lb := _DEADLINE_LABEL.search(text)):
        hit = parse_due_plain(lb.group(1), base)
        if hit is not None:
            return hit
    for mk in reversed(list(_DEADLINE_MARK_TASK.finditer(text))):
        window = _tail(text, mk.end(), 5)  # 표지 앞 네 어절 + 표지
        if mk[0].startswith("중") and len(_MONTH_DAY.findall(window)) >= 2:
            continue  # '11/29 · 12/6 중 가능한 날': 고를 날짜이지 기한이 아니다
        if _find_date(window, base.date()) is None and _find_date(wide := _tail(text, mk.end(), 8), base.date()):
            window = wide  # 날짜가 조금 앞에 있다('수요일 오전 10시 내부 리뷰 전까지')
        # 앞 절('오늘 오후 1시에 보낼 예정이라, …')의 날짜는 이 기한이 아니다 → 마지막 절만 본다
        window = re.split(r",\s*|(?<=이라|라서|어서|아서|니까|는데|지만|으며)\s+", window)[-1]
        found = _find_date(window, base.date())
        if found is None and _ANAPHOR.search(window):
            hit = _resolve_anaphor(f"{prior} {text[: text.rfind(window)]}", base)
            if hit is not None:
                return hit
        ev = _UNKNOWN_EVENT.search(window)
        if ev and not _find_time(window):
            # '내일 고객 미팅 전에': 미팅 시각을 모른다 → 문구 그대로, 시각은 비운다(사용자는 안다)
            return DueParse(window[found[1].start() if found else ev.start():].strip(), None)
        if found is not None:
            hit = parse_due_plain(window, base)
            if hit is not None:
                hit.raw = window[found[1].start():].strip()
                return hit
        # 날짜 없이 오늘 안의 때만 있는 기한('오전 중에 · 점심 전까지 · 퇴근 전까지 · 3시까지')
        stated = _find_time(window)
        t = stated or _vague_time(window)
        if t is not None and (m := re.search(r"(?:오전|오후|점심|정오|퇴근|EOD|\d{1,2}\s*시|\d{1,2}:\d{2}).*", window)):
            return DueParse(m.group(0).strip(), datetime.combine(base.date(), t), stated is not None)
    for m in _ON_DAY_REQUEST.finditer(text):
        if _find_date(m.group(1), base.date()) is not None and not re.search(r"드린|했던|받은|주신|보낸", m.group(0)):
            return parse_due_plain(m.group(1), base)
    return _deadline_en(text, base)


# 영문 기한 표지. 날짜 · 시각이 표지 뒤에 온다('by EOD Thursday' · 'before our Friday sync at 10:00 AM KST')
_EN_MARK = re.compile(r"\b(?:by|before|no later than|until|till|prior to|due(?:\s+(?:on|by))?)\b", re.I)
_EN_EVENT = re.compile(r"\b(?:sync|meeting|call|review|session|workshop|demo|presentation)\b", re.I)


def _deadline_en(text: str, base: datetime) -> DueParse | None:
    for mk in _EN_MARK.finditer(text):
        window = re.split(r"[?;!]|\.(?:\s|$)", " ".join(text[mk.end():].split()[:8]))[0].strip()
        found, t = _find_date(window, base.date()), _find_time(window)
        raw = f"{mk[0]} {window}"
        if found is None:
            if t is not None:  # 'by 3 PM': 오늘 그 시각
                return DueParse(raw, datetime.combine(base.date(), t), True)
            continue
        if t is None and _EN_EVENT.search(window):  # 'before the Friday sync': 회의 시각을 모른다 → 시각을 비운다
            return DueParse(raw, None)
        return DueParse(raw, datetime.combine(found[0], t or _vague_time(window) or DEFAULT_TIME), t is not None)
    return None


# 일정 시간 범위: '14:00~15:30' · '오후 2시 - 4시' · '10시부터 12시까지' · '14시~16시 30분'
_CLOCK = r"(?:오전|오후|아침|저녁|밤|새벽)?\s*\d{1,2}\s*(?::\d{2}|시(?!간)(?:\s*\d{1,2}\s*분|\s*반)?)"
_RANGE = re.compile(rf"({_CLOCK})\s*(?:~|∼|〜|-|–|—|부터)\s*({_CLOCK})")


_CLOCK_PARTS = re.compile(r"(오전|오후|아침|저녁|밤|새벽)?\s*(\d{1,2})\s*(?::(\d{2})|시(?:\s*(\d{1,2})\s*분|\s*(반))?)")


def parse_event_end(text: str, start: datetime | None) -> datetime | None:
    """일정 끝 시각(AI-20 · D50). 시작 시각과 같은 시각으로 시작하는 범위가 글자로 있을 때만 돌려준다.
    끝 시각 후보(그 시각 · 12시간 뒤 · 다음 날)를 놓고 시작보다 늦은 가장 이른 것을 고른다. 오전 · 오후를 적었으면 그 쪽만 본다.
    '오후 2시~4시' 16:00 · '11시~1시' 13:00 · '23:30~00:30' 다음 날 00:30 · '22:00~24:00' 다음 날 00:00 · '밤 11시~1시' 다음 날 01:00.
    콜론으로 쓴 끝 시각('9:00')은 24시간제라 12시간을 더하지 않는다.
    12시간을 넘는 범위는 일정 길이가 아니라 다른 뜻으로 보고 버린다. 범위가 없으면 None(길이 기본값 1시간은 backend가 둔다)."""
    if not text or start is None:
        return None
    ends, prev = [], 0
    for m in _RANGE.finditer(text):
        seg, prev = text[prev:m.start()], m.end()
        if _find_time(m[1]) != start.time():
            continue
        e = _CLOCK_PARTS.search(m[2])
        if e is None:
            continue
        md = _MONTH_DAY.findall(seg)
        ends.append((_range_end(e, start), md[-1] if md else None))
    if len({end for end, _ in ends}) <= 1:
        return ends[0][0] if ends else None
    # 시작 시각이 같은 범위가 여럿이고 끝이 다르면('1차 11/12 14:00~15:00 / 2차 11/19 14:00~17:00') 바로 앞 날짜가 시작 날짜인 범위.
    # 날짜로 가를 수 없으면 지어내지 않는다
    same = [end for end, md in ends if md and (int(md[0]), int(md[1])) == (start.month, start.day)]
    return same[0] if same else None


_MONTH_DAY = re.compile(r"(\d{1,2})\s*(?:/|월\s*)(\d{1,2})")


def _range_end(e: re.Match, start: datetime) -> datetime | None:
    """범위 끝 글자(_CLOCK_PARTS)를 시작보다 늦은 가장 이른 시각으로. 12시간을 넘으면 None."""
    h, mi = int(e[2]), int(e[3] or e[4] or (30 if e[5] else 0))
    if h > 24 or mi > 59:
        return None
    ampm = e[1]
    if ampm in ("오후", "저녁", "밤") and h < 12:
        hours = [h + 12]
    elif ampm in ("오전", "아침", "새벽"):
        hours = [h % 12]
    elif e[3] is not None:  # '9:00'처럼 콜론으로 쓴 시각은 24시간제로 읽는다('10:00~9:00'을 21:00으로 바꾸지 않는다)
        hours = [h % 24]
    else:  # '4시'는 오전 · 오후가 갈린다 → 둘 다 후보
        hours = [h % 24] + ([h + 12] if h < 12 else [])
    cands = [datetime.combine(start.date(), time(0, 0)) + timedelta(days=day, hours=hh, minutes=mi)
             for day in (0, 1) for hh in hours]
    later = [c for c in cands if start < c <= start + timedelta(hours=12)]
    return min(later) if later else None


def parse_date_range(text: str, base: datetime) -> tuple[date, date] | None:
    """명령용 기간 표현: '이번 주' · '다음 주' · '오늘' · '내일' → (시작일, 끝일)."""
    b = base.date()
    ws = _week_start(b)
    if re.search(r"다음\s*주|차주", text):
        return ws + timedelta(days=7), ws + timedelta(days=13)
    if re.search(r"이번\s*주|금주", text):
        return ws, ws + timedelta(days=6)
    if re.search(r"지난\s*주|저번\s*주", text):  # 11-18 '지난주에 받은 메일'(T19)
        return ws - timedelta(days=7), ws - timedelta(days=1)
    if "오늘" in text:
        return b, b
    if "어제" in text:  # 11-18 '어제 받은 메일 몇 통'(T19)
        return b - timedelta(days=1), b - timedelta(days=1)
    if "내일" in text:
        return b + timedelta(days=1), b + timedelta(days=1)
    if re.search(r"이번\s*달|이달", text):
        nxt = date(b.year + (b.month == 12), b.month % 12 + 1, 1)
        return date(b.year, b.month, 1), nxt - timedelta(days=1)
    return None
