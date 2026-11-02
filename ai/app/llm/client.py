"""엑사원 호출부 (AI-1). ollama `/api/chat`만 쓴다 — 외부 LLM 호출 경로를 두지 않는다(D41).

호출 조건은 10/24 벤치(`eval/bench/exaone_20261024/bench_v2.ps1`의 Call-Model)와 같다:
stream=false · think=false · temperature=0 · format=JSON 스키마.
"""
import json
import re
import time
from typing import Any, Protocol

import httpx

from app.core.config import Settings


class LLMError(RuntimeError):
    """모델 호출 실패 · 응답 형식 오류. 호출한 쪽은 규칙 결과로 대신한다."""


class LLMClient(Protocol):
    model: str

    def chat_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]: ...

    def chat_text(self, system: str, user: str) -> str: ...

    def health(self) -> dict[str, Any]: ...


def parse_json(text: str) -> dict[str, Any]:
    """모델 출력에서 JSON 객체 하나를 꺼낸다. 앞뒤에 설명이 붙은 경우도 처리한다."""
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            raise LLMError("JSON 없음")
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            raise LLMError(f"JSON 파싱 실패: {e}") from e
    if not isinstance(obj, dict):
        raise LLMError("JSON 객체가 아님")
    return obj


class OllamaClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.model = settings.model
        self._http = httpx.Client(base_url=settings.ollama_base_url, timeout=settings.llm_timeout_s, transport=transport)

    def _chat(self, system: str, user: str, fmt: Any = None) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "think": False,
            "options": {"temperature": 0},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if fmt is not None:
            body["format"] = fmt
        try:
            r = self._http.post("/api/chat", json=body)
            r.raise_for_status()
            return r.json()["message"]["content"]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            # 본문 · 프롬프트는 로그 · 오류 메시지에 남기지 않는다(구조도 10절)
            raise LLMError(f"ollama 호출 실패: {type(e).__name__}") from e

    def chat_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        return parse_json(self._chat(system, user, schema))

    def chat_text(self, system: str, user: str) -> str:
        return self._chat(system, user).strip()

    def health(self) -> dict[str, Any]:
        t = time.perf_counter()
        try:
            r = self._http.get("/api/tags", timeout=5)
            r.raise_for_status()
            names = [m.get("name") or m.get("model") for m in r.json().get("models", [])]
        except (httpx.HTTPError, ValueError) as e:
            return {"reachable": False, "model_ready": False, "error": type(e).__name__}
        return {"reachable": True, "model_ready": self.model in names,
                "latency_ms": round((time.perf_counter() - t) * 1000)}


class DisabledClient:
    """LLM_ENABLED=false일 때. 모든 호출이 LLMError → 규칙 결과만 쓴다."""

    def __init__(self, settings: Settings):
        self.model = settings.model

    def chat_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        raise LLMError("LLM 비활성")

    def chat_text(self, system: str, user: str) -> str:
        raise LLMError("LLM 비활성")

    def health(self) -> dict[str, Any]:
        return {"reachable": False, "model_ready": False, "error": "disabled"}


def build_client(settings: Settings) -> LLMClient:
    return OllamaClient(settings) if settings.llm_enabled else DisabledClient(settings)
