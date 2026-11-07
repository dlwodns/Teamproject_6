"""요청 ID · 접근 로그 (INF-12, infra/plan.md). 한 요청을 frontend → backend → ai까지 같은 ID로 따라간다.

- 들어온 요청에 `X-Request-ID`가 있고 형식이 맞으면 그대로 쓰고, 없으면 새로 만든다. 응답 헤더에도 같은 값을 돌려준다.
- 접근 로그는 메서드 · 경로 · 상태 · 걸린 시간 · 요청 ID만 남긴다. 쿼리 문자열 · 본문 · 헤더는 남기지 않는다
  (메일 본문 · 토큰 · 사람 이름이 들어갈 수 있다, 7절 보안).
- `app.*` 로거로 남긴 줄에는 모두 요청 ID가 붙는다: `logging.getLogger(__name__)`.
"""
import logging
import re
import time
import uuid
from contextvars import ContextVar

from fastapi import FastAPI, Request

HEADER = "X-Request-ID"
NO_ID = "-"
_VALID = re.compile(r"[A-Za-z0-9._-]{1,64}")  # 밖에서 온 값은 이 형식만 받는다(로그 줄 깨기 · 긴 값 막기)
request_id_var: ContextVar[str] = ContextVar("request_id", default=NO_ID)
access_log = logging.getLogger("app.access")


def current_request_id() -> str:
    return request_id_var.get()


def request_id_headers() -> dict[str, str]:
    """ai를 부를 때 같은 요청 ID를 넘긴다. BE-9 ai_client에서 `httpx.post(..., headers=request_id_headers())`로 쓴다."""
    rid = request_id_var.get()
    return {HEADER: rid} if rid != NO_ID else {}


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def setup_logging(level: int = logging.INFO) -> None:
    """`app` 로거에 요청 ID가 붙는 출력 형식을 단다. 여러 번 불러도 한 번만 단다."""
    logger = logging.getLogger("app")
    if any(isinstance(f, _RequestIdFilter) for h in logger.handlers for f in h.filters):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"))
    handler.addFilter(_RequestIdFilter())
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def _request_id(request: Request, call_next):
        incoming = request.headers.get(HEADER, "")
        rid = incoming if _VALID.fullmatch(incoming) else uuid.uuid4().hex
        token = request_id_var.set(rid)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers[HEADER] = rid
            return response
        finally:
            ms = (time.perf_counter() - start) * 1000
            level = logging.DEBUG if request.url.path == "/health" else logging.INFO  # 상태 확인은 자주 불려 기본으로 숨긴다
            access_log.log(level, "%s %s %d %.0fms", request.method, request.url.path, status, ms)
            request_id_var.reset(token)
