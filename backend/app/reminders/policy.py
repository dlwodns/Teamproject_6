"""알림 정책 — 언제 보내도 되는가 (명세 reminders.md 4.1 · 4.2절, BE-D28).

시각은 모두 시간대 없는 한국 시간이다(`app/core/clock.py`). 이 모듈은 DB에 쓰지 않는다.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.models import UserSettings

# ---- 정책 값(명세 4.1 · 4.2절). 바꾸면 docs/30_backend/decisions.md BE-D28도 고친다 ----
MAX_NOTIFY = 3  # 같은 항목은 최대 3번. 넘으면 목록에만 남기고 '조용히 둠'
BACKOFF = (timedelta(days=1), timedelta(days=2), timedelta(days=4))  # n번 보낸 뒤 다음 알림까지 간격. 3번째 뒤(4일)는 조용히 둠으로 바뀐다
DUE_BEFORE = timedelta(hours=3)  # R-기한. 시각 없는 기한은 18:00으로 보정되므로 15:00이 된다
MEETING_BEFORE = timedelta(minutes=30)
DIGEST_MIN = 3  # 같은 분에 이만큼 이상 나가면 "챙길 것 N건" 하나로 묶는다
EVENING_BEFORE_END = timedelta(minutes=30)  # 퇴근 회고 = 근무 끝 30분 전(명세 4.3절)
WEEKLY_DAY = 5  # 주간 회고 = 금요일(isoweekday)

DEFAULT_REMIND = "08:30"
DEFAULT_AWAIT_DAYS = 3
DEFAULT_WORK = ("09:00", "18:00", "1-5")


def hm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


def parse_days(value: str | None) -> frozenset[int]:
    """"1-5" · "1,3,5" · "1-3,6" → {1..7}(월=1). 못 읽으면 평일."""
    out: set[int] = set()
    try:
        for part in (value or DEFAULT_WORK[2]).split(","):
            part = part.strip()
            if "-" in part:
                a, b = part.split("-")
                out.update(range(int(a), int(b) + 1))
            elif part:
                out.add(int(part))
    except ValueError:
        return frozenset(range(1, 6))
    return frozenset(d for d in out if 1 <= d <= 7) or frozenset(range(1, 6))


@dataclass(frozen=True)
class Policy:
    remind: time = hm(DEFAULT_REMIND)
    await_days: int = DEFAULT_AWAIT_DAYS
    work_start: time = hm(DEFAULT_WORK[0])
    work_end: time = hm(DEFAULT_WORK[1])
    work_days: frozenset[int] = frozenset(range(1, 6))
    quiet: tuple[time, time] | None = None
    away_until: datetime | None = None
    mute: frozenset[str] = field(default_factory=frozenset)

    # ---------- 판정 ----------

    def is_work_day(self, d: date) -> bool:
        return d.isoweekday() in self.work_days

    def in_quiet(self, dt: datetime) -> bool:
        if self.quiet is None:
            return False
        s, e = self.quiet
        t = dt.time()
        return (s <= t < e) if s < e else (t >= s or t < e)  # 22:00~07:00처럼 자정을 넘을 수 있다

    def quiet_end_after(self, dt: datetime) -> datetime:
        """조용한 시간이 끝나는 첫 시각(dt가 조용한 시간 안일 때)."""
        assert self.quiet is not None
        end = datetime.combine(dt.date(), self.quiet[1])
        return end if end > dt else end + timedelta(days=1)

    def in_work(self, dt: datetime) -> bool:
        return (self.is_work_day(dt.date()) and self.work_start <= dt.time() < self.work_end
                and not self.in_quiet(dt))

    def away(self, at: datetime) -> bool:
        return self.away_until is not None and at < self.away_until

    # ---------- 시각 옮기기 ----------

    def next_work(self, dt: datetime) -> datetime | None:
        """dt 이후 처음으로 근무 시간이면서 조용한 시간이 아닌 시각. 2주 안에 없으면 None(근무 요일이 비었을 때 등)."""
        for k in range(15):
            day = dt.date() + timedelta(days=k)
            if not self.is_work_day(day):
                continue
            start, end = datetime.combine(day, self.work_start), datetime.combine(day, self.work_end)
            s = max(start, dt)
            if s >= end:
                continue
            if self.in_quiet(s):
                s = self.quiet_end_after(s)
            if s < end and not self.in_quiet(s):
                return s
        return None

    def outside_quiet(self, dt: datetime) -> datetime:
        return self.quiet_end_after(dt) if self.in_quiet(dt) else dt

    def latest_morning(self, at: datetime) -> datetime | None:
        """at 이전(포함) 가장 가까운 근무일의 R-아침."""
        for k in range(15):
            day = at.date() - timedelta(days=k)
            slot = datetime.combine(day, self.remind)
            if self.is_work_day(day) and slot <= at:
                return slot
        return None

    def next_morning(self, dt: datetime) -> datetime | None:
        """dt 이후(포함) 첫 근무일의 R-아침."""
        for k in range(15):
            day = dt.date() + timedelta(days=k)
            slot = datetime.combine(day, self.remind)
            if self.is_work_day(day) and slot >= dt:
                return slot
        return None

    def evening(self, day: date) -> datetime:
        return datetime.combine(day, self.work_end) - EVENING_BEFORE_END


def load(db: Session, user_id: int) -> Policy:
    s = db.get(UserSettings, user_id)
    if s is None:
        return Policy()
    days = s.awaiting_reply_days if s.awaiting_reply_days is not None else DEFAULT_AWAIT_DAYS
    quiet = (hm(s.quiet_start), hm(s.quiet_end)) if s.quiet_start and s.quiet_end else None
    if quiet is not None and quiet[0] == quiet[1]:
        quiet = None
    mute = frozenset(k for k, v in (s.reminder_mute or {}).items() if v)
    return Policy(remind=hm(s.remind_time or DEFAULT_REMIND), await_days=max(1, days),
                  work_start=hm(s.work_start or DEFAULT_WORK[0]), work_end=hm(s.work_end or DEFAULT_WORK[1]),
                  work_days=parse_days(s.work_days), quiet=quiet, away_until=s.away_until, mute=mute)


def slot_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M")


def parse_slot(value: str) -> datetime:
    return datetime.fromisoformat(value)
