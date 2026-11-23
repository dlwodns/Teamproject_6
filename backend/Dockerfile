# Railway backend 이미지 (infra/railway_setup.md)
# 빌드 컨텍스트 = 저장소 루트. Railway에서 Root Directory를 비우고 RAILWAY_DOCKERFILE_PATH=backend/Dockerfile 로 둔다.
# 루트에서 빌드하는 이유: 더미 메일을 저장소 루트의 data/dummy에서 읽는다(app/mail/body.py · app/dev/seed.py, parents[3]).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# TZ: CI와 같은 한국 시간(INF-6). 리마인더 08:30 · 기한 18:00이 Asia/Seoul 기준이다(app/core/clock.py)
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 TZ=Asia/Seoul
WORKDIR /app/backend
# Linux에서는 시스템 시간대 파일을 쓴다(uv.lock의 tzdata는 win32 전용). 없으면 실행 때가 아니라 빌드에서 멈춘다
RUN python -c "from zoneinfo import ZoneInfo; ZoneInfo('Asia/Seoul')"

# 의존성 먼저(코드만 바뀌면 이 층은 캐시를 쓴다)
COPY backend/pyproject.toml backend/uv.lock ./
# --no-dev: 개발용 패키지를 이미지에 넣지 않는다(uv Docker 가이드). 지금 pytest는 extra(dev)라 기본으로도 빠지지만, dev 그룹으로 옮겨도 막히게 둔다
RUN uv sync --locked --no-install-project --no-dev

COPY backend/ ./
COPY data/dummy/ /app/data/dummy/

ENV PATH="/app/backend/.venv/bin:$PATH"
# 프로세스 1개(리마인더 중복 방지, deploy_decision.md R2). 0.0.0.0 = IPv4. ::는 IPv6만 받아 헬스체크가 닿지 않는다(railway_setup.md 3절)
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
