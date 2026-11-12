"""테스트에서 서비스 시각을 옮기는 도구. 시간 이동은 clock.set_offset 하나로 한다(#49 CLOCK_START와 같은 장치)."""
from datetime import datetime, timedelta

from app.core import clock


def move_to(at: datetime | None) -> None:
    """서비스 시각을 at(시간대 없으면 KST)으로 옮긴다. 이후로는 실제 시간만큼 흐른다. None이면 실제 시각으로 돌아간다."""
    clock.set_offset(timedelta(0) if at is None else clock.to_kst_naive(at) - clock.real_now())
