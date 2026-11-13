"""모델 비교 실험용 외부 API 호출부 (AI-21): OpenRouter · LG K-EXAONE API(api.exaone.ai, OpenAI 형식). eval/에서만 쓴다 — 서비스(ai/ · backend/)에는 넣지 않는다(D26 · D41).

엑사원 호출부(ai/app/llm/client.py)와 같은 모양(chat_json · chat_text · health · model)이라 분류 파이프라인 · 명령 해석에 그대로 꽂힌다.
조건은 엑사원과 맞춘다: temperature 0 · JSON 스키마 강제(response_format json_schema) · 추론(thinking) 끔.
출력 상한은 엑사원의 320토큰 대신 1024토큰이다 — 엑사원 상한은 PC CPU 폭주를 끊으려는 값이고 정상 출력은 그보다 짧다.
키는 OPENROUTER_API_KEY · EXAONE_API_KEY(환경 변수 또는 레포 루트 .env)에서 읽고 로그 · 보고서에 남기지 않는다.
K-EXAONE 2.5(11/9 LG 무료 공개)는 추론 모델이다. 추론을 끄면(enable_thinking=false) 응답이 깨져서(11/11 확인) 켠 채로 돌리고,
추론 토큰까지 들어가도록 출력 상한을 4096으로 둔다. 다른 두 모델은 추론을 끈다 — 보고서에 함께 적는다.
"""
import copy
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

from app.llm.client import LLMError, parse_json

ROOT = Path(__file__).resolve().parents[2]
URL = "https://openrouter.ai/api/v1/chat/completions"
EXAONE_URL = "https://api.exaone.ai/v1/chat/completions"
MAX_TOKENS = 1024
EXAONE_MAX_TOKENS = 4096
# Claude 5 계열(Haiku 5.5)은 OpenRouter에서 temperature를 받지 않는다(supported_parameters, 11/11 확인). 기본 샘플링으로 돈다 —
# 같은 메일을 다시 돌리면 출력이 조금 다를 수 있다(보고서에 적는다)
NO_TEMPERATURE = ("anthropic/claude-haiku-5", "anthropic/claude-sonnet-5", "anthropic/claude-opus-5")


class QuotaExhausted(RuntimeError):
    """하루 호출 한도를 다 썼다(LG 무료 API는 하루 100회, 11/11 응답 머리글로 확인). LLMError가 아니라서 파이프라인이 '분류 실패'로
    삼키지 않고 실행 전체가 멈춘다 — 한도 소진이 모델 오답처럼 점수에 섞이지 않게 한다."""


def api_key(name: str = "OPENROUTER_API_KEY") -> str:
    key = os.environ.get(name, "").strip()
    env = ROOT / ".env"
    if not key and env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                key = line.split("=", 1)[1].split("#")[0].strip()
    if not key:
        raise SystemExit(f"{name}가 없다(.env 또는 환경 변수)")
    return key


def make_client(spec: str) -> "OpenRouterClient":
    """'openrouter:<모델 ID>' 또는 'exaone:<모델 ID>[@추론]'(예: exaone:k-exaone_v2.5, exaone:k-exaone_v2.5@off).
    추론: on(기본) · low(reasoning_effort low) · off(enable_thinking false, 스키마 강제 없이 프롬프트의 JSON 지시만) ·
    offschema(enable_thinking false + 스키마 강제 — 11/11 짧은 시험에서 응답이 깨짐)."""
    kind, _, model = spec.partition(":")
    model, _, think = model.partition("@")
    if kind == "openrouter" and model:
        return OpenRouterClient(model)
    if kind == "exaone" and model:
        if think not in ("", "on", "low", "off", "offschema"):
            raise SystemExit("추론은 on · low · off · offschema")
        c = OpenRouterClient(model, url=EXAONE_URL, key_name="EXAONE_API_KEY", exaone=True)
        c.think = think or "on"
        return c
    raise SystemExit("--model은 openrouter:<모델 ID> 또는 exaone:<모델 ID>")


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """엄격 모드는 객체마다 additionalProperties: false가 필요하다. 엑사원(ollama format)도 스키마 밖 칸은 내지 않으므로 조건이 같다."""
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


