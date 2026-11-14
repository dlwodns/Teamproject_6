"""ai 서비스 호출 (BE-9, D34 · D47). backend가 ai를 부르는 곳은 여기 한 곳이다.

- 엑사원을 직접 부르지 않는다. 분류 · 명령 해석 · 요약 · 초안은 ai 서비스(`AI_SERVICE_URL`)에 HTTP로만 요청한다(D34 · D41).
- 시각 · ID 변환은 `app/schemas/ai.py`에서 한다: ai 응답 ID(문자열) → 정수, 시각 → 시간대 없는 KST.
- ai가 꺼져 있거나 느려도 backend는 죽지 않는다. 부르는 쪽이 AIError를 받아 처리한다
  (분류: job을 queued로 남김, 명령: "지금은 명령을 처리할 수 없습니다", 구조도 4 · 12절 #17).
- 요청 ID(X-Request-ID)를 ai에 넘겨 두 서비스 로그를 이어 본다(INF-12).
"""
from datetime import datetime
from typing import Any

import httpx
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.request_id import request_id_headers
from app.schemas.ai import ClassifyResult, DraftResult, MemoryExtractResult, PlanResult, PolishResult, SummarizeResult

# 엑사원 1통 약 28초(모든 메일, PC CPU), 명령 해석 첫 호출 70~120초(AI-T8). ai 쪽 제한 120초보다 길게 둔다
TIMEOUT_S = 130.0
CONNECT_S = 5.0
HEALTH_S = 5.0


class AIError(Exception):
    """kind: timeout(제한 시간 넘음) · unavailable(연결 안 됨) · bad_response(오류 응답 · 형식 다름)."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


class AIClient:
    def __init__(self, base_url: str | None = None, *, timeout: float = TIMEOUT_S,
                 transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(base_url=base_url or get_settings().ai_service_url,
                                  timeout=httpx.Timeout(timeout, connect=CONNECT_S), transport=transport)

    def close(self) -> None:
        self._http.close()

    def _post(self, path: str, payload: dict[str, Any], out: type[BaseModel]):
        try:
            r = self._http.post(path, json=jsonable_encoder(payload), headers=request_id_headers())
        except httpx.TimeoutException as e:
            raise AIError("timeout", f"ai {path} 제한 시간 초과") from e
        except httpx.TransportError as e:
            raise AIError("unavailable", f"ai {path} 연결 실패: {type(e).__name__}") from e
        if r.status_code >= 400:
            raise AIError("bad_response", f"ai {path} 응답 {r.status_code}")  # 본문은 남기지 않는다(메일 내용이 섞일 수 있다)
        try:
            return out.model_validate(r.json())
        except (ValueError, ValidationError) as e:
            raise AIError("bad_response", f"ai {path} 응답 형식이 계약과 다름") from e

    def health(self) -> dict[str, Any]:
        """ai 상태. 실패해도 예외 없이 status: down을 돌려준다(헬스 체크 · 대시보드 표시용)."""
        try:
            r = self._http.get("/health", headers=request_id_headers(), timeout=HEALTH_S)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError):
            return {"status": "down"}

    def classify(self, payload: dict[str, Any]) -> ClassifyResult:
        """메일 1통 분류. payload는 구조도 8절 `/classify` 요청 형식(본문은 개인정보를 가린 것만, BE-6)."""
        return self._post("/classify", payload, ClassifyResult)

    def plan(self, text: str, actions: list[dict[str, Any]], *, now: datetime,
             selected_mail_ids: list[int] | None = None, last_result_ids: list[int] | None = None) -> PlanResult:
        """명령 해석. actions는 행동 레지스트리에서 만든 `{id, name, description}` 목록(D47, detail 2.1절)."""
        return self._post("/agent/plan", {
            "text": text, "actions": actions,
            "context": {"now": now, "selected_mail_ids": selected_mail_ids or [], "last_result_ids": last_result_ids or []},
        }, PlanResult)

    def extract_memory(self, payload: dict[str, Any]) -> MemoryExtractResult:
        """문맥 기억 추출(PL-16, BE-D21). 보낸 사람의 담당 업무 · 소속을 근거 문장과 함께 받는다."""
        return self._post("/memory/extract", payload, MemoryExtractResult)

    def summarize(self, payload: dict[str, Any]) -> SummarizeResult:
        return self._post("/summarize", payload, SummarizeResult)

    def draft(self, payload: dict[str, Any]) -> DraftResult:
        return self._post("/draft", payload, DraftResult)

    def polish(self, payload: dict[str, Any]) -> PolishResult:
        """답장 다듬기. payload는 {text, style, mail?} — 개인정보를 가린 것만(BE-6)."""
        return self._post("/polish", payload, PolishResult)


_client: AIClient | None = None


def get_ai_client() -> AIClient:
    """FastAPI Depends용. 연결을 재사용한다. 테스트는 app.dependency_overrides로 가짜를 넣는다."""
    global _client
    if _client is None:
        _client = AIClient()
    return _client
