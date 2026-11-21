"""봉인 테스트 C 같은 섞인 세트를 묶음(짧은 · 긴 · 영어 · 일본어 · 스팸)별 × 모델별로 맞대는 표(DE-13 · DE-D33). 모델을 부르지 않는다.

run_dummy.py가 남긴 결과(predictions_*.json)와 처리 시간 파일(timing_*.json)을 모델마다 받아,
정답의 태그로 묶음을 나눠(스팸 · 피싱 → 스팸, 긴메일 → 긴 메일, 영어메일 → 영어, 일본어메일 → 일본어, 나머지 → 짧은 메일)
놓침 · 할 일로 잡음 · 정밀도 · 모든 칸 정답 · 마감 맞음(할 일 단위) · 분류 실패 · 시간 초과 · 처리 시간을 센다.
봉인 세트라 개수만 적는다(메일 번호 · 내용 없음). --csv는 차트용 숫자 표.

    python eval/runners/part_table.py --file <TP6_sealed>/testC/testC_mails.json \\
        "K-EXAONE 2.5=<…>/predictions_testC_exaone-high_mask.json" "Claude Haiku 5.5=<…>/predictions_testC_or-haiku_mask.json" \\
        "DeepSeek V4.1 Flash=<…>/predictions_testC_or-deepseek_mask.json" --md part_table.md --csv part_table.csv
"""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data/dummy"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval import evaluate, load_gold  # noqa: E402  data/dummy/eval.py
import run_dummy  # noqa: E402,F401  ai 경로를 넣는다
from app.core.config import Settings  # noqa: E402

PARTS = ["짧은 메일", "긴 메일", "영어", "일본어", "스팸", "전체"]


def part_of(gold: dict) -> str:
    tags = set(gold.get("tags") or [])
    if tags & {"스팸", "피싱"}:
        return "스팸"
    if "긴메일" in tags:
        return "긴 메일"
    if "영어메일" in tags:
        return "영어"
    if "일본어메일" in tags:
        return "일본어"
    return "짧은 메일"


def measure(mails: list, preds: list, owner: str, timing: list | None, limit: float) -> dict:
    ids = {o["mail"]["id"] for o in mails}
    r = evaluate(mails, preds, owner)
    pos, miss, fp = r["groups"]["있음"]["n"], len(r["wrong_ids"]["있음"]), len(r["wrong_ids"]["없음"])
    found = pos - miss
    t = r["task"]
    secs, timeout, over, failed_calls = [], 0, 0, 0
    for x in timing or []:
        if x["id"] not in ids or x.get("calls") == 0:  # calls 0 = --resume로 앞 실행 출력을 다시 쓴 메일
            continue
        secs.append(x["s"])
        for c in x.get("call", []):
            over += c["s"] > limit
            timeout += c["kind"] == "timeout"
            failed_calls += c["kind"] != "ok"
    secs.sort()
    return dict(n=r["n"], pos=pos, miss=miss, fp=fp, prec=found / (found + fp) if found + fp else None,
                recall=found / pos if pos else None, full=r["full"], due_ok=t["due_ok"], due_n=t["gold"],
                failed=sum(p.get("_source") == "failed" for p in preds if p.get("id") in ids),
                med=secs[len(secs) // 2] if secs else None, max=secs[-1] if secs else None,
                timeout=timeout, over=over, failed_calls=failed_calls, timed=len(secs))


def pct(x):
    return "-" if x is None else f"{x:.1%}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", help="'모델 이름=결과 파일(predictions_*.json)'")
    ap.add_argument("--file", type=Path, required=True, help="세트 정답 파일(봉인 테스트는 레포 밖)")
    ap.add_argument("--limit", type=float, default=Settings.llm_background_timeout_s, help="'N초 넘은 호출' 기준(기본: 서비스 분류 제한 시간)")
    ap.add_argument("--md", type=Path, default=None)
    ap.add_argument("--csv", type=Path, default=None, help="차트용 숫자 표")
    a = ap.parse_args()
    data = json.loads(a.file.read_text(encoding="utf-8"))
    gold, owner = load_gold(str(a.file)), data["mailbox"]["owner"]  # load_gold는 보낸 메일을 뺀다(분류 채점 대상만)
    by_part = {p: [o for o in gold if part_of(o["gold"]) == p] for p in PARTS[:-1]}
    by_part["전체"] = gold
    res = {}
    for spec in a.runs:
        name, _, path = spec.partition("=")
        p = Path(path)
        preds = json.loads(p.read_text(encoding="utf-8"))
        missing = {o["mail"]["id"] for o in gold} - {x.get("id") for x in preds}
        if missing:
            sys.exit(f"{name}: 결과가 {len(missing)}통 비었다 — run_dummy.py --resume으로 끝까지 잰 뒤 다시")
        tp = p.with_name(f"timing_{p.stem}.json")
        timing = json.loads(tp.read_text(encoding="utf-8")) if tp.is_file() else None
        res[name] = {part: measure(by_part[part], preds, owner, timing, a.limit) for part in PARTS}
    names = list(res)
    L = [f"# 묶음별 × 모델 표 · {a.file.name} ({len(gold)}통)", "",
         "- 놓침 = 할 일 메일을 할 일 없음으로 판정(누락, 1순위 D15) · 할 일로 잡음 = 할 일 없는 메일을 할 일로 판정 · 마감 맞음 = 정답 할 일 중 짝지어지고 마감이 분까지 같은 수",
         f"- 시간 초과 · {a.limit:.0f}초 넘음은 호출 수. 처리 시간은 메일 1통(다시 부른 것 포함), 그 실행에서 실제로 부른 메일만. 개수만 적는다(봉인 세트)",
         "", "## 묶음 구성", "", "| 묶음 | 메일 | 할 일 메일 | 정답 할 일 |", "|---|---|---|---|"]
    first = res[names[0]]
    L += [f"| {p} | {first[p]['n']} | {first[p]['pos']} | {first[p]['due_n']} |" for p in PARTS]
    for title, key in [("놓침 ↓(놓친 수/할 일 메일)", lambda m: f"{m['miss']}/{m['pos']}"),
                       ("할 일로 잡음 ↓(할 일 없는 메일 중)", lambda m: f"{m['fp']}/{m['n'] - m['pos']}"),
                       ("할 일 메일 정밀도 ↑", lambda m: pct(m["prec"])),
                       ("모든 칸 정답 ↑", lambda m: f"{m['full']}/{m['n']}"),
                       ("마감 맞음 ↑(할 일 단위)", lambda m: f"{m['due_ok']}/{m['due_n']}" if m["due_n"] else "-"),
                       ("처리 시간 중앙 · 최대", lambda m: f"{m['med']:.1f} · {m['max']:.1f}초" if m["med"] is not None else "-"),
                       ("분류 실패(최종) · 시간 초과 호출", lambda m: f"{m['failed']} · {m['timeout']}")]:
        L += ["", f"## {title}", "", "| 묶음 | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
        L += [f"| {p} | " + " | ".join(key(res[n][p]) for n in names) + " |" for p in PARTS]
    text = "\n".join(L) + "\n"
    print(text)
    if a.md:
        a.md.write_text(text, encoding="utf-8")
    if a.csv:
        with a.csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            cols = ["n", "pos", "miss", "fp", "prec", "recall", "full", "due_ok", "due_n", "failed", "med", "max", "timeout", "over"]
            w.writerow(["model", "part", *cols])
            for n in names:
                for p in PARTS:
                    w.writerow([n, p, *[res[n][p][c] for c in cols]])


if __name__ == "__main__":
    main()
