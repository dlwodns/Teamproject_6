"""backend 진입점. 실행: `uvicorn app.main:app --port 8000` (backend/ 폴더에서)."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.core.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()  # 테이블이 없으면 만든다. 있는 테이블 · 데이터는 건드리지 않는다
    yield


app = FastAPI(title="ax-backend", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
