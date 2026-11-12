"""모델 비교 결과를 한 표로 모은다 (AI-21). run_dummy.py가 남긴 predictions_<세트>_<모델>.json을 다시 채점한다.

사용: ai/.venv/bin/python eval/runners/compare_summary.py <세트 파일 *_mails.json> ... [--hide]
각 세트 파일 옆의 predictions_*.json(엑사원은 predictions_*_llm.json 또는 _replay.json)을 찾아 모델별로 한 줄씩 낸다.
--hide: 메일 ID를 적지 않는다(봉인 세트).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data/dummy"))
from eval import evaluate, load_gold  # noqa: E402

LABEL = {"llm": "엑사원 3.5 7.8B", "replay": "엑사원 3.5 7.8B", "claude-haiku-5.5": "Claude Haiku 5.5",
         "deepseek-v4.1-flash": "DeepSeek V4.1 Flash", "k-exaone_v2.5": "K-EXAONE 2.5 (API)",
         "k-exaone_v2.5_classify_v6": "K-EXAONE 2.5 · 프롬프트 v6", "k-exaone_v2.5_classify_v7": "K-EXAONE 2.5 · 프롬프트 v7"}
ORDER = list(LABEL)


def rows_for(src: Path, pred_dir: Path | None = None):
    owner = json.loads(src.read_text(encoding="utf-8"))["mailbox"]["owner"]
    gold = load_gold(src.resolve())
    stem = src.stem.removesuffix("_mails")
    for p in sorted((pred_dir or src.parent).glob(f"predictions_{stem}_*.json"), key=lambda p: ORDER.index(k) if (k := p.stem.split(f"{stem}_", 1)[1]) in ORDER else 99):
        key = p.stem.split(f"{stem}_", 1)[1]
        r = evaluate(gold, json.loads(p.read_text(encoding="utf-8")), owner)
        y, n = r["groups"]["있음"], r["groups"]["없음"]
        found, caught = y["n"] - y["wrong"], n["wrong"]
        yield stem, LABEL.get(key, key), y, n, r, found, caught


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sets", nargs="+", type=Path)
    ap.add_argument("--pred-dir", type=Path, default=None, help="예측 파일 폴더(기본: 세트 파일 옆). --set core는 eval/reports")
    a = ap.parse_args()
    L = ["| 세트 | 모델 | 할 일 있음: 맞음 · 일부 틀림 · 놓침 | 할 일 없음: 맞음 · 일부 틀림 · 할 일로 잡음 | 모든 칸 정답 ↑ | 할 일 여부 맞음 ↑ | 정밀도 ↑ |",
         "|---|---|---|---|---|---|---|"]
    tot = {}
    for src in a.sets:
        for stem, model, y, n, r, found, caught in rows_for(src, a.pred_dir):
            prec = f"{found / (found + caught) * 100:.0f}% ({found}/{found + caught})" if found + caught else "-"
            L.append(f"| {stem} | {model} | {y['n']}통 중 {y['ok']} · {y['n'] - y['ok'] - y['wrong']} · {y['wrong']} "
                     f"| {n['n']}통 중 {n['ok']} · {n['n'] - n['ok'] - n['wrong']} · {n['wrong']} | {r['full']}/{r['n']} "
                     f"| {r['n'] - y['wrong'] - n['wrong']}/{r['n']} | {prec} |")
            t = tot.setdefault(model, [0] * 8)
            for i, v in enumerate((y["n"], y["ok"], y["wrong"], n["n"], n["ok"], n["wrong"], r["full"], r["n"])):
                t[i] += v
    if len(a.sets) > 1:
        for model, (yn, yok, yw, nn, nok, nw, full, nall) in tot.items():
            found = yn - yw
            L.append(f"| **합계** | {model} | {yn}통 중 {yok} · {yn - yok - yw} · {yw} | {nn}통 중 {nok} · {nn - nok - nw} · {nw} "
                     f"| {full}/{nall} | {nall - yw - nw}/{nall} | "
                     + (f"{found / (found + nw) * 100:.0f}% ({found}/{found + nw}) |" if found + nw else "- |"))
    print("\n".join(L))


if __name__ == "__main__":
    main()
