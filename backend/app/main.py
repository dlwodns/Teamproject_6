"""backend 진입점. 실행: `uvicorn app.main:app --port 8000` (backend/ 폴더에서)."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import actions, agent_command, health
from app.core import request_id
from app.core.config import ensure_settings
from app.core.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_settings()  # 설정이 틀리면 뜨지 않는다(INF-4)
    init_db()  # 테이블이 없으면 만든다. 있는 테이블 · 데이터는 건드리지 않는다
    yield


request_id.setup_logging()
app = FastAPI(title="ax-backend", version="0.1.0", lifespan=lifespan)
request_id.install(app)  # X-Request-ID · 접근 로그(INF-12)
app.include_router(health.router)
app.include_router(actions.router)
app.include_router(agent_command.router)
