"""서비스 시각. 기한 18:00 · 리마인드 08:30은 한국 시간 기준이다(CI도 TZ=Asia/Seoul, INF-6).

시각은 모두 이 모듈의 now()로 얻는다. 개발 모드 시간 이동(BE-14)은 여기만 바꾸면 된다.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def now() -> datetime:
    return datetime.now(KST)
