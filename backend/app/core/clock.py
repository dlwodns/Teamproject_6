"""서비스 시각. 기한 18:00 · 리마인드 08:30은 한국 시간 기준이다(CI도 TZ=Asia/Seoul, INF-6).

시각은 모두 이 모듈의 now()로 얻는다. 개발 모드 시간 이동(BE-14)은 여기만 바꾸면 된다.
값은 시간대 없는 한국 시간(naive KST)이다. SQLite DateTime 칸은 시간대를 저장하지 않아 읽으면 naive로
돌아오고, ai 서비스(#4)도 naive 시각을 전제로 한다. aware 값과 섞어 비교하면 TypeError가 난다.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def now() -> datetime:
    return datetime.now(KST).replace(tzinfo=None)


def to_kst_naive(dt: datetime) -> datetime:
    """요청으로 들어온 시각을 저장 형식으로. 시간대가 붙어 있으면 KST로 바꿔 떼고, 없으면 KST로 본다(D47)."""
    return dt.astimezone(KST).replace(tzinfo=None) if dt.tzinfo else dt


def as_kst(dt: datetime | None) -> datetime | None:
    """저장된 naive KST를 응답 형식으로. backend → frontend 응답 시각에는 항상 +09:00을 붙인다(D47)."""
    return dt.replace(tzinfo=KST) if dt is not None else None
