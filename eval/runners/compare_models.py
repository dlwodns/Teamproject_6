"""모델 결과 맞대기(지금은 오픈라우터 2종, DE-D24) — 메일마다 몇 개 모델이 틀렸나(DE-D25). run_dummy.py --or로 모델별 결과를 만든 뒤 쓴다.

사용 (레포 루트에서):
  python eval/runners/compare_models.py --set dev4                       # eval/reports/predictions_dev4_or-*.json을 모두 맞댄다
  python eval/runners/compare_models.py --file <레포 밖 폴더>/testA_mails.json   # 봉인 세트: 메일 번호 없이 유형 · 태그별 개수만
결과: 같은 폴더의 compare_<세트>.md. 모델 비교는 할 일 여부(놓침 · 할 일로 잡음)와 주 유형만 본다.
읽는 법(DE-D25): 모두 틀림 → 정답부터 다시 보고 규칙 · 프롬프트 후보, 일부만 틀림 → 그 모델 약점으로 기록하고 다른 메일 · 세트에서도
반복되면 후보(서비스는 더 작은 엑사원이라 가볍게 넘기지 않는다). 메일 한 통에만 맞춘 규칙은 만들지 않는다.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data/dummy"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval import is_sealed, load_gold  # noqa: E402  data/dummy/eval.py
from run_dummy import SETS  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=SETS, default="dev4")
    ap.add_argument("--file", type=Path, default=None, help="레포 밖 봉인 세트 파일(결과도 그 옆에 있어야 한다)")
    a = ap.parse_args()
    src = a.file.expanduser().resolve() if a.file else ROOT / "data/dummy" / SETS[a.set]
    tag = src.stem.removesuffix("_mails") if a.file else a.set
    folder = src.parent if a.file else ROOT / "eval/reports"
    files = []
    for f in sorted(folder.glob(f"predictions_{tag}_or-*.json")):  # 모델 호출이 실패한 메일은 규칙 결과라 맞대기에서 모델 판단으로 볼 수 없다
        ps = json.loads(f.read_text(encoding="utf-8"))
        bad = sum(1 for p in ps if "호출 실패" in str(p.get("_fallback") or ""))
        if bad:
            print(f"뺌: {f.name} — 모델 호출 실패 {bad}/{len(ps)}통(크레딧 · 연결 문제). 그 모델을 다시 돌리면 덮어써진다")
            continue
        files.append(f)
    if len(files) < 2:
        sys.exit(f"맞댈 모델 결과가 {len(files)}개뿐이다 — run_dummy.py --or로 모델마다 먼저 돌린다({folder.name}/predictions_{tag}_or-*.json)")
    models = [f.stem.split("_or-", 1)[1] for f in files]
    preds = {mdl: {p["id"]: p for p in json.loads(f.read_text(encoding="utf-8"))} for mdl, f in zip(models, files)}
    gold = load_gold(src)
    hide = is_sealed(src)

    rows, by_n = [], Counter()
    for o in gold:
        i, g = o["mail"]["id"], o["gold"]
        has = bool(g["tasks"])
        miss = [m for m in models if has and not preds[m].get(i, {}).get("tasks")]
        extra = [m for m in models if not has and preds[m].get(i, {}).get("tasks")]
        typ = [m for m in models if (preds[m].get(i, {}).get("action_types") or [None])[0] not in
               (g["action_types"] if len(g["tasks"]) >= 2 else g["action_types"][:1])]
        for kind, who in (("놓침", miss), ("할 일로 잡음", extra), ("주 유형", typ)):
            if who:
                by_n[(kind, len(who))] += 1
                rows.append((kind, len(who), i, o["mail"]["subject"], g["action_types"][0], g["tags"], who))

    n = len(models)
    L = [f"# 모델 맞대기 · {tag} ({len(gold)}통)", "", f"- 모델: {' · '.join(models)}",
         "- 읽는 법(DE-D25): 모두 틀림 → 정답부터 확인 후 규칙 · 프롬프트 후보 / 일부만 틀림 → 그 모델 약점으로 기록, 다른 메일 · 세트에서도 반복되면 후보", "",
         "| 틀린 칸 | " + " | ".join(f"{k}개 모델 틀림" for k in range(n, 0, -1)) + " |", "|---" * (n + 1) + "|"]
    for kind in ("놓침", "할 일로 잡음", "주 유형"):
        L.append(f"| {kind} | " + " | ".join(f"{by_n[(kind, k)]}통" for k in range(n, 0, -1)) + " |")
    L.append("")
    rows.sort(key=lambda r: (["놓침", "할 일로 잡음", "주 유형"].index(r[0]), -r[1], r[2]))
    if hide:  # 봉인 세트: 메일 번호 · 제목을 적지 않고 정답 유형 · 태그별 개수만(plan 8.5)
        cnt = Counter((r[0], r[1], r[4]) for r in rows)
        tags = Counter((r[0], r[1], t) for r in rows for t in r[5])
        L += ["## 틀린 메일 — 정답 유형별 개수(봉인 세트라 메일 번호는 적지 않음)", "", "| 틀린 칸 | 틀린 모델 수 | 정답 유형 | 통 |", "|---|---|---|---|"]
        L += [f"| {k} | {m} | {t} | {c} |" for (k, m, t), c in sorted(cnt.items())]
        L += ["", "| 틀린 칸 | 틀린 모델 수 | 태그 | 통 |", "|---|---|---|---|"] + [f"| {k} | {m} | {t} | {c} |" for (k, m, t), c in sorted(tags.items())]
    else:
        L += ["## 메일별", "", "| 틀린 칸 | 틀린 모델 수 | 메일 | 제목 | 정답 주 유형 | 태그 | 틀린 모델 |", "|---|---|---|---|---|---|---|"]
        L += [f"| {k} | {m}/{n} | {i} | {s} | {t} | {', '.join(tg) or '-'} | {', '.join(w)} |" for k, m, i, s, t, tg, w in rows]
    out = folder / f"compare_{tag}.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(" · ".join(f"{kind} {'/'.join(str(by_n[(kind, k)]) for k in range(n, 0, -1))}" for kind in ("놓침", "할 일로 잡음", "주 유형"))
          + f" (앞에서부터 모델 {n}개 · {n - 1}개" + (" · …" if n > 2 else "") + " 틀림 순) → " + str(out))


if __name__ == "__main__":
    main()
