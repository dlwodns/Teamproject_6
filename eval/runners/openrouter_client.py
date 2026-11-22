"""오픈라우터 모델 클라이언트 — 평가 전용(DE-D24). 서비스 경로(ai/)에는 두지 않는다(D26 · D41).

run_dummy.py --or <모델 ID>가 쓴다. ai 파이프라인의 LLMClient 모양(chat_json · chat_text · health · model)을 따른다.
키는 환경 변수 OPENROUTER_API_KEY, 없으면 레포 맨 위 .env(깃에 안 올라감)에서 읽는다. 키를 출력 · 보고서에 적지 않는다.
호출 조건은 엑사원과 맞춘다: stream 없음 · temperature 0 · JSON 스키마 응답. 생각(reasoning)은 낮게 하고 응답에서 뺀다.
"""
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from app.llm.client import LLMError, parse_json

ROOT = Path(__file__).resolve().parents[2]
BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")  # 시험용으로만 바꾼다
# 출력 상한(추론 토큰 포함). 분류 JSON은 수백 토큰. 11/22 FINAL TEST에서 Gemma 4 26B A4B가 평균 1,940토큰을 써 2,000에 닿아 빈 답이 났다(DE-D33 7번)
# → OPENROUTER_MAX_TOKENS로 바꿔 잰다. 기본(2,000)이 아니면 결과 이름에 -cap<N>이 붙어 다른 상한의 결과와 섞이지 않는다
MAX_TOKENS = int(os.environ.get("OPENROUTER_MAX_TOKENS", "2000"))
# 메일마다 되풀이해도 소용없는 오류는 바로 멈춘다. 그대로 두면 전부 규칙 결과로 대신해 '모델 점수'처럼 보인다(11/7 dev4 402)
STOP = {401: "키 거절(HTTP 401) — 오픈라우터 Keys에서 키가 켜져 있는지 보고 .env의 키를 바꾼다",
        402: "크레딧 부족(HTTP 402) — 오픈라우터 Credits에서 충전한 뒤 다시 실행한다(키 한도와 계정 잔액은 다르다)",
        403: "거절(HTTP 403) — 키 권한 · 모델 접근 설정을 확인한다"}


def load_key() -> str:
    """OPENROUTER_API_KEY: 환경 변수 → 레포 맨 위 .env 순서. 없으면 빈 글자."""
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    env = ROOT / ".env"
    if not key and env.is_file():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "OPENROUTER_API_KEY":
                key = value.split("#")[0].strip().strip("'\"")
    return key


