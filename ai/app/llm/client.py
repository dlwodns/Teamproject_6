"""엑사원 호출부 (AI-1 · AI-22). 설정값 `LLM_BACKEND` 하나로 실행기를 바꿔 끼운다(D52). 엑사원 말고 다른 외부 모델은 부르지 않는다(D53).

- 엑사원 API `/v1/chat/completions` (기본, `LLM_BACKEND=exaone_api`). K-EXAONE 2.5, OpenAI 호환 형식(docs.exaone.ai)
- ollama `/api/chat` (`LLM_BACKEND=ollama`, 로컬 옵션). `OLLAMA_UDS`가 있으면 Unix 소켓으로 부른다(PC 엑사원 터널)
- llama.cpp `llama-server`의 OpenAI 형식 `/v1/chat/completions` (`LLM_BACKEND=llamacpp`). GGUF 파일을 직접 띄울 때

로컬 호출 조건은 10/24 벤치(`eval/bench/exaone_20261024/bench_v2.ps1`의 Call-Model)와 같다:
stream=false · think=false · temperature=0 · format=JSON 스키마. API 조건은 `ExaoneApiClient` 설명에 있다.
"""
import copy
import json
import re
import time
from typing import Any, Protocol

import httpx

from app.core.config import Settings


class LLMError(RuntimeError):
    """모델 호출 실패 · 응답 형식 오류. 호출한 쪽은 규칙 결과로 대신한다."""


class LLMAuthError(LLMError):
    """엑사원 API 키가 없거나 거절됐다(설정 문제). 메일 · 명령 탓이 아니므로 backend는 시도 횟수에 세지 않고 키를 고칠 때까지 기다린다."""


class LLMQuotaError(LLMError):
    """엑사원 API 하루 호출 한도를 다 썼다. 서비스는 다른 실패처럼 규칙 결과로 대신하고, 평가 실행기는 이것을 보고 실행을 멈춘다
    (한도 소진이 모델 오답처럼 점수에 섞이지 않게)."""


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


MAX_OUTPUT_TOKENS = 320  # 관측 최대 약 150토큰의 2배. PC CPU 초당 약 4토큰 → 상한까지 가도 약 80초로 제한 시간(120초) 안에서 끊긴다


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
            # num_predict: 출력 상한. 관측 최대(메일 1통 약 150토큰)보다 넉넉해 정상 출력은 같고, 같은 말을 되풀이하는 폭주만 끊는다
            "options": {"temperature": 0, "num_predict": MAX_OUTPUT_TOKENS},
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


API_MAX_TOKENS = 4096  # 추론 토큰도 이 상한에 들어간다(docs.exaone.ai). 11-11 실측 추론 평균 532 · 분류 JSON 수백 토큰
API_RETRY_STATUS = (429, 500, 502, 503, 504)  # 429는 하루 한도가 아니면 서버 전체 혼잡이다(11-13 실측 "concurrent requests"). 잠깐 쉬고 다시


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """엄격 모드는 객체마다 additionalProperties: false가 필요하다. ollama format도 스키마 밖 칸은 내지 않으므로 조건이 같다."""
    s = copy.deepcopy(schema)

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                node.setdefault("additionalProperties", False)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(s)
    return s


