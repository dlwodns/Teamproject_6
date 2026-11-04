import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.deps import llm_dep
from app.llm.client import LLMError
from app.main import app


class FakeLLM:
    """엑사원 대신 쓰는 테스트용 클라이언트. replies에 넣은 응답을 차례로 돌려준다."""

    model = "fake-exaone"

    def __init__(self, replies: list[Any] | None = None):
        self.replies = list(replies or [])
        self.calls: list[dict[str, Any]] = []

    def _next(self, kind: str, system: str, user: str):
        self.calls.append({"kind": kind, "system": system, "user": user})
        if not self.replies:
            raise LLMError("fake: 응답 없음")
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def chat_json(self, system, user, schema):
        r = self._next("json", system, user)
        return r if isinstance(r, dict) else json.loads(r)

    def chat_text(self, system, user):
        return self._next("text", system, user)

    def health(self):
        return {"reachable": True, "model_ready": True}


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def client(fake_llm):
    app.dependency_overrides[llm_dep] = lambda: fake_llm
    yield TestClient(app)
    app.dependency_overrides.clear()