class OpenRouterClient:
    """오픈라우터 OpenAI 형식 /chat/completions. JSON 스키마를 못 받는 경로면 json_object → 형식 지정 없음 순서로 한 번씩 낮춘다."""

    def __init__(self, model: str, key: str, timeout: float = 120.0, transport: httpx.BaseTransport | None = None):
        if not key:
            raise LLMError("OPENROUTER_API_KEY 없음 — 레포 맨 위 .env에 넣는다(.env.example 참고)")
        self.model = model
        self.last_stats: dict = {}  # 엑사원 시간 내역(로딩 · 입력 읽기)은 없다 → 보고서 시간 내역 표를 건너뛴다
        self.usage: list[dict] = []  # 호출마다 토큰 · 비용(달러)
        self._format, self._retry, self._calls = "json_schema", 0, 0
        self.format_changes: list[str] = []  # 응답 형식을 낮춘 기록(몇 번째 호출 · 무엇에서 무엇으로 · HTTP 상태). 보고서 호출 표에 적는다
        self._http = httpx.Client(base_url=BASE_URL, timeout=timeout, transport=transport, headers={
            "Authorization": f"Bearer {key}", "X-Title": "TP6 eval (data)"})

    def _body(self, system: str, user: str, schema: Any) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model, "stream": False, "temperature": 0, "max_tokens": MAX_TOKENS,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "reasoning": {"effort": "low", "exclude": True}, "usage": {"include": True}}
        if schema is not None and self._format == "json_schema":
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "out", "schema": schema}}
        elif schema is not None and self._format == "json_object":
            body["response_format"] = {"type": "json_object"}
        return body

    def _chat(self, system: str, user: str, schema: Any = None) -> str:
        self._calls += 1
        while True:
            try:
                r = self._http.post("/chat/completions", json=self._body(system, user, schema))
            except httpx.HTTPError as e:
                raise LLMError(f"오픈라우터 호출 실패: {type(e).__name__}") from e
            if r.status_code in STOP:
                sys.exit(f"오픈라우터 {STOP[r.status_code]}. 결과 파일은 쓰지 않았다")
            if r.status_code == 429 and self._retry < 3:  # 잠깐 몰림: 조금 쉬었다 다시
                self._retry += 1
                time.sleep(5 * self._retry)
                continue
            self._retry = 0
            if r.status_code in (400, 404, 422) and schema is not None and self._format != "none":
                old, self._format = self._format, "json_object" if self._format == "json_schema" else "none"  # 형식 지정을 낮춰 다시
                self.format_changes.append(f"{self._calls}번째 호출 {old} → {self._format}(HTTP {r.status_code})")  # 이후 호출도 낮은 형식 그대로
                continue
            if r.status_code != 200:
                raise LLMError(f"오픈라우터 호출 실패: HTTP {r.status_code}")
            try:
                j = r.json()
                if j.get("error"):
                    raise LLMError(f"오픈라우터 호출 실패: {str(j['error'].get('code', '오류'))}")
                u = j.get("usage") or {}
                self.usage.append({"prompt_tokens": u.get("prompt_tokens", 0), "completion_tokens": u.get("completion_tokens", 0),
                                   "cost": float(u.get("cost") or 0)})
                return j["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError, ValueError, TypeError) as e:
                raise LLMError(f"오픈라우터 응답 형식 오류: {type(e).__name__}") from e

    def chat_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        return parse_json(self._chat(system, user, schema))

    def chat_text(self, system: str, user: str) -> str:
        return self._chat(system, user).strip()

    def health(self) -> dict[str, Any]:
        """키가 맞는지(/key) · 모델 ID가 있는지(/models). 남은 크레딧 한도도 돌려준다."""
        t = time.perf_counter()
        try:
            k = self._http.get("/key", timeout=10)
            if k.status_code != 200:
                return {"reachable": True, "model_ready": False, "error": f"키 확인 실패 HTTP {k.status_code}"}
            ids = {m.get("id") for m in self._http.get("/models", timeout=20).json().get("data", [])}
        except (httpx.HTTPError, ValueError) as e:
            return {"reachable": False, "model_ready": False, "error": type(e).__name__}
        info = k.json().get("data", {})
        balance = None
        try:  # 계정 잔액(충전액 - 사용액). 키 한도(limit_remaining)와 다르다
            c = self._http.get("/credits", timeout=10)
            if c.status_code == 200:
                d = c.json().get("data", {})
                balance = round(float(d.get("total_credits", 0)) - float(d.get("total_usage", 0)), 4)
        except (httpx.HTTPError, ValueError, TypeError):
            pass
        err = None if self.model in ids else "모델 ID 없음"  # 잔액(/credits)은 조직 키 등에서 다르게 보일 수 있어 막지 않고 알리기만 한다. 진짜 판단은 첫 호출(402면 멈춤)
        return {"reachable": True, "model_ready": err is None, "error": err, "balance": balance,
                "limit_remaining": info.get("limit_remaining"), "latency_ms": round((time.perf_counter() - t) * 1000)}

    def format_text(self) -> str:
        """보고서 '응답 형식' 칸. 한 번 낮추면 그 실행이 끝날 때까지 낮은 형식으로 돈다."""
        if not self.format_changes:
            return "json_schema 그대로"
        return " · ".join(self.format_changes) + " — 이후 호출은 낮춘 형식"

    def cost_text(self) -> str:
        n = len(self.usage)
        if not n:
            return "기록 없음"
        p, c = sum(x["prompt_tokens"] for x in self.usage), sum(x["completion_tokens"] for x in self.usage)
        return f"{n}회 · 입력 {p:,} · 출력 {c:,} 토큰 · 비용 약 ${sum(x['cost'] for x in self.usage):.4f}"
