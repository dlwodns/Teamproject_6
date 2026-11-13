"""에이전트 시나리오 평가를 실제 서버에 돌린다 (PL-16 5.5절).

    # 1) 시나리오 전용 DB로 backend를 띄운다(load가 테이블을 지우므로 ax.db · demo.db에서는 켜지지 않는다)
    cd backend && APP_MODE=dev DATABASE_URL=sqlite:///./scenario.db .venv/bin/uvicorn app.main:app --port 8000
    # 2) 다른 창에서
    backend/.venv/bin/python eval/scenarios/run_scenarios.py --base-url http://localhost:8000
    backend/.venv/bin/python eval/scenarios/run_scenarios.py --only SC-01 SC-07 --out <결과.json>

시연 서버 · 배포 서버(INF)에도 --base-url만 바꿔 같은 시나리오를 돌린다.
"""
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runner import load_cases, run_case, summarize  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--user-id", type=int, default=1, help="X-User-Id 헤더 값(운영 모드 서버용)")
    ap.add_argument("--out", help="결과 JSON 저장 경로")
    args = ap.parse_args()

    client = httpx.Client(base_url=args.base_url.rstrip("/"), timeout=30)

    def call(method, path, body, headers):
        r = client.request(method, path, json=body, headers={"X-User-Id": str(args.user_id), **(headers or {})})
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, r.text

    try:
        results = [run_case(c, call) for c in load_cases(args.only)]
    finally:
        call("POST", "/api/dev/scenario/clock", {"now": None}, None)  # 서버 시각을 실제 시각으로 돌려 둔다
    print(summarize(results))
    if args.out:
        Path(args.out).write_text(json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
