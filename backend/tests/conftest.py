import os

os.environ["DATABASE_URL"] = "sqlite://"  # app을 불러오기 전에 정한다. 테스트는 메모리 DB만 쓴다
os.environ.setdefault("APP_MODE", "dev")
os.environ.pop("CLOCK_START", None)  # 셸에 시연 시각이 있어도 테스트는 실제 시각에서 시작한다
os.environ.pop("DEMO_TOOLS", None)  # 셸에 켜 둬도 테스트의 app에는 시연 도구가 없다(BE-14 테스트가 따로 켠다)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core import clock  # noqa: E402
from app.core.db import Base, SessionLocal, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def db():
    """테스트마다 빈 테이블에서 시작한다."""
    Base.metadata.drop_all(engine)
    init_db()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    offset = clock.get_offset()
    with TestClient(app) as c:
        # 서버 시작이 시각 offset을 다시 정해도(#49 CLOCK_START) 테스트가 먼저 옮겨 둔 시각을 그대로 쓴다
        clock.set_offset(offset)
        yield c