class OpenRouterClient:
    def __init__(self, model: str, timeout: float = 180.0, url: str = URL, key_name: str = "OPENROUTER_API_KEY", exaone: bool = False):
        self.model, self._url, self._exaone = model, url, exaone
        self.think = "off"  # OpenRouter 모델은 추론을 끈다. LG API는 make_client가 정한다
        self._http = httpx.Client(timeout=timeout, headers={"Authorization": f"Bearer {api_key(key_name)}",
                                                            "X-Title": "TP6 model compare (eval)"})
        self.last_stats: dict[str, float] = {}
        self.cost = 0.0  # 달러, OpenRouter usage.cost 합
        self.retries = 0  # 429 · 5xx로 다시 부른 횟수
        self.loose = 0  # 추론 off: JSON 뒤에 글이 붙어 첫 객체만 꺼낸 횟수

    def _chat(self, system: str, user: str, schema: dict[str, Any] | None = None) -> str:
        body: dict[str, Any] = {
            "model": self.model, "temperature": 0, "max_tokens": MAX_TOKENS,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "reasoning": {"enabled": False},
            "usage": {"include": True},
        }
        if self.model.startswith(NO_TEMPERATURE):
            del body["temperature"]
        if self._exaone:  # LG API: 추론은 켠 채로(끄면 응답이 깨짐), OpenRouter 전용 칸은 뺀다
            body["max_tokens"] = EXAONE_MAX_TOKENS
            del body["reasoning"], body["usage"]
            if self.think == "low":
                body["reasoning_effort"] = "low"
            elif self.think in ("off", "offschema"):
                body["chat_template_kwargs"] = {"enable_thinking": False}
                body["max_tokens"] = MAX_TOKENS
        if schema is not None and not (self._exaone and self.think == "off"):
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "out", "strict": True, "schema": strict_schema(schema)}}
            if not self._exaone:
                body["provider"] = {"require_parameters": True}  # 스키마 강제를 지원하는 공급자에만 보낸다
        last = None
        for attempt in range(8):  # LG 무료 API는 동시 호출이 많으면 429를 낸다(11/11) — 기다렸다 다시 부른다
            try:
                r = self._http.post(self._url, json=body)
                if r.status_code == 429 and (r.headers.get("x-day-rate-limit-remaining") == "0" or r.headers.get("x-should-retry") == "false"):
                    raise QuotaExhausted(f"하루 호출 한도 소진(x-day-rate-limit {r.headers.get('x-day-rate-limit')}) — 한도가 풀린 뒤 다시 실행")
                if r.status_code in (429, 500, 502, 503, 504):
                    last = f"HTTP {r.status_code}"
                    self.retries += 1
                    wait = r.headers.get("retry-after")
                    time.sleep(min(float(wait), 120) if wait and wait.replace(".", "").isdigit() else 10 * (attempt + 1))
                    continue
                if r.status_code >= 400:
                    raise LLMError(f"api 호출 실패: HTTP {r.status_code} {r.text[:200]}")
                j = r.json()
                u = j.get("usage") or {}
                self.cost += float(u.get("cost") or 0)
                self.last_stats = {"prompt_tokens": u.get("prompt_tokens", 0), "gen_tokens": u.get("completion_tokens", 0),
                                   "reasoning_tokens": u.get("reasoning_tokens") or 0,
                                   "cost": float(u.get("cost") or 0), "provider": j.get("provider")}
                msg = j["choices"][0]["message"]
                if not msg.get("content"):
                    raise LLMError(f"api 빈 응답: finish={j['choices'][0].get('finish_reason')}")
                return msg["content"]
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
                last = type(e).__name__
                time.sleep(2 * (attempt + 1))
        raise LLMError(f"api 호출 실패: {last}")

    def chat_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        text = self._chat(system, user, schema)
        if self._exaone and self.think == "off":  # 스키마 강제 없이: JSON 뒤에 설명을 붙이면 첫 객체만 쓴다(형식 오류 건수는 따로 센다)
            try:
                return parse_json(text)
            except LLMError:
                self.loose += 1
                i = text.find("{")
                try:
                    obj, _ = json.JSONDecoder().raw_decode(text[i:]) if i >= 0 else (None, 0)
                except ValueError:
                    obj = None
                if isinstance(obj, dict):
                    return obj
                raise
        return parse_json(text)

    def chat_text(self, system: str, user: str) -> str:
        return self._chat(system, user).strip()

    def health(self) -> dict[str, Any]:
        return {"reachable": True, "model_ready": True,
                "version": f"{f'LG EXAONE API(추론 {self.think})' if self._exaone else 'openrouter(추론 끔)'} {self.model}"}
