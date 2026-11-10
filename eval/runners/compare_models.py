"""모델 결과 맞대기(지금은 오픈라우터 2종, DE-D24) — 메일마다 몇 개 모델이 틀렸나(DE-D25). run_dummy.py --or로 모델별 결과를 만든 뒤 쓴다.

사용 (레포 루트에서, ai/.venv 파이썬으로):
  python eval/runners/compare_models.py --set dev4                       # eval/reports/predictions_dev4_or-*.json을 모두 맞댄다
  python eval/runners/compare_models.py --file <레포 밖 폴더>/testA_mails.json   # 봉인 세트: 메일 번호 없이 유형 · 태그별 개수만
결과: 같은 폴더의 compare_<세트>.md. 할 일 여부(놓침 · 할 일로 잡음)와 주 유형만 본다. 세 가지를 나란히 맞댄다(#38 리뷰):
  최종    predictions_*_or-*.json — 규칙과 모델 출력을 합친 판정(서비스가 내는 것)
  원출력  llm_cache_predictions_*_or-*.json에 남은 모델 출력 그대로(합치기 전). 같은 메일 요청을 다시 만들어 캐시에서 꺼낸다(모델 호출 없음)
  규칙만  모델 없이 지금 규칙으로 다시 분류한 결과
  모델 응답이 실패한 메일(JSON 형식 오류 등)은 원출력이 없고 최종도 규칙 결과다 → '응답 실패'로 따로 센다.
  결과를 만든 뒤 프롬프트 · 규칙 코드가 바뀌면 캐시에서 못 찾는다 → '원출력 없음'으로 세고, 그 모델을 다시 돌리면 생긴다.
읽는 법(DE-D25): 원출력이 모두 틀림 → 정답부터 다시 보고 프롬프트 후보 / 원출력은 맞는데 최종이 틀림 → 합치기 · 규칙이 덮어쓴 것(프롬프트를
고쳐도 안 바뀐다) / 원출력은 틀렸는데 최종이 맞음 → 규칙이 받쳐 주는 메일(규칙을 덜어내면 드러날 수 있다) / 일부 모델만 틀림 → 그 모델
약점으로 기록, 다른 메일 · 세트에서도 반복되면 후보(서비스는 더 작은 엑사원이라 가볍게 넘기지 않는다). 메일 한 통에만 맞춘 규칙은 만들지 않는다.
"""
import argparse
import json
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data/dummy"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval import is_sealed, load_gold  # noqa: E402  data/dummy/eval.py
from run_dummy import SETS, RuleOnlyClient, prompt_key, requests  # noqa: E402

from app.core.config import get_settings  # noqa: E402  (run_dummy가 ai를 sys.path에 넣는다)
from app.llm.client import LLMError  # noqa: E402
from app.pipeline.classify import classify  # noqa: E402

KINDS = ("놓침", "할 일로 잡음", "주 유형")


class CacheReader:
    """llm_cache에 남은 모델 출력을 메일마다 꺼낸다(모델 호출 없음). 꺼낸 출력은 last에 남는다(합치기 전 원출력)."""

    def __init__(self, cache: dict, model: str):
        self.cache, self.model, self.last = cache, model, None

    def chat_json(self, system, user, schema):
        self.last = self.cache.get(prompt_key(system, user))
        if self.last is None:
            raise LLMError("캐시 없음")
        return self.last


def wrong(g: dict, has_tasks: bool, first_type) -> set[str]:
    """정답과 비교해 틀린 칸. 주 유형은 할 일이 2개 이상이면 정답 유형 중 하나면 맞다(eval.py와 같은 기준)."""
    has = bool(g["tasks"])
    ok = g["action_types"] if len(g["tasks"]) >= 2 else g["action_types"][:1]
    return {k for k, bad in zip(KINDS, (has and not has_tasks, not has and has_tasks, first_type not in ok)) if bad}


def raw_view(out) -> tuple[bool, object] | None:
    """모델 원출력에서 할 일 여부 · 주 유형. 출력이 없으면 None(모르는 것으로 센다)."""
    if not isinstance(out, dict):
        return None
    return bool(out.get("tasks")), (out.get("action_types") or [None])[0]


