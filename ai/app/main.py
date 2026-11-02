"""ai 서비스 진입점. 실행: `uvicorn app.main:app --port 8001` (backend의 AI_SERVICE_URL과 맞춘다)."""
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import agent, assist, classify, health
from app.api.deps import llm_dep


@asynccontextmanager
async def lifespan(_: FastAPI):
    warm = getattr(llm_dep(), "warm", None)  # ollama만 있다. 기다리지 않고 뒤에서 모델을 올린다
    if warm:
        threading.Thread(target=warm, daemon=True).start()
    yield


app = FastAPI(title="ax-ai", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
app.include_router(classify.router)
app.include_router(agent.router)
app.include_router(assist.router)
