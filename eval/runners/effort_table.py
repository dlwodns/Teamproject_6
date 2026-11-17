"""강도별 · 본문 길이 구간별 분류 표(#210 · docs/40_ai/io_spec.md 6절). 모델을 부르지 않는다.

run_dummy.py가 남긴 결과(predictions_*.json)와 처리 시간 파일(timing_*.json)을 읽어 강도 · 회차마다
놓침 · 할 일로 잡음 · 정밀도 · 모든 칸 정답 · 빈 답(finish=length) · 시간 초과 · 출력 · 추론 토큰 · 처리 시간을 세고,
본문 길이 구간(1,000자 미만 · 1,000~2,000자 · 2,000자 이상)마다 같은 표를 만든다. 세트가 여럿이면 구간 표는 합친다.

    # 강도 · 회차는 파일 이름에서 읽는다 → run_dummy.py --out .../predictions_dev9_i210-high-r2_mask.json
    python eval/runners/effort_table.py eval/reports/predictions_dev4_i210-*_mask.json eval/reports/predictions_dev9_i210-*_mask.json
    # '이름=경로'는 그 이름으로 칸만 만들고 강도 고르기에는 넣지 않는다(출력 상한 4096 때 결과 같은 비교용)
    python eval/runners/effort_table.py ... "4096 max=eval/reports/predictions_dev9_t600-max_mask.json"

강도 고르기(io_spec 6절 판단 기준): 길이 구간마다 가장 좋은 강도가 모든 회차에서 같고 다음 강도보다 모든 칸 정답이
2통 이상 많을 때만 그 구간을 그 강도로 나눈다. 아니면 전체에서 가장 좋은 강도 하나로 고정한다.
'좋다'의 순서: 모든 칸 정답 많은 쪽 → 놓침 적은 쪽 → 할 일로 잡음 적은 쪽 → 낮은 강도.
봉인 세트(--file)도 개수만 나온다(메일 번호를 적지 않는다).
"""
import argparse
import glob
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data/dummy"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval import evaluate, load_gold  # noqa: E402  data/dummy/eval.py
from run_dummy import SETS  # noqa: E402
from app.core.config import Settings  # noqa: E402  run_dummy가 ai 경로를 넣는다

EFFORTS = ["low", "medium", "high", "max"]
BINS = [("1,000자 미만", 0, 1000), ("1,000~2,000자", 1000, 2000), ("2,000자 이상", 2000, 10**9)]


def parse_label(stem: str):
    """파일 이름 → (강도, 회차). 못 읽으면 None."""
    e = re.search(r"(?<![a-z])(low|medium|high|max)(?![a-z])", stem)
    r = re.search(r"(?:^|[-_@])r(\d+)(?=[-_]|$)", stem)
    return (e.group(1) if e else None), (int(r.group(1)) if r else None)


def set_of(path: Path, sealed: Path | None):
    """결과 파일 → (세트 이름, 정답 파일). predictions_<세트>_… 이름이 레포 세트가 아니면 --file 세트."""
    m = re.match(r"predictions_([a-z0-9]+)_", path.name)
    if m and m.group(1) in SETS:
        return m.group(1), SETS[m.group(1)]
    if sealed is None:
        sys.exit(f"{path.name}: 세트를 이름에서 못 읽었다 — 레포 밖 세트면 --file로 정답 파일을 준다")
    return sealed.stem.removesuffix("_mails"), str(sealed.resolve())


def zero():
    return Counter(n=0, pos=0, miss=0, fp=0, full=0, failed=0, calls=0, resp=0, gen=0, reason=0, empty=0, timeout=0, over=0,
                   tok_known=0)


def count(gold: list, preds: list, owner: str, timing: list | None, lo: int, hi: int, limit: float) -> tuple[Counter, list]:
    """한 세트 · 한 구간의 개수와 처리 시간 목록."""
    sub = [o for o in gold if lo <= len(o["mail"]["body"]) < hi]
    c = zero()
    if sub:
        r = evaluate(sub, preds, owner)
        ids = {o["mail"]["id"] for o in sub}
        c.update(n=r["n"], pos=r["groups"]["있음"]["n"], miss=len(r["wrong_ids"]["있음"]), fp=len(r["wrong_ids"]["없음"]),
                 full=r["full"], failed=sum(p.get("_source") == "failed" for p in preds if p.get("id") in ids))
    secs = []
    for t in timing or []:
        if not lo <= t["chars"] < hi:
            continue
        secs.append(t["s"])
        c["over"] += t["s"] > limit
        errs = t.get("call_errors", [t["error"]] if t.get("failed") else [])
        c["empty"] += sum("finish=length" in e for e in errs)
        c["timeout"] += sum("초과" in e or "Timeout" in e for e in errs)
        if "calls" in t:  # 토큰은 #210부터 남긴다(그 전 timing 파일에는 없다)
            c.update(calls=t["calls"], resp=t["calls"] - sum("호출 실패" in e for e in errs), gen=t["gen"], reason=t["reasoning"],
                     tok_known=1)
    return c, secs


