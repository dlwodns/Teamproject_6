"""ai 서비스 진입점. 실행: `uvicorn app.main:app --port 8001` (backend의 AI_SERVICE_URL과 맞춘다)."""
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import agent, assist, classify, health
from app.api.deps import llm_dep
from app.core import request_id
from app.core.config import ensure_settings
from app.pipeline.classify import PROMPT


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_settings()  # 설정이 틀리면 뜨지 않는다(INF-4)
    warm = getattr(llm_dep(), "warm", None)  # ollama만 있다. 기다리지 않고 뒤에서 모델을 올린다
    if warm:  # 메일 분류가 가장 자주 부르므로 분류 시스템 프롬프트를 미리 읽혀 둔다
        threading.Thread(target=warm, args=(PROMPT.SYSTEM,), daemon=True).start()
    yield


request_id.setup_logging()
app = FastAPI(title="ax-ai", version="0.1.0", lifespan=lifespan)
request_id.install(app)  # X-Request-ID · 접근 로그(INF-12)
app.include_router(health.router)
app.include_router(classify.router)
app.include_router(agent.router)
app.include_router(assist.router)
