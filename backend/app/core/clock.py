"""서비스 시각. 기한 18:00 · 리마인드 08:30은 한국 시간 기준이다(CI도 TZ=Asia/Seoul, INF-6).

시각은 모두 이 모듈의 now()로 얻는다. 개발 모드 시간 이동(BE-14)은 여기만 바꾸면 된다.
값은 시간대 없는 한국 시간(naive KST)이다. SQLite DateTime 칸은 시간대를 저장하지 않아 읽으면 naive로
돌아오고, ai 서비스(#4)도 naive 시각을 전제로 한다. aware 값과 섞어 비교하면 TypeError가 난다.

시연 시각(CLOCK_START): now() = 실제 현재 KST + offset. 멈춘 시각이 아니라 실제 시간만큼 같이 흐른다.
- offset은 서버 시작 때 init_clock()이 한 번 정한다(offset = 목표 시작 시각 - 실제 현재 KST).
  CLOCK_START가 비면 0이다. 다시 부르면 기존 offset을 바꿔 넣는다(더하지 않는다).
- offset은 프로세스 메모리 값이다. 재시작하면 CLOCK_START 시각부터 다시 시작하고, worker가 여럿이면 서로 나누지 않는다.
- 시간 이동(BE-14)은 set_offset()으로 offset을 바꿔 넣는다. 단일 worker를 전제로 한다.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

_offset = timedelta(0)


def _utc_now() -> datetime:
    """실제 시각을 대는 곳(시간대 있는 UTC). 테스트는 이것만 바꿔 실제 시각을 정한다."""
    return datetime.now(timezone.utc)


def real_now() -> datetime:
    """offset을 넣지 않은 실제 현재 KST(naive). 서버 OS 시간대와 상관없이 KST로 바꾼다."""
    return _utc_now().astimezone(KST).replace(tzinfo=None)


def now() -> datetime:
    return real_now() + _offset


def to_kst_naive(dt: datetime) -> datetime:
    """요청으로 들어온 시각을 저장 형식으로. 시간대가 붙어 있으면 KST로 바꿔 떼고, 없으면 KST로 본다(D47)."""
    return dt.astimezone(KST).replace(tzinfo=None) if dt.tzinfo else dt


def as_kst(dt: datetime | None) -> datetime | None:
    """저장된 naive KST를 응답 형식으로. backend → frontend 응답 시각에는 항상 +09:00을 붙인다(D47)."""
    # 마이크로초는 버린다. 응답 시각 형식을 "YYYY-MM-DDTHH:MM:SS+09:00" 하나로 고정(프런트엔드 · 시나리오가 글자 그대로 비교한다)
    return dt.replace(tzinfo=KST, microsecond=0) if dt is not None else None


def parse_clock_start(value: str | None) -> datetime | None:
    """CLOCK_START 값을 naive KST로. 비면 None, 틀리면 ValueError.

    ISO 8601만 받는다. 시간대가 없으면 KST로 보고, 있으면(+09:00 · Z 등) KST로 바꿔 뗀다.
    예) 2026-10-20T09:00 = 2026-10-20T09:00:00+09:00 = 2026-10-20T00:00:00Z
    """
    value = (value or "").strip()
    if not value:
        return None
    return to_kst_naive(datetime.fromisoformat(value))


def init_clock(clock_start: str | None) -> timedelta:
    """서버 시작 때 offset을 정한다. 기존 offset은 바꿔 넣는다. 비면 0. 정한 offset을 돌려준다.

    offset은 offset이 들어간 now()가 아니라 real_now()로 계산한다(다시 불러도 누적되지 않는다).
    """
    start = parse_clock_start(clock_start)
    return set_offset(start - real_now() if start is not None else timedelta(0))


def set_offset(offset: timedelta) -> timedelta:
    """offset을 바꿔 넣는다(더하지 않는다). 시간 이동(BE-14)용. 앞으로 하루: set_offset(get_offset() + timedelta(days=1))."""
    global _offset
    if not isinstance(offset, timedelta):
        raise TypeError("offset은 timedelta여야 한다")
    _offset = offset
    return _offset


def get_offset() -> timedelta:
    return _offset