def fmt_row(label: str, c: Counter, secs: list, set_name: str | None = None) -> str:
    prec = f"{(c['pos'] - c['miss']) / (c['pos'] - c['miss'] + c['fp']):.1%}" if c["pos"] - c["miss"] + c["fp"] else "-"
    tok = f"{c['gen'] / c['resp']:,.0f} ({c['reason'] / c['resp']:,.0f})" if c["tok_known"] and c["resp"] else "-"
    ts = sorted(secs)  # 중앙은 run_dummy.py 보고서 머리와 같은 방식(정렬해 절반 자리)
    tm = f"{ts[min(len(ts) - 1, len(ts) // 2)]:.1f} · {ts[-1]:.1f}초" if ts else "-"
    head = f"| {set_name} " if set_name is not None else ""
    return (f"{head}| {label} | {c['miss']}/{c['pos']} | {c['fp']} | {prec} | {c['full']}/{c['n']} | {c['failed']} | {c['empty']} | "
            f"{c['timeout']} | {tok} | {tm} | {c['over']} |")


COLS = "| 강도 · 회차 | 놓침 | 할 일로 잡음 | 정밀도 | 모든 칸 정답 | 실패(최종) | 빈 답(finish=length) | 시간 초과 | 출력 토큰(추론) 평균 | 처리 시간 중앙 · 최대 | {limit}초 넘음 |"
SEP = "|---" * 11 + "|"


def better(a: tuple[str, Counter], b: tuple[str, Counter]) -> bool:
    """a가 b보다 좋은가: 모든 칸 정답 → 놓침 → 할 일로 잡음 → 낮은 강도."""
    ka = (a[1]["full"], -a[1]["miss"], -a[1]["fp"], -EFFORTS.index(a[0]))
    kb = (b[1]["full"], -b[1]["miss"], -b[1]["fp"], -EFFORTS.index(b[0]))
    return ka > kb


def rank(cands: list[tuple[str, Counter]]) -> list[tuple[str, Counter]]:
    out = []
    for x in cands:
        i = next((i for i, y in enumerate(out) if better(x, y)), len(out))
        out.insert(i, x)
    return out


