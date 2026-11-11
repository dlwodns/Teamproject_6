"""서비스 시각. 기한 18:00 · 리마인드 08:30은 한국 시간 기준이다(CI도 TZ=Asia/Seoul, INF-6).

시각은 모두 이 모듈의 now()로 얻는다. 개발 모드 시간 이동(BE-14)은 여기만 바꾸면 된다.
값은 시간대 없는 한국 시간(naive KST)이다. SQLite DateTime 칸은 시간대를 저장하지 않아 읽으면 naive로
돌아오고, ai 서비스(#4)도 naive 시각을 전제로 한다. aware 값과 섞어 비교하면 TypeError가 난다.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
_offset: timedelta | None = None  # 개발 모드 시간 이동. 시나리오 평가(PL-16)만 쓴다. 운영에서는 항상 None


def _real_now() -> datetime:
    return datetime.now(KST).replace(tzinfo=None)


def now() -> datetime:
    off = _offset  # 한 번만 읽는다(다른 요청이 그사이 바꿔도 None + 시각이 되지 않게)
    base = _real_now()
    return base + off if off is not None else base


def set_dev_now(at: datetime | None) -> None:
    """서비스 시각을 at으로 옮긴다(이후로는 실제 시간만큼 흐른다). None이면 실제 시각으로 돌아간다.
    부르는 쪽(dev 라우터)이 APP_MODE=dev인지 먼저 확인한다."""
    global _offset
    _offset = None if at is None else to_kst_naive(at) - _real_now()


def to_kst_naive(dt: datetime) -> datetime:
    """요청으로 들어온 시각을 저장 형식으로. 시간대가 붙어 있으면 KST로 바꿔 떼고, 없으면 KST로 본다(D47)."""
    return dt.astimezone(KST).replace(tzinfo=None) if dt.tzinfo else dt


def as_kst(dt: datetime | None) -> datetime | None:
    """저장된 naive KST를 응답 형식으로. backend → frontend 응답 시각에는 항상 +09:00을 붙인다(D47)."""
    # 마이크로초는 버린다. 응답 시각 형식을 "YYYY-MM-DDTHH:MM:SS+09:00" 하나로 고정(프런트엔드 · 시나리오가 글자 그대로 비교한다)
    return dt.replace(tzinfo=KST, microsecond=0) if dt is not None else None
