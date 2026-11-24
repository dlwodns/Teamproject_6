"""FINAL TEST(final-v1) 같은 섞인 세트를 묶음(짧은 · 긴 · 영어 · 일본어 · 스팸)별 × 모델별로 맞대는 표(DE-13 · DE-D33). 모델을 부르지 않는다.

run_dummy.py가 남긴 결과(predictions_*.json)와 처리 시간 파일(timing_*.json)을 모델마다 받아,
정답의 태그로 묶음을 나눠(스팸 · 피싱 → 스팸, 긴메일 → 긴 메일, 영어메일 → 영어, 일본어메일 → 일본어, 나머지 → 짧은 메일)
묶음마다 모델 × 지표 표를 그린다(지금까지 PR · scores.md의 모델 맞대기 표와 같은 칸, 10절 표 2):
찾음 · 놓침 · 할 일로 잡음 · 정밀도 · 모든 칸 정답 · 주 유형 · 마감 맞음 · 놓친 할 일 · 더 만든 할 일 · 우선순위 · 분류 실패 · 처리 시간.
칸마다 가장 좋은 값은 굵게(모두 같으면 굵게 하지 않음). 봉인 세트라 개수만 적는다(메일 번호 · 내용 없음). --csv는 같은 숫자를 csv로.

    python eval/runners/part_table.py --file <TP6_sealed>/final/final_mails.json \\
        "K-EXAONE 2.5=<…>/predictions_final_exaone-high_mask.json" "Claude Haiku 5.5=<…>/predictions_final_or-haiku_mask.json" \\
        "DeepSeek V4.1 Flash=<…>/predictions_final_or-deepseek_mask.json" --md part_table.md --csv part_table.csv
"""
import argparse
import csv
import json
import sys
from collections import Counter
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
    secs, timeout, over, failed_calls, first = [], 0, 0, 0, {}
    for x in timing or []:  # 한 줄 = 한 번 처리(다시 부른 메일은 줄이 더 있다) — 보고서의 처리 시간과 같은 기준
        if x["id"] not in ids or x.get("calls") == 0:  # calls 0 = --resume로 앞 실행 출력을 다시 쓴 메일
            continue
        secs.append(x["s"])
        first.setdefault(x["id"], bool(x.get("call")) and x["call"][0]["kind"] != "ok")  # 메일마다 첫 시도에 판단하지 못했나
        for c in x.get("call", []):
            over += c["s"] > limit
            timeout += c["kind"] == "timeout"
            failed_calls += c["kind"] != "ok"
    secs.sort()
    whole = len(first) == r["n"]  # --resume로 나눠 잰 실행은 마지막 실행 시간만 남는다 → 처리 시간 · 1차 실패는 '기록 없음'
    first_fail = sum(first.values())
    return dict(n=r["n"], pos=pos, miss=miss, fp=fp, prec=found / (found + fp) if found + fp else None,
                recall=found / pos if pos else None, full=r["full"], due_ok=t["due_ok"], due_n=t["gold"],
                failed=sum(p.get("_source") == "failed" for p in preds if p.get("id") in ids),
                med=secs[len(secs) // 2] if whole else None, p90=secs[min(len(secs) - 1, int(len(secs) * 0.9))] if whole else None,
                max=secs[-1] if whole else None, first_fail=first_fail if whole else None,
                type_acc=r["acc"]["주 유형"], prio_acc=r["acc"]["우선순위"],
                task_miss=t["gold"] - t["paired"], task_extra=t["pred"] - t["paired"],
                timeout=timeout, over=over, failed_calls=failed_calls, timed=len(secs), type_pairs=r["type_pairs"],
                fields=r["wrong_fields"], ev=evidence(mails, preds))


def evidence(mails: list, preds: list) -> tuple:
    """근거 문장(AI-15): 예측 할 일 수 · 근거 있음 · 근거가 본문에 그대로 있음(run_dummy 보고서와 같은 기준). 내용이 맞는지는 채점하지 않는다."""
    body = {o["mail"]["id"]: o["mail"]["body"] for o in mails}
    ts = [(t, body[p["id"]]) for p in preds if p.get("id") in body for t in p.get("tasks") or [] if isinstance(t, dict)]
    has = [(t["evidence"], b) for t, b in ts if t.get("evidence")]
    return len(ts), len(has), sum(all(x in b for x in e.split("\n")) for e, b in has)


def pct(x):
    return "-" if x is None else f"{x:.1%}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", help="'모델 이름=결과 파일(predictions_*.json)'")
    ap.add_argument("--file", type=Path, required=True, help="세트 정답 파일(봉인 테스트는 레포 밖)")
    ap.add_argument("--limit", type=float, default=Settings.llm_background_timeout_s, help="'N초 넘은 호출' 기준(기본: 서비스 분류 제한 시간)")
    ap.add_argument("--md", type=Path, default=None)
    ap.add_argument("--csv", type=Path, default=None, help="같은 숫자를 csv로")
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
         "- 처리 시간은 메일 1통(다시 부른 것 포함). --resume로 나눠 잰 실행은 마지막 실행 시간만 남아 처리 시간 · 1차 실패를 '기록 없음'으로 둔다",
         "- 칸마다 가장 좋은 값은 굵게(모두 같으면 굵게 하지 않음). 개수만 적는다(봉인 세트)",
         "", "## 묶음 구성", "", "| 묶음 | 메일 | 할 일 메일 | 정답 할 일 |", "|---|---|---|---|"]
    first = res[names[0]]
    L += [f"| {p} | {first[p]['n']} | {first[p]['pos']} | {first[p]['due_n']} |" for p in PARTS]
    cols = [  # (칸, 값 글자, 비교 값, 좋은 쪽) — 지금까지 PR의 모델 맞대기 표와 같은 칸
        ("찾음 ↑", lambda m: f"{m['pos'] - m['miss']}/{m['pos']}" if m["pos"] else "-", lambda m: m["pos"] - m["miss"] if m["pos"] else None, max),
        ("놓침 ↓", lambda m: str(m["miss"]) if m["pos"] else "-", lambda m: m["miss"] if m["pos"] else None, min),
        ("할 일로 잡음 ↓", lambda m: f"{m['fp']}/{m['n'] - m['pos']}", lambda m: m["fp"], min),
        ("할 일 메일 정밀도 ↑", lambda m: pct(m["prec"]) if m["pos"] else "-", lambda m: m["prec"] if m["pos"] else None, max),
        ("모든 칸 정답 ↑", lambda m: f"{m['full']}/{m['n']}", lambda m: m["full"], max),
        ("주 유형 ↑", lambda m: pct(m["type_acc"]), lambda m: m["type_acc"], max),
        ("마감 맞음 ↑", lambda m: f"{m['due_ok']}/{m['due_n']}" if m["due_n"] else "-", lambda m: m["due_ok"] if m["due_n"] else None, max),
        ("놓친 할 일 · 더 만든 할 일 ↓", lambda m: f"{m['task_miss']} · {m['task_extra']}", lambda m: None, min),
        ("우선순위 ↑", lambda m: pct(m["prio_acc"]), lambda m: m["prio_acc"], max),
        ("분류 실패 1차 → 다시 부른 뒤 ↓", lambda m: f"{'기록 없음' if m['first_fail'] is None else m['first_fail']} → {m['failed']}",
         lambda m: m["failed"], min),
        ("1통 처리 시간 중앙 · 90% · 최대", lambda m: "기록 없음" if m["med"] is None else f"{m['med']:.1f}초 · {m['p90']:.1f}초 · {m['max']:.1f}초",
         lambda m: m["med"], min),
    ]
    for p in PARTS:
        m0 = first[p]
        L += ["", f"## {p} — 메일 {m0['n']}통 · 할 일 메일 {m0['pos']} · 정답 할 일 {m0['due_n']}개", "",
              "| 모델 | " + " | ".join(c[0] for c in cols) + " |", "|---|" + "---|" * len(cols)]
        best = []
        for _, _, val, better in cols:
            vs = [v for v in (val(res[n][p]) for n in names) if v is not None]
            best.append(better(vs) if vs and len(set(vs)) > 1 else None)
        for n in names:
            m = res[n][p]
            cells = [f"**{txt(m)}**" if b is not None and val(m) == b else txt(m) for (_, txt, val, _), b in zip(cols, best)]
            L.append(f"| {n} | " + " | ".join(cells) + " |")
    # 칸별로 틀린 메일(메일 단위) — 모든 칸 정답이 아닌 메일이 어느 칸에서 틀렸나. 한 메일이 여러 칸에서 틀릴 수 있어 칸 합은 틀린 메일보다 크다
    fcols = ["Task 여부", "Task 수", "마감", "주 유형", "우선순위", "긴급", "지목", "재요청"]
    L += ["", "## 칸별로 틀린 메일 (메일 단위, 통수)", "",
          "- 틀린 메일 = 모든 칸 정답이 아닌 메일. 한 메일이 여러 칸에서 틀릴 수 있어 칸을 더하면 틀린 메일보다 크다",
          "- 할 일 여부 = 할 일 있음 · 없음 판정(놓침 + 할 일로 잡음) · 할 일 수 = 할 일 개수 · 마감 = 메일의 마감이 분까지 모두 같은가",
          "- 근거 문장은 코드로 내용을 채점하지 않는다 — 예측 할 일 중 근거가 있고 본문에 그대로 있는 수만 센다(AI-15)"]
    for p in PARTS:
        L += ["", f"### {p} — 메일 {first[p]['n']}통", "",
              "| 모델 | 틀린 메일 | 할 일 여부 | 할 일 수 | 마감 | 주 유형 | 우선순위 | 긴급 | 지목 | 재요청 | 근거 문장 본문 그대로 / 예측 할 일 |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        for n in names:
            m = res[n][p]
            ev = m["ev"]
            L.append(f"| {n} | {m['n'] - m['full']} | " + " | ".join(str(m["fields"][k]) for k in fcols) + f" | {ev[2]}/{ev[0]} |")
    # 주 유형이 틀린 메일을 정답 → 예측 짝으로(통수만). '유형만 틀림' = 다른 칸(할 일 여부 · 수 · 마감 · 우선순위 …)은 모두 맞음
    L += ["", "## 주 유형 틀림 — 정답 첫 유형 → 예측 첫 유형 (전체, 통수)", "",
          "- 유형만 틀림 = 모든 칸 정답에서 주 유형 한 칸만 틀린 메일(할 일 · 마감 · 우선순위는 맞음)",
          "- 답을 못 낸 메일(분류 실패)은 유형을 고른 것이 아니라 짝에서 빼고 따로 센다(#297 리뷰)", ""]
    for n in names:
        pairs, only, failed = Counter(), Counter(), 0
        for (g, pr, type_only), k in res[n]["전체"]["type_pairs"].items():
            if pr == "분류 실패":
                failed += k
                continue
            pairs[(g, pr)] += k
            only[(g, pr)] += k * type_only
        L += [f"### {n} — {pairs.total()}통 (유형만 틀림 {only.total()}{f' · 분류 실패 {failed}통 따로' if failed else ''})", "",
              "| 정답 → 예측 | 통 | 그중 유형만 틀림 |", "|---|---|---|"]
        L += [f"| {g} → {pr} | {k} | {only[(g, pr)]} |" for (g, pr), k in pairs.most_common()]
        L.append("")
    text = "\n".join(L) + "\n"
    print(text)
    if a.md:
        a.md.write_text(text, encoding="utf-8")
    if a.csv:
        with a.csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            keys = ["n", "pos", "miss", "fp", "prec", "recall", "full", "type_acc", "due_ok", "due_n", "task_miss", "task_extra",
                    "prio_acc", "first_fail", "failed", "med", "p90", "max", "timeout", "over"]
            w.writerow(["model", "part", *keys])
            for n in names:
                for p in PARTS:
                    w.writerow([n, p, *[res[n][p][k] for k in keys]])


if __name__ == "__main__":
    main()