def decide(groups: dict) -> list[str]:
    """io_spec 6절 판단 기준. groups[(강도, 회차)][구간 이름] = Counter."""
    efforts = sorted({e for e, _ in groups}, key=EFFORTS.index)
    runs = sorted({r for _, r in groups})
    L = ["", "## 강도 고르기 (io_spec 6절 판단 기준)", ""]
    if len(efforts) < 2:
        return L + ["- 고르지 않는다: 이름에 강도 · 회차가 있는 결과(`…_i210-high-r1_mask.json`)가 강도 2개 이상 있어야 한다"]
    total = {e: sum((groups[(e, r)][b] for r in runs if (e, r) in groups for b, _, _ in BINS), zero()) for e in efforts}
    best = rank(list(total.items()))[0][0]
    L.append(f"- 전체(회차 {len(runs)}회 합): " + " · ".join(f"{e} 모든 칸 {total[e]['full']} · 놓침 {total[e]['miss']} · 잡음 {total[e]['fp']}"
                                                   for e in efforts) + f" → **{best}**")
    split = {}
    for b, _, _ in BINS:
        wins, gaps = [], []
        for r in runs:
            cands = [(e, groups[(e, r)][b]) for e in efforts if (e, r) in groups]
            if len(cands) < 2 or not cands[0][1]["n"]:
                continue
            ranked = rank(cands)
            wins.append(ranked[0][0])
            gaps.append(ranked[0][1]["full"] - ranked[1][1]["full"])
        if not wins:
            continue
        ok = len(runs) >= 2 and len(wins) == len(runs) and len(set(wins)) == 1 and min(gaps) >= 2
        L.append(f"- {b}: 회차별 가장 좋은 강도 {' · '.join(wins)} (다음 강도보다 모든 칸 +{' · +'.join(map(str, gaps))})"
                 f" → {'나눌 조건 맞음' if ok else '나눌 조건 아님'}")
        if ok and wins[0] != best:
            split[b] = wins[0]
    if len(runs) < 2:
        L.append("- 회차가 1회라 길이에 따라 나누는지는 판단하지 않는다(2회 필요)")
    L.append(f"- 결론(제안): " + (f"길이에 따라 나눔 — {' · '.join(f'{b} {e}' for b, e in split.items())}, 나머지 {best}" if split
                               else f"**{best}** 하나로 고정"))
    return L


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="+", help="결과 파일(predictions_*.json, 글롭 가능) 또는 '이름=경로'")
    ap.add_argument("--file", type=Path, default=None, help="레포 밖 세트(봉인 테스트)의 정답 파일. 개수만 적는다")
    ap.add_argument("--md", type=Path, default=None, help="표를 이 파일에도 쓴다")
    ap.add_argument("--limit", type=float, default=Settings.llm_background_timeout_s,
                    help="이 초를 넘은 호출 수를 센다(기본: 서비스 분류 제한 시간 LLM_BACKGROUND_TIMEOUT_S 기본값, AI-28)")
    a = ap.parse_args()

    entries = []  # (칸 이름, 강도, 회차, 결과 경로)
    for f in a.files:
        label, _, path = f.rpartition("=") if "=" in f else ("", "", f)
        for p in sorted(glob.glob(path)) or [path]:
            p = Path(p)
            if not p.is_file():
                sys.exit(f"결과 파일 없음: {p}")
            e, r = parse_label(p.stem) if not label else (None, None)
            entries.append((label or (f"{e} r{r}" if e and r else e or p.stem), e if r else None, r, p))

    per_set = defaultdict(list)  # 세트 → [(칸 이름, Counter, secs)]
    pooled = defaultdict(lambda: defaultdict(zero))  # 칸 이름 → 구간 → Counter
    pooled_s = defaultdict(lambda: defaultdict(list))
    groups = defaultdict(dict)  # (강도, 회차) → 구간 → Counter
    for label, e, r, p in entries:
        name, gold_path = set_of(p, a.file)
        gold = load_gold(gold_path)
        owner = json.loads((Path(gold_path) if Path(gold_path).is_absolute() else ROOT / "data/dummy" / gold_path)
                           .read_text(encoding="utf-8"))["mailbox"]["owner"]
        preds = json.loads(p.read_text(encoding="utf-8"))
        tp = p.with_name(f"timing_{p.stem}.json")
        timing = json.loads(tp.read_text(encoding="utf-8")) if tp.is_file() else None
        whole, ws = count(gold, preds, owner, timing, 0, 10**9, a.limit)
        per_set[name].append((label, whole, ws))
        for b, lo, hi in BINS:
            c, s = count(gold, preds, owner, timing, lo, hi, a.limit)
            pooled[label][b] += c
            pooled_s[label][b] += s
        if e and r:
            groups[(e, r)] = pooled[label]

    cols = COLS.format(limit=f"{a.limit:.0f}")
    order = sorted(pooled, key=lambda k: (k not in {f"{e} r{r}" for e, r in groups}, k))
    L = ["# 강도별 · 길이 구간별 분류 표 (#210)", "",
         "- 놓침은 '놓친 수/정답 할 일 메일 수', 실패(최종)는 다시 부른 뒤에도 분류 실패로 남은 메일(정답으로 세지 않음)",
         f"- 빈 답 · 시간 초과 · {a.limit:.0f}초 넘음은 호출(다시 부른 것 포함) 수(넘음 기준은 서비스 분류 제한 시간, --limit), 토큰은 응답이 온 호출 1회 평균",
         "", "## 세트별", "", "| 세트 " + cols, "|---" + SEP]
    for name, rows in per_set.items():
        for label, c, s in sorted(rows, key=lambda x: order.index(x[0])):
            L.append(fmt_row(label, c, s, name))
    for b, _, _ in BINS:
        n = max((pooled[k][b]["n"] for k in order), default=0)
        L += ["", f"## {b} (세트 합침, {n}통)", "", cols, SEP]
        L += [fmt_row(k, pooled[k][b], pooled_s[k][b]) for k in order]
    L += decide(groups)
    text = "\n".join(L) + "\n"
    print(text)
    if a.md:
        a.md.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