class ExaoneApiClient:
    """엑사원 API(K-EXAONE 2.5). 공식 문서 docs.exaone.ai(11-09 게시)와 11-11 · 11-13 실측을 따른다.

    - 추론은 늘 켜져 있다(끌 수 없음). 강도는 `EXAONE_REASONING_EFFORT`(low · high · max), 비우면 API 기본 max
    - temperature 0 · JSON 스키마 강제(response_format json_schema strict). 스키마 강제는 문서 요청 표에 없지만 실측에서 동작했다
      (11-11 40통 JSON 오류 0). 거절(400 · 422)되면 그 뒤로는 강제 없이 프롬프트의 JSON 지시만으로 받는다
    - 하루 호출 한도(기본 100회, docs.exaone.ai FAQ)를 다 쓰면 `LLMQuotaError`. 서버 혼잡 429 · 5xx는 제한 시간 안에서만 다시 부른다
    - `LLM_TIMEOUT_S`는 다시 부르기까지 합친 한 번의 호출 전체 시간이다. backend가 ai를 기다리는 130초보다 짧아야 한다
    - 본문 · 프롬프트 · 키는 로그 · 오류 메시지에 남기지 않는다(구조도 10절)
    """

    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None, sleep=time.sleep):
        self.model = settings.exaone_api_model
        self._key = settings.exaone_api_key
        self._effort = settings.exaone_reasoning_effort
        self._timeout = settings.llm_timeout_s
        self._schema_ok = True  # 스키마 강제를 거절당하면 False
        self._sleep = sleep
        self._http = httpx.Client(base_url=settings.exaone_api_base_url, timeout=settings.llm_timeout_s, transport=transport,
                                  headers={"Authorization": f"Bearer {self._key}"})
        self.last_stats: dict[str, float] = {}  # 마지막 호출의 토큰 수(평가 실행기가 읽는다)
        self.day_limit: dict[str, str | None] = {"limit": None, "remaining": None}  # 마지막 응답 머리글의 하루 한도
        self.quota_exhausted = False
        self.retries = 0

    def _body(self, system: str, user: str, schema: Any) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model, "stream": False, "temperature": 0, "max_tokens": API_MAX_TOKENS,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if self._effort:
            body["reasoning_effort"] = self._effort
        if schema is not None and self._schema_ok:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "out", "strict": True, "schema": strict_schema(schema)}}
        return body

    def _read_limit(self, r: httpx.Response) -> None:
        if "x-day-rate-limit-remaining" in r.headers:
            self.day_limit = {"limit": r.headers.get("x-day-rate-limit"), "remaining": r.headers.get("x-day-rate-limit-remaining")}

    def _chat(self, system: str, user: str, schema: Any = None) -> str:
        if not self._key:
            raise LLMAuthError("엑사원 API 호출 실패: EXAONE_API_KEY 없음(.env)")
        deadline = time.monotonic() + self._timeout
        attempt = 0
        while True:
            try:
                r = self._http.post("/chat/completions", json=self._body(system, user, schema),
                                    timeout=max(deadline - time.monotonic(), 1.0))
            except httpx.HTTPError as e:
                raise LLMError(f"엑사원 API 호출 실패: {type(e).__name__}") from e
            self._read_limit(r)
            if r.status_code == 429 and (self.day_limit["remaining"] == "0" or r.headers.get("x-should-retry") == "false"):
                self.quota_exhausted = True
                raise LLMQuotaError(f"엑사원 API 하루 호출 한도 소진(x-day-rate-limit {self.day_limit['limit']})")
            if r.status_code in API_RETRY_STATUS:
                attempt += 1
                wait = r.headers.get("retry-after")
                wait_s = min(float(wait), 30.0) if wait and wait.replace(".", "", 1).isdigit() else 3.0 * attempt
                if attempt > 3 or time.monotonic() + wait_s >= deadline:
                    raise LLMError(f"엑사원 API 호출 실패: HTTP {r.status_code}(다시 부르기 {attempt - 1}회)")
                self.retries += 1
                self._sleep(wait_s)
                continue
            if r.status_code in (400, 422) and schema is not None and self._schema_ok:
                self._schema_ok = False  # 이 클라이언트가 사는 동안 강제 없이. parse_json이 앞뒤 글을 걷어 낸다
                continue
            if r.status_code == 401:
                raise LLMAuthError("엑사원 API 호출 실패: 키 거절(HTTP 401) — 키가 틀렸거나 30일 유효기간이 지났다")
            if r.status_code != 200:
                raise LLMError(f"엑사원 API 호출 실패: HTTP {r.status_code}")
            self.quota_exhausted = False
            try:
                j = r.json()
                choice = j["choices"][0]
                content = (choice["message"].get("content") or "").strip()  # 답 앞에 줄바꿈이 붙을 수 있다(docs.exaone.ai)
            except (KeyError, IndexError, ValueError, TypeError, AttributeError) as e:
                raise LLMError(f"엑사원 API 응답 형식 오류: {type(e).__name__}") from e
            u = j.get("usage") or {}
            self.last_stats = {"prompt_tokens": u.get("prompt_tokens") or 0, "gen_tokens": u.get("completion_tokens") or 0,
                               "reasoning_tokens": u.get("reasoning_tokens") or 0, "cost": 0.0}
            if not content:
                raise LLMError(f"엑사원 API 빈 응답: finish={choice.get('finish_reason')}")
            return content

    def chat_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        return parse_json(self._chat(system, user, schema))

    def chat_text(self, system: str, user: str) -> str:
        return self._chat(system, user)

    def health(self) -> dict[str, Any]:
        """API를 부르지 않는다(하루 한도를 아낀다). 키가 있는지와 마지막 호출에서 본 하루 한도만 알린다."""
        ready = bool(self._key) and not self.quota_exhausted
        out: dict[str, Any] = {"reachable": None, "model_ready": ready, "backend": "exaone_api",
                               "version": f"엑사원 API {self.model}(추론 {self._effort or '기본 max'})",
                               "day_limit": self.day_limit}
        if not self._key:
            out["error"] = "EXAONE_API_KEY 없음"
        elif self.quota_exhausted:
            out["error"] = "하루 호출 한도 소진"
        return out


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
    if settings.llm_backend == "ollama":
        return OllamaClient(settings)
    if settings.llm_backend == "llamacpp":
        return LlamaCppClient(settings)
    return ExaoneApiClient(settings)  # 기본(D52)
