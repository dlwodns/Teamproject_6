"""명령 해석 모델 비교 (AI-21): 범위 밖 먼 것(far) 10 · 가까운 것(near) 10 + 정상 대조 10문장.

사용 (레포 루트에서):
  ai/.venv/bin/python eval/runners/compare_commands.py --model openrouter:anthropic/claude-haiku-5.5 --out <폴더>
  scripts/exaone-pc.sh run ai/.venv/bin/python eval/runners/compare_commands.py --exaone --out <폴더>

왜 '모델만' 채점인가: 서비스 경로(plan)는 규칙이 행동을 1개로 정하거나 지원 외가 분명하면 모델을 부르지 않는다(D44).
범위 밖 문장은 대부분 규칙이 먼저 걸러서, 파이프라인으로 재면 모델이 바뀌어도 점수가 같다. 그래서 같은 프롬프트(agent_v1)를
모든 문장에 모델로 직접 보내 모델의 판단만 잰다. 파이프라인 결과(규칙 + 모델)도 함께 적는다.
정상 대조 10문장: 범위 밖만 재면 '전부 거절하는 모델'이 만점을 받으므로, 정상 명령을 실행하는지도 함께 본다.

- far(먼 범위 밖): 메일 업무와 무관한 요청(날씨 · 맛집 · 계산 · 전화 · 회의실 등)
- near(가까운 범위 밖): 메일 관련이지만 14개 행동에 없는 일 + 행동 단어를 넣은 함정 · 부정 · 과거 서술
- 캘린더 등록 문장은 AI-20(T15)으로 지원 범위가 바뀌어 정답이 낡았으므로 넣지 않았다.
"""
import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.agent.plan import plan  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.llm.client import LLMError, build_client  # noqa: E402
from app.prompts import agent_v1  # noqa: E402
from app.schemas.agent import PlanContext, PlanRequest  # noqa: E402
from run_agent_commands import ACTIONS  # noqa: E402

FAR = ["V-087", "V-088", "V-089", "V-090", "V-091", "V-092", "D-119", "E-115", "E-111", "D-114"]
NEAR = ["V-071", "V-072", "V-076", "V-084", "V-085", "V-093", "V-094", "V-095", "V-096", "V-097"]
NORMAL_N = 10  # v4 정상 문장에서 행동이 겹치지 않게 앞에서부터


def load_rows() -> list[dict]:
    rows = {}
    for v in (2, 3, 4):
        for ln in (ROOT / f"eval/datasets/agent_commands_v{v}.jsonl").read_text(encoding="utf-8").splitlines():
            if ln.strip():
                r = json.loads(ln)
                rows[r["id"]] = r
    normal, seen = [], set()
    for r in rows.values():
        if r["id"].startswith("V-") and r["type"] == "정상" and r["sub"] not in seen and len(normal) < NORMAL_N:
            seen.add(r["sub"])
            normal.append(dict(r, group="정상 대조"))
    return [dict(rows[i], group="far") for i in FAR] + [dict(rows[i], group="near") for i in NEAR] + normal


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--model", help="openrouter:<모델 ID> · exaone:k-exaone_v2.5")
    g.add_argument("--exaone", action="store_true", help="엑사원(ollama · PC 터널)")
    ap.add_argument("--out", type=Path, required=True, help="결과 폴더(레포 밖 권장)")
    a = ap.parse_args()
    if a.model:
        from openrouter import make_client
        llm = make_client(a.model)
        name = a.model.split(":", 1)[1].split("/")[-1]
    else:
        llm = build_client(replace(get_settings(), llm_enabled=True))
        if not llm.health().get("model_ready"):
            sys.exit("엑사원 준비 안 됨(PC 터널 확인: scripts/exaone-pc.sh check)")
        name = "exaone"

    system, schema = agent_v1.render_system(ACTIONS), agent_v1.schema(ACTIONS)
    results = []
    for r in load_rows():
        ctx = PlanContext(now=r["now"], selected_mail_ids=r.get("selected_mail_ids", []), last_result_ids=r.get("last_result_ids", []))
        exp = r["expected"].get("action")
        t = time.perf_counter()
        try:
            raw = llm.chat_json(system, agent_v1.render_user(r["text"], ctx), schema).get("action")
        except LLMError as e:
            raw = f"실패: {str(e)[:60]}"
        sec = time.perf_counter() - t
        pipe = plan(PlanRequest(text=r["text"], actions=ACTIONS, context=ctx), llm)
        if exp is None:  # 범위 밖: 실행 행동을 내지 않으면 성공. reason까지 맞는지는 따로
            ok = raw in ("unsupported", "ambiguous")
            reason_ok = raw == r["expected"].get("reason")
        else:
            ok = reason_ok = raw == exp
        results.append({"id": r["id"], "group": r["group"], "text": r["text"], "expected": exp or r["expected"].get("reason"),
                        "model": raw, "ok": ok, "reason_ok": reason_ok, "sec": round(sec, 2),
                        "pipeline": pipe.action or pipe.reason, "pipeline_source": pipe.source})

    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / f"commands_{name}.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    L = [f"# 명령 해석 모델 비교 · {name}", "", f"- 프롬프트 {agent_v1.PROMPT_VERSION} · 모델만 채점(규칙 없이 모든 문장을 모델에 보냄)", ""]
    L += ["| 묶음 | 문장 | 모델 판단 맞음 | reason까지 맞음 | 파이프라인(규칙+모델) 맞음 |", "|---|---|---|---|---|"]
    for grp in ("far", "near", "정상 대조"):
        g = [x for x in results if x["group"] == grp]
        pipe_ok = sum((x["pipeline"] == x["expected"]) if grp == "정상 대조" else (x["pipeline"] in ("unsupported", "ambiguous")) for x in g)
        L.append(f"| {grp} | {len(g)} | {sum(x['ok'] for x in g)}/{len(g)} | {sum(x['reason_ok'] for x in g)}/{len(g)} | {pipe_ok}/{len(g)} |")
    L += ["", f"- 문장 1개 평균 {sum(x['sec'] for x in results) / len(results):.1f}초"
          + (f" · 비용 ${llm.cost:.4f}" if hasattr(llm, "cost") else ""), "", "## 틀린 문장", "",
          "| ID | 묶음 | 지시 | 정답 | 모델 |", "|---|---|---|---|---|"]
    L += [f"| {x['id']} | {x['group']} | {x['text']} | {x['expected']} | {x['model']} |" for x in results if not x["ok"]]
    (a.out / f"commands_{name}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[4:9]))


if __name__ == "__main__":
    main()
