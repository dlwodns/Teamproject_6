"""ai 서비스 진입점. 실행: `uvicorn app.main:app --port 8001` (backend의 AI_SERVICE_URL과 맞춘다)."""
from fastapi import FastAPI

from app.api import health

app = FastAPI(title="ax-ai", version="0.1.0")
app.include_router(health.router)
