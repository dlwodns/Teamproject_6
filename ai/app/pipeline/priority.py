"""우선순위 (AI-6). 모델에 맡기지 않고 코드로 계산한다(벤치 결정 · AI-D4).

점수 규칙은 data/dummy/build.py `priority`와 같다(D9). 가중치 확정은 `[미정]`.
"""
from datetime import datetime


def score(*, superior_or_favorite: bool, dues: list[datetime], received_at: datetime,
          urgent: bool, follow_up: bool, recipient: str) -> int:
    s = 30 if superior_or_favorite else 0  # 상급자 · 즐겨찾기 중복 가산 없음
    if dues:
        h = (min(dues) - received_at).total_seconds() / 3600
        s += 30 if h <= 24 else 15 if h <= 72 else 0
    s += 15 if urgent else 0
    s += 20 if follow_up else 0
    s += 10 if recipient == "to" else -10 if recipient == "cc" else 0
    return s


def level(points: int) -> str:
    return "P1" if points >= 70 else "P2" if points >= 40 else "P3"
