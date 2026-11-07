from app.core.clock import now
from app.models import User


def test_now_is_naive_kst():
    assert now().tzinfo is None


def test_db_time_comparable_with_now(db):
    # DB에서 읽은 시각과 now()를 비교해도 오류가 나지 않아야 한다(기한 지남 · 리마인더 판정)
    db.add(User(id=1, name="테스트"))
    db.commit()
    db.expire_all()
    assert db.get(User, 1).created_at <= now()
