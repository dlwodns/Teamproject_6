# Railway ai 이미지 (infra/railway_setup.md). 빌드 컨텍스트 = ai/ (Root Directory /ai)
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 TZ=Asia/Seoul
WORKDIR /app

COPY pyproject.toml uv.lock ./
# --no-dev: 개발용 패키지를 이미지에 넣지 않는다(uv Docker 가이드). 지금 pytest는 extra(dev)라 기본으로도 빠지지만, dev 그룹으로 옮겨도 막히게 둔다
RUN uv sync --locked --no-install-project --no-dev

# 로컬 .venv가 이미지 .venv를 덮지 않게 ai/.dockerignore에서 뺀다
COPY . .

ENV PATH="/app/.venv/bin:$PATH"
# 공개 주소 없이 내부망(ai.railway.internal)으로만 받는다(R7). 0.0.0.0 = IPv4. ::는 asyncio가 IPV6_V6ONLY를 켜 IPv6만 받아 헬스체크가 닿지 않는다(railway_setup.md 3절)
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8001}"]
