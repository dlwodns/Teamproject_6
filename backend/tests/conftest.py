import os

os.environ["DATABASE_URL"] = "sqlite://"  # app을 불러오기 전에 정한다. 테스트는 메모리 DB만 쓴다
os.environ.setdefault("APP_MODE", "dev")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

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
    with TestClient(app) as c:
        yield c
