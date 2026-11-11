"""에이전트 시나리오 평가(eval/scenarios)를 테스트로도 돌린다 (PL-16 5.5절).

실제 서버 대신 TestClient로 같은 HTTP 요청을 보낸다. 시나리오가 하나라도 틀리면 실패한다.
"""
import sys
from pathlib import Path

import pytest

from app.core import clock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval" / "scenarios"))
from runner import load_cases, run_case  # noqa: E402

CASES = load_cases()


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_scenario(client, case):
    def call(method, path, body, headers):
        r = client.request(method, path, json=body, headers=headers or {})
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, r.text

    try:
        res = run_case(case, call)
    finally:
        clock.set_dev_now(None)
    assert res.passed, "\n".join(res.failures)
    assert res.forbidden == 0


def test_cases_exist():
    assert len(CASES) >= 10
