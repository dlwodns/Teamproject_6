"""세트에서 메일 N통을 정답 할 일 있음 · 없음 반반으로 뽑아 작은 세트 파일을 만든다 (모델 비교 AI-21).

사용 (레포 루트에서):
  python eval/runners/make_subset.py --set dev7 --n 10 --exclude <40통 세트>.json --out <폴더>/dev7s_mails.json
  python eval/runners/make_subset.py --file /home/.../testA_mails.json --n 30 --out /home/.../runs/compare/testAs_mails.json

- 받은 메일만 뽑는다(보낸 메일은 분류 대상이 아님). 보낸 메일은 응답 대기 계산 재료라 그대로 넣지 않는다.
- 시드 고정(기본 21)이라 같은 명령은 같은 메일을 뽑는다. 메일 내용은 출력하지 않는다(봉인 세트를 열지 않고 뽑을 수 있게).
- --exclude: 그 세트 파일에 든 메일 ID(앞에 '세트:'가 붙은 것 포함)는 뽑지 않는다 — 40통과 겹치지 않게.
"""
import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_dummy import SETS  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=SETS)
    ap.add_argument("--file", type=Path)
    ap.add_argument("--n", type=int, default=0)
    ap.add_argument("--ids", default="", help="뽑을 메일 ID를 쉼표로(주면 --n · 시드 대신). 위험 메일 회귀 확인용")
    ap.add_argument("--seed", type=int, default=21)
    ap.add_argument("--exclude", type=Path, action="append", default=[])
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    src = a.file if a.file else ROOT / "data/dummy" / SETS[a.set]
    label = a.set or src.stem.removesuffix("_mails")
    data = json.loads(src.read_text(encoding="utf-8"))
    skip = set()
    for ex in a.exclude:
        for o in json.loads(ex.read_text(encoding="utf-8"))["mails"]:
            i = o["mail"]["id"]
            skip.add(i.split(":", 1)[1] if i.startswith(f"{label}:") else i)
    owner = data["mailbox"]["owner"]
    pool = [o for o in data["mails"] if o["mail"]["from"] != owner and o["mail"]["id"] not in skip]
    rng = random.Random(f"{a.seed}:{label}")
    yes = [o for o in pool if o["gold"]["tasks"]]
    no = [o for o in pool if not o["gold"]["tasks"]]
    if a.ids:
        want = set(a.ids.split(","))
        pick = [o for o in pool if o["mail"]["id"] in want]
        if len(pick) != len(want):
            sys.exit(f"없는 ID: {want - {o['mail']['id'] for o in pick}}")
        k = sum(bool(o["gold"]["tasks"]) for o in pick)
    else:
        k = min(a.n // 2, len(yes))
        pick = rng.sample(yes, k) + rng.sample(no, min(a.n - k, len(no)))
    pick.sort(key=lambda o: o["mail"]["id"])
    meta = dict(data["meta"], version=f"{data['meta']['version']}-sub{len(pick)}s{a.seed}", count=len(pick),
                subset_of=src.name)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(dict(data, meta=meta, mails=pick), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{label}: {len(pick)}통 (할 일 있음 {k} · 없음 {len(pick) - k}, 제외 {len(skip)}) → {a.out}")


if __name__ == "__main__":
    main()
