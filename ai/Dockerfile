# Railway ai 이미지 (infra/railway_setup.md). 빌드 컨텍스트 = ai/ (Root Directory /ai)
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 TZ=Asia/Seoul
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

COPY . .

ENV PATH="/app/.venv/bin:$PATH"
# 공개 주소 없이 내부망(ai.railway.internal)으로만 받는다(R7). :: = IPv4 · IPv6 둘 다
CMD ["sh", "-c", "exec uvicorn app.main:app --host :: --port ${PORT:-8001}"]