def short(slug: str) -> str:
    return slug.split("-", 1)[-1] if "-" in slug else slug  # anthropic-claude-haiku-5.5 → claude-haiku-5.5


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
    models = [short(f.stem.split("_or-", 1)[1]) for f in files]
    preds = {mdl: {p["id"]: p for p in json.loads(f.read_text(encoding="utf-8"))} for mdl, f in zip(models, files)}
    caches = {}
    for mdl, f in zip(models, files):
        c = f.with_name(f"llm_cache_{f.stem}.json")
        caches[mdl] = json.loads(c.read_text(encoding="utf-8")) if c.is_file() else {}
    gold = load_gold(src)
    hide = is_sealed(src)
    reqs = {o["mail"]["id"]: req for o, req in requests(json.loads(src.read_text(encoding="utf-8")))}

    # 메일마다 세 가지를 다시 만든다: 규칙만(모델 없이) · 모델별 원출력(캐시에서) · 최종(결과 파일)
    base = get_settings()
    rule_s, model_s = replace(base, llm_enabled=False), replace(base, llm_enabled=True)
    rule_c = RuleOnlyClient(base.model)
    miss, fail = Counter(), Counter()
    W = {}  # 메일 → {"rule": set, "final": {모델: set}, "raw": {모델: set | None}}
    for o in gold:
        i, g = o["mail"]["id"], o["gold"]
        rr = classify(reqs[i], rule_c, rule_s)
        w = {"rule": wrong(g, bool(rr.tasks), (rr.action_types or [None])[0]), "final": {}, "raw": {}}
        for m in models:
            p = preds[m].get(i, {})
            w["final"][m] = wrong(g, bool(p.get("tasks")), (p.get("action_types") or [None])[0])
            if p.get("_fallback"):  # 이 메일은 모델 응답이 실패해 최종도 규칙 결과다
                fail[m] += 1
                w["raw"][m] = None
                continue
            reader = CacheReader(caches[m], m)
            classify(reqs[i], reader, model_s)
            rv = raw_view(reader.last)
            miss[m] += rv is None
            w["raw"][m] = None if rv is None else wrong(g, *rv)
        W[i] = w

    n = len(models)
    final_n = {(i, k): [m for m in models if k in W[i]["final"][m]] for i in W for k in KINDS}
    raw_n = {(i, k): [m for m in models if W[i]["raw"][m] is not None and k in W[i]["raw"][m]] for i in W for k in KINDS}
    raw_known = {i: [m for m in models if W[i]["raw"][m] is not None] for i in W}

    def reading(i, k) -> str:
        fw, rw, known = final_n[(i, k)], raw_n[(i, k)], raw_known[i]
        over = [m for m in known if m in fw and m not in rw]  # 원출력은 맞는데 최종이 틀림
        saved = [m for m in known if m in rw and m not in fw]  # 원출력은 틀렸는데 최종이 맞음
        if known and len(rw) == len(known) == n:
            return "원출력 모두 틀림 → 정답 확인 · 프롬프트 후보" + ("" if fw else "(지금은 규칙이 바로잡음 — 규칙을 덜면 드러남)")
        if over:
            return "합치기 · 규칙이 덮어씀 → 규칙 후보"
        if saved and not fw:
            return "규칙이 바로잡음(원출력 틀림)"
        return "일부 모델만 → 모델 약점 기록" if fw or rw else "-"

    by = Counter()
    for (i, k), fw in final_n.items():
        rw = raw_n[(i, k)]
        by[("최종", k, len(fw))] += bool(fw)
        by[("원출력", k, len(rw))] += bool(rw)
        by[("규칙만", k)] += k in W[i]["rule"]
        by[("덮어씀", k)] += sum(1 for m in raw_known[i] if m in fw and m not in rw)
        by[("바로잡음", k)] += sum(1 for m in raw_known[i] if m in rw and m not in fw)

    L = [f"# 모델 맞대기 · {tag} ({len(gold)}통)", "", f"- 모델: {' · '.join(models)}",
         "- 최종 = 규칙과 모델 출력을 합친 판정 · 원출력 = llm_cache에 남은 모델 출력 그대로(합치기 전) · 규칙만 = 모델 없이 지금 규칙",
         "- 읽는 법(DE-D25): 원출력 모두 틀림 → 정답 확인 후 프롬프트 후보 / 원출력은 맞는데 최종이 틀림 → 합치기 · 규칙 후보 / "
         "원출력은 틀렸는데 최종이 맞음 → 규칙이 받쳐 주는 메일 / 일부 모델만 틀림 → 그 모델 약점으로 기록, 반복되면 후보"]
    if any(fail.values()):
        L.append("- 응답 실패(JSON 형식 오류 등 — 원출력 없음, 최종은 규칙 결과): " + " · ".join(f"{m} {fail[m]}통" for m in models if fail[m]))
    if any(miss.values()):
        L.append("- 원출력 없음: " + " · ".join(f"{m} {miss[m]}통" for m in models if miss[m])
                 + "(캐시에 없음 — 결과를 만든 뒤 프롬프트 · 규칙 코드가 바뀌었으면 그 모델을 다시 돌린다)")
    head = lambda w: " | ".join(f"{w} {k}개 모델" for k in range(n, 0, -1))  # noqa: E731
    L += ["", f"| 틀린 칸 | {head('최종')} | {head('원출력')} | 규칙만 | 합치기가 덮어씀(원출력 맞음 → 최종 틀림) | 규칙이 바로잡음(원출력 틀림 → 최종 맞음) |",
          "|---" * (2 * n + 4) + "|"]
    for k in KINDS:
        L.append(f"| {k} | " + " | ".join(f"{by[('최종', k, c)]}통" for c in range(n, 0, -1)) + " | "
                 + " | ".join(f"{by[('원출력', k, c)]}통" for c in range(n, 0, -1))
                 + f" | {by[('규칙만', k)]}통 | {by[('덮어씀', k)]}건 | {by[('바로잡음', k)]}건 |")
    L += ["", "덮어씀 · 바로잡음은 메일 × 모델 건수다.", ""]
    keys = sorted({(i, k) for (i, k) in final_n if final_n[(i, k)] or raw_n[(i, k)]},
                  key=lambda x: (KINDS.index(x[1]), -len(final_n[x]), -len(raw_n[x]), x[0]))
    info = {o["mail"]["id"]: o for o in gold}
    if hide:  # 봉인 세트: 메일 번호 · 제목을 적지 않고 정답 유형 · 태그별 개수만(plan 8.5)
        cnt = Counter((k, len(final_n[(i, k)]), len(raw_n[(i, k)]), "틀림" if k in W[i]["rule"] else "맞음",
                       info[i]["gold"]["action_types"][0]) for i, k in keys)
        tags = Counter((k, len(final_n[(i, k)]), len(raw_n[(i, k)]), t) for i, k in keys for t in info[i]["gold"]["tags"])
        L += ["## 틀린 메일 — 정답 유형별 개수(봉인 세트라 메일 번호는 적지 않음)", "",
              "| 틀린 칸 | 최종 틀린 모델 수 | 원출력 틀린 모델 수 | 규칙만 | 정답 유형 | 통 |", "|---|---|---|---|---|---|"]
        L += [f"| {k} | {f} | {r} | {ru} | {t} | {c} |" for (k, f, r, ru, t), c in sorted(cnt.items())]
        L += ["", "| 틀린 칸 | 최종 틀린 모델 수 | 원출력 틀린 모델 수 | 태그 | 통 |", "|---|---|---|---|---|"]
        L += [f"| {k} | {f} | {r} | {t} | {c} |" for (k, f, r, t), c in sorted(tags.items())]
    else:
        L += ["## 메일별", "", "| 틀린 칸 | 메일 | 제목 | 정답 주 유형 | 태그 | 최종 틀림 | 원출력 틀림 | 규칙만 | 읽기 |",
              "|---|---|---|---|---|---|---|---|---|"]
        for i, k in keys:
            g, fw, rw = info[i]["gold"], final_n[(i, k)], raw_n[(i, k)]
            L.append(f"| {k} | {i} | {info[i]['mail']['subject']} | {g['action_types'][0]} | {', '.join(g['tags']) or '-'} | "
                     f"{len(fw)}/{n}{' ' + ', '.join(fw) if fw else ''} | {len(rw)}/{len(raw_known[i])}{' ' + ', '.join(rw) if rw else ''} | "
                     f"{'틀림' if k in W[i]['rule'] else '맞음'} | {reading(i, k)} |")
    out = folder / f"compare_{tag}.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")

    def line(what):
        return " · ".join(f"{k} {'/'.join(str(by[(what, k, c)]) for c in range(n, 0, -1))}" for k in KINDS)
    print(f"최종 {line('최종')} | 원출력 {line('원출력')} (모델 {n}개 · {n - 1}개" + (" · …" if n > 2 else "") + " 틀림 순)"
          f" | 규칙만 " + " · ".join(f"{k} {by[('규칙만', k)]}" for k in KINDS)
          + f" | 덮어씀 {sum(by[('덮어씀', k)] for k in KINDS)}건 · 바로잡음 {sum(by[('바로잡음', k)] for k in KINDS)}건"
          + (f" | 응답 실패 {sum(fail.values())}통" if any(fail.values()) else "")
          + (f" | 원출력 없음 {sum(miss.values())}통" if any(miss.values()) else "") + f" → {out}")


if __name__ == "__main__":
    main()
