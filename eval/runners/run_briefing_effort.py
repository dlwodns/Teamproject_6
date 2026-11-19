"""요약 · 회고 머리 문장 추론 강도 측정(AI-29, io_spec 3.5절: 세 종류 강도 하나로 고정, 후보 low · high).

입력: dump_briefing_payloads.py가 만든 eval/reports/briefing_payloads.json(서비스가 보내는 요청 그대로, 개인정보 가림).
조건마다 ai 서비스 함수(app.agent.assist.summarize)를 엑사원 API로 부른다. 제한 시간 600초 · 출력 상한 16,384(서비스와 같다).
  python eval/runners/run_briefing_effort.py --efforts low high --repeat 2      # ai/.venv 파이썬, 레포 루트
판정(코드): 모델 문장 채택(검증 통과) 비율이 높은 강도 → 같으면 낮은 강도(빠르고 한도를 덜 쓴다). 문장은 보고서에서 사람이 읽는다.
결과: eval/reports/briefing_effort.json · .md
"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai"))

from app.agent.assist import summarize  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.llm.client import Timed, build_client  # noqa: E402
from app.prompts import assist_v4  # noqa: E402
from app.schemas.assist import SummarizeRequest  # noqa: E402

IN = ROOT / "eval/reports/briefing_payloads.json"
OUT = ROOT / "eval/reports/briefing_effort"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--efforts", nargs="+", default=["low", "high"])
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--input", type=Path, default=IN)
    args = ap.parse_args()
    cases = json.loads(args.input.read_text(encoding="utf-8"))
    base = build_client(get_settings())

    def one(job):
        case, effort, rep = job
        llm = Timed(base, assist_v4.SUMMARY_TIMEOUT_S, effort)
        t0 = time.monotonic()
        r = summarize(SummarizeRequest.model_validate(case["payload"]), llm)
        return {"id": case["id"], "effort": effort, "rep": rep, "seconds": round(time.monotonic() - t0, 1),
                "source": r.source, "fallback": r.fallback, "chars": len(r.text), "text": r.text}

    jobs = [(c, e, k) for c in cases for e in args.efforts for k in range(args.repeat)]
    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(one, jobs))
    OUT.with_suffix(".json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    md = [f"# 요약 · 회고 머리 문장 강도 측정 ({assist_v4.PROMPT_VERSION}, {base.model})", "",
          "| 강도 | 모델 문장 채택 | 처리 시간 중앙(초) | 평균 글자 수 |", "|---|---|---|---|"]
    for e in args.efforts:
        rs = [r for r in rows if r["effort"] == e]
        secs = sorted(r["seconds"] for r in rs)
        ok = sum(r["source"] == "exaone" for r in rs)
        md.append(f"| {e} | {ok}/{len(rs)} | {secs[len(secs) // 2]} | {sum(r['chars'] for r in rs) // max(len(rs), 1)} |")
    md += ["", "## 조건별 결과", ""]
    for r in rows:
        md.append(f"- `{r['id']}` · {r['effort']} · {r['rep'] + 1}회 · {r['source']} · {r['seconds']}초"
                  + (f" · 사유: {r['fallback']}" if r["fallback"] else "") + f"\n  > {r['text']}")
    OUT.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[:2 + 2 + len(args.efforts)]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
