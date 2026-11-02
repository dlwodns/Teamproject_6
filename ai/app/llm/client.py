"""엑사원 호출부 (AI-1). 로컬 실행기만 부른다 — 외부 LLM 호출 경로를 두지 않는다(D41).

- ollama `/api/chat` (기본, `LLM_BACKEND=ollama`). `OLLAMA_UDS`가 있으면 Unix 소켓으로 부른다(PC 엑사원 터널)
- llama.cpp `llama-server`의 OpenAI 형식 `/v1/chat/completions` (`LLM_BACKEND=llamacpp`). GGUF 파일을 직접 띄울 때

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


def ollama_stats(j: dict[str, Any]) -> dict[str, float]:
    """ollama 응답의 시간 칸(나노초)을 초 · 토큰 수로 바꾼다. 느린 원인이 로딩 · 입력 읽기 · 출력 생성 중 어디인지 가른다.
    prompt_tokens는 프리픽스 캐시로 다시 읽지 않은 토큰까지 센다(11/3 실측) — 초당 토큰은 prompt_s 쪽으로 판단한다."""
    ns = 1e9
    return {"load_s": j.get("load_duration", 0) / ns,
            "prompt_tokens": j.get("prompt_eval_count", 0), "prompt_s": j.get("prompt_eval_duration", 0) / ns,
            "gen_tokens": j.get("eval_count", 0), "gen_s": j.get("eval_duration", 0) / ns}


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
        self._keep_alive = settings.ollama_keep_alive
        self._pin = {"digest": settings.model_digest, "version": settings.ollama_version}
        self._pin_ok = not any(self._pin.values())  # 고정값이 없으면 확인하지 않는다
        if transport is None and settings.ollama_uds:
            transport = httpx.HTTPTransport(uds=settings.ollama_uds)
        self._http = httpx.Client(base_url=settings.ollama_base_url, timeout=settings.llm_timeout_s, transport=transport)
        self.last_stats: dict[str, float] = {}  # 마지막 호출의 시간 내역(평가 실행기가 읽는다)

    def _inspect(self) -> dict[str, Any]:
        """올라간 모델의 digest · ollama 버전을 읽어 고정값과 비교한다."""
        r = self._http.get("/api/tags", timeout=5)
        r.raise_for_status()
        m = next((m for m in r.json().get("models", []) if (m.get("name") or m.get("model")) == self.model), None)
        got = {"digest": m.get("digest") if m else None,
               "version": self._http.get("/api/version", timeout=5).json().get("version")}
        return {**got, "found": m is not None,
                "pin_mismatch": [k for k, v in self._pin.items() if v and got[k] != v]}

    def _ensure_pinned(self) -> None:
        if self._pin_ok:
            return
        try:
            info = self._inspect()
        except (httpx.HTTPError, ValueError) as e:
            raise LLMError(f"ollama 호출 실패: {type(e).__name__}") from e
        if info["pin_mismatch"]:  # 다른 모델 · 버전으로 낸 결과가 고정 모델 결과처럼 남지 않게 한다
            raise LLMError(f"ollama 호출 실패: 고정값과 다름 {info['pin_mismatch']}")
        self._pin_ok = True

    def _chat(self, system: str, user: str, fmt: Any = None) -> str:
        self._ensure_pinned()
        body: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "think": False,
            "keep_alive": self._keep_alive,
            "options": {"temperature": 0},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if fmt is not None:
            body["format"] = fmt
        try:
            r = self._http.post("/api/chat", json=body)
            r.raise_for_status()
            j = r.json()
            self.last_stats = ollama_stats(j)
            return j["message"]["content"]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            self._pin_ok = not any(self._pin.values())  # 터널이 다시 붙으면 PC 쪽 모델이 바뀌었을 수 있어 다시 확인한다
            # 본문 · 프롬프트는 로그 · 오류 메시지에 남기지 않는다(구조도 10절)
            raise LLMError(f"ollama 호출 실패: {type(e).__name__}") from e

    def chat_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        return parse_json(self._chat(system, user, schema))

    def chat_text(self, system: str, user: str) -> str:
        return self._chat(system, user).strip()

    def warm(self, system: str | None = None) -> None:
        """모델을 메모리에 올리고(프롬프트 없는 /api/generate), system을 주면 그 시스템 프롬프트까지 미리 읽힌다.
        PC CPU는 새 입력을 초당 약 12토큰 읽어 분류 시스템 프롬프트(약 950토큰)만 80초다(11/3 실측). 미리 읽어 두면
        첫 메일부터 ollama 프리픽스 캐시가 맞아 메일마다 바뀌는 부분만 읽는다 — 첫 메일이 제한 시간에 걸리지 않게 한다."""
        try:
            self._http.post("/api/generate", json={"model": self.model, "keep_alive": self._keep_alive})
            if system:
                self._http.post("/api/chat", json={
                    "model": self.model, "stream": False, "think": False, "keep_alive": self._keep_alive,
                    "options": {"temperature": 0, "num_predict": 1},
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": ""}]})
        except httpx.HTTPError:
            pass  # 터널이 꺼져 있어도 서비스는 뜬다. 첫 호출이 대신 올린다

    def health(self) -> dict[str, Any]:
        t = time.perf_counter()
        try:
            info = self._inspect()
        except (httpx.HTTPError, ValueError) as e:
            return {"reachable": False, "model_ready": False, "error": type(e).__name__}
        return {"reachable": True, "model_ready": info["found"] and not info["pin_mismatch"],
                "version": info["version"], "digest": info["digest"], "pin_mismatch": info["pin_mismatch"],
                "latency_ms": round((time.perf_counter() - t) * 1000)}


class LlamaCppClient:
    """llama-server 하나에 모델 하나가 올라가 있다. model 값은 보고용 이름이고 서버는 무시한다."""

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.model = settings.model
        self._http = httpx.Client(base_url=settings.llamacpp_base_url, timeout=settings.llm_timeout_s, transport=transport)

    def _chat(self, system: str, user: str, schema: Any = None) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "temperature": 0,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if schema is not None:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "out", "schema": schema}}
        try:
            r = self._http.post("/v1/chat/completions", json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise LLMError(f"llama.cpp 호출 실패: {type(e).__name__}") from e

    def chat_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        return parse_json(self._chat(system, user, schema))

    def chat_text(self, system: str, user: str) -> str:
        return self._chat(system, user).strip()

    def health(self) -> dict[str, Any]:
        t = time.perf_counter()
        try:
            r = self._http.get("/health", timeout=5)  # 모델 로딩 중이면 503
            served = [m.get("id") for m in self._http.get("/v1/models", timeout=5).json().get("data", [])] \
                if r.status_code == 200 else []
        except (httpx.HTTPError, ValueError) as e:
            return {"reachable": False, "model_ready": False, "error": type(e).__name__}
        return {"reachable": True, "model_ready": r.status_code == 200, "served": served,
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
    if not settings.llm_enabled:
        return DisabledClient(settings)
    return LlamaCppClient(settings) if settings.llm_backend == "llamacpp" else OllamaClient(settings)
