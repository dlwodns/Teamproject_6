"""라우터 기준 쓸기 · 규칙 확신도 보정 (AI-3, 11/3 피드백 1 '적정 수치 측정 · 최적화').

사용 (레포 루트에서, ai/.venv 파이썬으로):
  ai/.venv/bin/python eval/runners/sweep_router.py                     # dev · dev2 · dev3, 기준 0.30~1.00(0.05 간격)
  ai/.venv/bin/python eval/runners/sweep_router.py --sets dev3 --replay dev3=eval/reports/llm_cache_predictions_dev3_llm.json
  ai/.venv/bin/python eval/runners/sweep_router.py --replay-dir <폴더>     # 세트마다 <폴더>/llm_cache_all_<세트>.json(전 메일 엑사원 출력)
  ai/.venv/bin/python eval/runners/sweep_router.py --classifier app.pipeline.classify:classify --judge app.pipeline.rules.mail_rules_v1:judge
결과: eval/reports/router_sweep.md (--out으로 바꿈)

하는 일
1. 기준값별: 엑사원행 수 · 비율 · 하루 200통 기준 엑사원 시간(CPU 22초/통 실측 · GPU 3초/통 [추정]).
   replay 캐시가 있는 세트만 정확도(누락 · Task 정밀도 · 완전 정답 · 주 유형)를 낸다. 캐시에 없는 메일(대개 그때 기준 이상이라
   엑사원에 가지 않았던 메일)은 classify가 규칙 결과로 대신하므로 '추정 불가'로 따로 센다.
2. 보정: 규칙만 결과를 확신도 값 · judge 사유별로 나눠 Task 여부 · 주 유형 · 완전 정답 정확도를 낸다(과신 · 과소신 찾기).
3. 정책 비교: 같은 메일의 '규칙만'(기준 0)과 '전부 엑사원'(기준 1.01, replay) classify 결과를 메일마다 골라 붙여
   사유별 라우팅을 흉내 낸다. 순수 기준값 정책은 classify를 그 기준으로 직접 돌린 값과 같은지 확인해 적는다(합성 검증).
4. 상한: 엑사원 자리에 정답을 내는 가짜 모델(OracleClient)을 넣어, 모델이 완벽해도 합치기 규칙 때문에 못 고치는 메일을 가린다.
   캐시가 없는 세트에서도 '라우팅을 늘려 얻을 수 있는 최대 이득'을 잰다.

분류 함수 바꿔 끼우기: --classifier 모듈:함수. 함수는 (ClassifyRequest, llm, Settings) → .confidence · .action_types · .tasks ·
  .mentioned_me · .urgent · .is_follow_up · .priority · .fallback 을 가진 결과(ClassifyResponse 형식)를 낸다.
  라우팅이 settings.router_threshold 하나로 정해진다고 본다(합성 검증이 깨지면 보고서에 적힌다).
  --judge 모듈:함수는 사유(.reasons)를 읽을 때만 쓴다. 'none'이면 사유 표를 건너뛴다.
엑사원을 부르지 않는다(replay · 규칙만). data/dummy/eval.py는 evaluate · load_gold만 쓴다.
"""
import argparse
import hashlib
import importlib
import json
import sys
import time
from collections import defaultdict
from dataclasses import replace
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai"))
sys.path.insert(0, str(ROOT / "data/dummy"))

from app.core.config import get_settings  # noqa: E402
from app.llm.client import LLMError  # noqa: E402
from app.schemas.classify import ClassifyRequest, OwnerProfile, SenderFlags  # noqa: E402
from eval import evaluate, load_gold  # noqa: E402  data/dummy/eval.py

SETS = {"dev": "dummy_mails.json", "dev2": "dev2_mails.json", "dev3": "dev3_mails.json"}  # 테스트셋은 넣지 않는다(봉인)
DEFAULT_REPLAY = {"dev3": ROOT / "eval/reports/llm_cache_predictions_dev3_llm.json"}
FULL = ["주 유형", "Task 여부", "Task 수", "마감", "지목", "긴급", "재요청", "우선순위"]  # 메일 완전 정답 기준(eval.FIELDS와 같다)
CPU_S, GPU_S, PER_DAY = 22.0, 3.0, 200  # 메일 1통 엑사원 시간: CPU 11/3 실측(plan 4.4 · 4.5) · GPU [추정]
NEVER, ALWAYS = 0.0, 1.01
GOLD, UNK, ALLM = "gold", "unknown", "all_m"


def load_fn(spec: str):
    mod, fn = spec.split(":")
    return getattr(importlib.import_module(mod), fn)


class ReplayClient:
    """남긴 모델 출력(llm_cache_*.json)을 돌려준다. 없는 프롬프트는 LLMError → classify가 규칙 결과로 대신한다."""

    def __init__(self, path: Path, model: str):
        self.model, self.cache = model, json.loads(path.read_text(encoding="utf-8"))

    def chat_json(self, system, user, schema):
        out = self.cache.get(hashlib.sha256(f"{system}\0{user}".encode()).hexdigest()[:24])
        if out is None:
            raise LLMError("replay: 캐시에 없는 프롬프트")
        return out


class NoModel:
    """캐시 없는 세트: 모든 엑사원 호출이 실패해 규칙 결과로 대신한다(엑사원행 수만 센다)."""

    def __init__(self, model: str):
        self.model = model

    def chat_json(self, system, user, schema):
        raise LLMError("replay: 캐시 없는 세트")


class OracleClient:
    """상한 측정용 가짜 모델: 지금 메일의 정답(유형 · 할 일 · 기한 원문)을 모델 출력 형식으로 돌려준다.
    '엑사원이 완벽해도 합치기 규칙(classify._from_model) 때문에 못 고치는 메일'을 가려 라우팅의 최대 이득을 잰다."""

    def __init__(self, model: str):
        self.model, self.answer = model, None

    def chat_json(self, system, user, schema):
        g = self.answer
        return {"action_types": list(g["action_types"]),
                "tasks": [{"action": t["action"], "due_raw": t.get("due_raw") or "없음", "format": t.get("format") or "없음"} for t in g["tasks"]]}


def run_oracle(classify, reqs, gold, settings) -> dict:
    """모든 메일을 '정답을 내는 모델'로 보낸 classify 결과."""
    llm, s, by_id, preds = OracleClient(settings.model), replace(settings, router_threshold=ALWAYS), {o["mail"]["id"]: o["gold"] for o in gold}, {}
    for q in reqs:
        llm.answer = by_id[q.mail_id]
        preds[q.mail_id] = pred_of(classify(q, llm, s))
    return preds


def requests(name: str) -> list[ClassifyRequest]:
    data = json.loads((ROOT / "data/dummy" / SETS[name]).read_text(encoding="utf-8"))
    box, me = data["mailbox"], data["people"]["me"]
    owner = OwnerProfile(email=box["owner"], name=me["name"], position=me["position"], team=me["team"], member_of=box["member_of"])
    out = []
    for o in data["mails"]:
        m = o["mail"]
        out.append(ClassifyRequest(**{"from": m["from"]}, mail_id=m["id"], to=m["to"], cc=m["cc"], subject=m["subject"],
                                   body=m["body"], attachments=m["attachments"], received_at=m["received_at"], owner=owner,
                                   sender=SenderFlags(is_superior=m["from"] in box["superiors"], is_favorite=m["from"] in box["favorites"])))
    return out


def pred_of(r) -> dict:
    return {"id": r.mail_id, "action_types": list(r.action_types), "mentioned_me": r.mentioned_me, "urgent": r.urgent,
            "is_follow_up": r.is_follow_up, "priority": r.priority,
            "tasks": [{"action": t.text, "format": t.format, "due_raw": t.due_raw,
                       "due_at": t.due_at.strftime("%Y-%m-%dT%H:%M") if t.due_at else None} for t in r.tasks]}


def run(classify, reqs, llm, settings, t: float) -> tuple[dict, dict]:
    """기준 t로 classify를 돌린다. → (메일 id → 예측, 메일 id → {conf, routed, unknown})"""
    s = replace(settings, router_threshold=t)
    preds, meta = {}, {}
    for q in reqs:
        r = classify(q, llm, s)
        preds[q.mail_id] = pred_of(r)
        unknown = bool(r.fallback) and "replay" in str(r.fallback)
        meta[q.mail_id] = {"conf": r.confidence, "routed": r.confidence < t, "unknown": unknown}
    return preds, meta


def per_mail(gold: list, preds: dict) -> dict:
    """메일 id → 맞힌 칸. evaluate의 오답 목록에서 거꾸로 읽는다."""
    res = evaluate(gold, list(preds.values()))
    wrong = {row[0]: set(row[3]) for row in res["rows"]}
    out = {}
    for o in gold:
        mid, w = o["mail"]["id"], wrong.get(o["mail"]["id"], set())
        p = preds.get(mid, {})
        out[mid] = {"task": "Task 여부" not in w, "type": "주 유형" not in w, "full": not (w & set(FULL)),
                    "gold_task": bool(o["gold"]["tasks"]), "pred_task": bool(p.get("tasks")), "wrong": sorted(w & set(FULL))}
    return out


def summary(gold: list, preds: dict) -> dict:
    res = evaluate(gold, list(preds.values()))
    p, r, _, fn = res["bin"]["Task 여부"]
    return {"n": res["n"], "full": res["full"], "miss": fn, "prec": p, "rec": r, "type": res["acc"]["주 유형"]}


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def fmt_sum(s: dict) -> str:
    return f"{s['miss']} | {pct(s['prec'])} | {s['full']}/{s['n']} | {pct(s['type'])}"


def compose(gold, rule_p, all_p, all_m, route) -> tuple[dict, int, int]:
    """메일마다 route(id)면 '전부 엑사원' 결과, 아니면 '규칙만' 결과. → (예측, 엑사원행 수, 추정 불가 수)"""
    preds, n_route, n_unk = {}, 0, 0
    for o in gold:
        mid = o["mail"]["id"]
        if route(mid):
            n_route += 1
            n_unk += all_m[mid]["unknown"]
            preds[mid] = all_p[mid]
        else:
            preds[mid] = rule_p[mid]
    return preds, n_route, n_unk


def external(q: ClassifyRequest) -> bool:
    dom = lambda a: a.rsplit("@", 1)[-1].strip("<> ").lower()  # noqa: E731
    return "@" in q.from_ and dom(q.from_) != dom(q.owner.email)


def exempt_reasons(data: dict, sets: list[str], base: float = 0.8, min_n: int = 3) -> set[str]:
    """dev · dev2(세트에 있으면)의 엑사원행 메일 중 규칙만으로 완전 정답 100%(min_n통 이상)인 사유. dev3는 확인용이라 쓰지 않는다."""
    tune = [n for n in sets if n in ("dev", "dev2")]
    grp = defaultdict(list)
    for nm in tune:
        d = data[nm]
        for mid, x in d["rule_pm"].items():
            if d["rule_m"][mid]["conf"] < base:
                for rs in d["reasons"][mid]:
                    grp[rs].append(x["full"])
    return {rs for rs, xs in grp.items() if len(xs) >= min_n and all(xs)}


def policies(data: dict, sets: list[str]) -> list[str]:
    """사유별 라우팅 후보를 '규칙만' · '전부 엑사원' 결과를 메일마다 골라 붙여 비교한다."""
    if not all(data[n]["reasons"] for n in sets):
        return []
    ex = exempt_reasons(data, sets)
    conf = lambda d, mid: d["rule_m"][mid]["conf"]  # noqa: E731
    P = [("기준 0.80 (현행)", lambda d, mid: conf(d, mid) < 0.8),
         ("기준 0.75 (0.75 구간 생략: 요청 여러 개 · 참조 지목)", lambda d, mid: conf(d, mid) < 0.75),
         ("기준 0.70 (0.7 구간도 생략)", lambda d, mid: conf(d, mid) < 0.7),
         (f"기준 0.80 − dev·dev2 규칙 만점 사유 면제({' · '.join(sorted(ex)) or '없음'})",
          lambda d, mid: conf(d, mid) < 0.8 and not set(d["reasons"][mid]) <= ex),
         ("기준 0.80 + 사외 발신인데 규칙이 할 일을 찾은 메일", lambda d, mid: conf(d, mid) < 0.8 or (d["ext"][mid] and d["rule_pm"][mid]["pred_task"])),
         ("기준 0.90 (0.85 구간 전부 추가)", lambda d, mid: conf(d, mid) < 0.9)]
    L = ["", "## 7. 라우팅 정책 비교", "",
         "규칙만(기준 0) · 전부 엑사원(기준 1.01, replay) classify 결과를 메일마다 골라 붙였다. 면제 사유는 dev · dev2에서만 정했다(dev3는 확인용).",
         "추정 불가가 있으면 그만큼은 엑사원 효과를 모른다(규칙 결과로 셈).", "",
         "오른쪽 '상한' 열은 엑사원 자리에 정답을 내는 가짜 모델을 넣은 값이다 — 모델이 완벽해도 합치기 규칙 때문에 이 이상은 안 오른다.", "",
         "| 정책 | 세트 | 엑사원행 | 추정 불가 | 누락 | Task 정밀도 | 완전 정답 | 주 유형 | 상한: 누락 · 정밀도 · 완전 정답 · 주 유형 |",
         "|---|---|---|---|---|---|---|---|---|"]
    tot = {}
    for name, route in P:
        for nm in sets:
            d = data[nm]
            preds, n_route, n_unk = compose(d["gold"], d["rule_p"], d["all_p"], d["all_m"], lambda mid, d=d: route(d, mid))
            ora = {k: (d["ora_p"][k] if route(d, k) else d["rule_p"][k]) for k in d["rule_p"]}
            L.append(f"| {name} | {nm} | {n_route} | {n_unk} | {fmt_sum(summary(d['gold'], preds))} | {fmt_sum(summary(d['gold'], ora)).replace(' | ', ' · ')} |")
            t = tot.setdefault(name, [0, 0])
            t[0] += n_route
            t[1] += len(d["gold"])
    L += ["", "| 정책 | 엑사원행 합계 | 비율 | 하루 200통 CPU | GPU `[추정]` |", "|---|---|---|---|---|"]
    for name, (r, n) in tot.items():
        L.append(f"| {name} | {r}/{n} | {pct(r / n)} | {r / n * PER_DAY * CPU_S / 60:.0f}분 | {r / n * PER_DAY * GPU_S / 60:.0f}분 |")
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", nargs="+", choices=SETS, default=list(SETS))
    ap.add_argument("--replay", action="append", default=[], help="세트=캐시경로 (기본 dev3=eval/reports/llm_cache_predictions_dev3_llm.json)")
    ap.add_argument("--replay-dir", type=Path, default=None,
                    help="세트마다 이 폴더의 llm_cache_all_<세트>.json(전 메일 엑사원 출력)을 쓴다. 있으면 기준 0.8 이상 · 1.0까지 정확도가 나온다")
    ap.add_argument("--classifier", default="app.pipeline.classify:classify")
    ap.add_argument("--judge", default="app.pipeline.rules.mail_rules_v1:judge")
    ap.add_argument("--lo", type=float, default=0.30)
    ap.add_argument("--hi", type=float, default=1.00)
    ap.add_argument("--step", type=float, default=0.05)
    ap.add_argument("--out", type=Path, default=ROOT / "eval/reports/router_sweep.md")
    a = ap.parse_args()

    classify = load_fn(a.classifier)
    judge = None if a.judge == "none" else load_fn(a.judge)
    settings = replace(get_settings(), llm_enabled=False)
    replay = {k: v for k, v in DEFAULT_REPLAY.items() if v.exists()}
    if a.replay_dir:
        for k in SETS:
            if (f := a.replay_dir / f"llm_cache_all_{k}.json").exists():
                replay[k] = f
    for kv in a.replay:
        k, v = kv.split("=", 1)
        replay[k] = Path(v) if Path(v).is_absolute() else ROOT / v
    n_steps = int(round((a.hi - a.lo) / a.step))
    thresholds = [round(a.lo + i * a.step, 2) for i in range(n_steps + 1)]
    t_start = time.perf_counter()

    data = {}  # 세트 → 계산 결과
    for name in a.sets:
        gold, reqs = load_gold(SETS[name]), requests(name)
        llm = ReplayClient(replay[name], settings.model) if name in replay else NoModel(settings.model)
        rule_p, rule_m = run(classify, reqs, llm, settings, NEVER)
        all_p, all_m = run(classify, reqs, llm, settings, ALWAYS)
        reasons = {q.mail_id: (list(judge(q).reasons) or ["(사유 없음)"]) if judge else [] for q in reqs}
        sweep = []
        for t in thresholds:
            p, m = run(classify, reqs, llm, settings, t)
            routed = sum(x["routed"] for x in m.values())
            unk = sum(x["routed"] and x["unknown"] for x in m.values())
            comp, _, _ = compose(gold, rule_p, all_p, all_m, lambda mid, t=t: rule_m[mid]["conf"] < t)
            sweep.append({"t": t, "routed": routed, "unknown": unk, "sum": summary(gold, p),
                          "composed_same": comp == p})
        ora_p = run_oracle(classify, reqs, gold, settings)
        data[name] = {"ora_p": ora_p, "ora_pm": per_mail(gold, ora_p), "gold": gold, "rule_p": rule_p, "rule_m": rule_m, "all_p": all_p, "all_m": all_m,
                      "reasons": reasons, "sweep": sweep, "replay": replay.get(name), "ext": {q.mail_id: external(q) for q in reqs},
                      "rule_pm": per_mail(gold, rule_p), "all_pm": per_mail(gold, all_p)}

    L = ["# 라우터 기준 쓸기 · 규칙 확신도 보정", "",
         f"- 실행 시각: {datetime.now():%Y-%m-%d %H:%M} · 분류 함수 `{a.classifier}` · 사유 `{a.judge}` · 실행 {time.perf_counter() - t_start:.1f}초",
         f"- 세트: {' · '.join(f'{n}({len(data[n][GOLD])}통)' for n in a.sets)} · 테스트셋 제외(봉인)",
         f"- replay: {', '.join(f'{k}={v.name}' for k, v in replay.items() if k in a.sets) or '없음'} — 엑사원을 부르지 않았다",
         f"- 캐시 적중(전부 엑사원으로 보냈을 때 출력이 있는 메일): {' · '.join(f'{n} {sum(not x[UNK] for x in data[n][ALLM].values())}/{len(data[n][GOLD])}' for n in a.sets)}",
         f"- 시간 환산: 하루 {PER_DAY}통 × 엑사원행 비율 × CPU {CPU_S:.0f}초(11/3 실측) · GPU {GPU_S:.0f}초 `[추정]`", ""]

    L += ["## 1. 기준값별 엑사원행 · 시간", "",
          "| 기준 | " + " | ".join(f"{n} 엑사원행" for n in a.sets) + " | 합계 비율 | 하루 200통 CPU | GPU `[추정]` |",
          "|---|" + "---|" * len(a.sets) + "---|---|---|"]
    total_n = sum(len(data[n]["gold"]) for n in a.sets)
    for i, t in enumerate(thresholds):
        cells = [f"{data[n]['sweep'][i]['routed']}/{len(data[n]['gold'])}" for n in a.sets]
        tot = sum(data[n]["sweep"][i]["routed"] for n in a.sets)
        ratio = tot / total_n
        L.append(f"| {t:.2f} | " + " | ".join(cells) + f" | {pct(ratio)} | {ratio * PER_DAY * CPU_S / 60:.0f}분 | {ratio * PER_DAY * GPU_S / 60:.0f}분 |")

    for n in a.sets:
        d = data[n]
        L += ["", f"## 2. 기준값별 정확도 · {n}" + (f" (replay {d['replay'].name})" if d["replay"] else " (캐시 없음 → 규칙 결과만)"), "",
              "누락 = 할 일 메일을 할 일 없음으로 낸 수(D15 기준 0). 추정 불가 = 엑사원행인데 캐시에 출력이 없어 규칙 결과로 대신한 메일.", "",
              "| 기준 | 엑사원행 | 추정 불가 | 누락 | Task 정밀도 | 완전 정답 | 주 유형 | 합성=직접 |", "|---|---|---|---|---|---|---|---|"]
        prev = None
        for s in d["sweep"]:
            key = (s["routed"], s["unknown"], fmt_sum(s["sum"]))
            if key == prev:
                continue  # 확신도 값이 띄엄띄엄이라 같은 줄은 생략
            prev = key
            L.append(f"| {s['t']:.2f} | {s['routed']} | {s['unknown']} | {fmt_sum(s['sum'])} | {'O' if s['composed_same'] else 'X'} |")

    # 3. 보정: 규칙만 결과를 확신도 값별로
    L += ["", "## 3. 규칙 확신도 보정 (규칙만 결과)", "",
          "확신도 값마다 규칙만으로 맞힌 비율. 기준 0.8 이상이면 엑사원에 가지 않으므로, 이 구간의 오답은 엑사원이 고칠 기회가 없다.", "",
          "| 세트 | 확신도 | 메일 | Task 여부 | 누락(할 일→없음) | 과잉(없음→할 일) | 주 유형 | 완전 정답 |", "|---|---|---|---|---|---|---|---|"]
    for n in a.sets + ["합계"]:
        names = a.sets if n == "합계" else [n]
        buckets = defaultdict(list)
        for nm in names:
            for mid, x in data[nm]["rule_pm"].items():
                buckets[data[nm]["rule_m"][mid]["conf"]].append(x)
        for c in sorted(buckets):
            xs = buckets[c]
            miss = sum(x["gold_task"] and not x["pred_task"] for x in xs)
            over = sum(x["pred_task"] and not x["gold_task"] for x in xs)
            L.append(f"| {n} | {c:.2f} | {len(xs)} | {pct(sum(x['task'] for x in xs) / len(xs))} | {miss} | {over} | "
                     f"{pct(sum(x['type'] for x in xs) / len(xs))} | {pct(sum(x['full'] for x in xs) / len(xs))} |")

    if judge:
        L += ["", "## 4. judge 사유별 (규칙만 · 엑사원 replay)", "",
              "사유가 여러 개면 각 사유에 한 번씩 센다. '엑사원' 칸은 replay 캐시가 있는 메일만(그 외 —).", "",
              "| 사유 | 세트 | 메일 | 확신도 | 규칙 Task 여부 | 규칙 주 유형 | 규칙 완전 정답 | 엑사원 완전 정답(캐시 있는 메일) |", "|---|---|---|---|---|---|---|---|"]
        rows = defaultdict(list)
        for nm in a.sets:
            for mid, x in data[nm]["rule_pm"].items():
                for rs in data[nm]["reasons"][mid]:
                    rows[(rs, nm)].append((mid, x, data[nm]))
        for (rs, nm), xs in sorted(rows.items()):
            confs = sorted({d["rule_m"][mid]["conf"] for mid, _, d in xs})
            llm_x = [d["all_pm"][mid] for mid, _, d in xs if not d["all_m"][mid]["unknown"] and d["replay"]]
            llm_cell = f"{sum(y['full'] for y in llm_x)}/{len(llm_x)}" if llm_x else "—"
            L.append(f"| {rs} | {nm} | {len(xs)} | {'·'.join(f'{c:.2f}' for c in confs)} | "
                     f"{sum(x['task'] for _, x, _ in xs)}/{len(xs)} | {sum(x['type'] for _, x, _ in xs)}/{len(xs)} | "
                     f"{sum(x['full'] for _, x, _ in xs)}/{len(xs)} | {llm_cell} |")

    # 5. 과신 목록: 기준 0.8 이상인데 규칙이 틀린 메일 (테스트셋 아님)
    L += ["", "## 5. 과신 메일 (규칙 확신도 ≥ 0.8인데 완전 정답 아님, 엑사원에 가지 않음)", "",
          "| 세트 | ID | 확신도 | 사유 | 틀린 칸 | 제목 |", "|---|---|---|---|---|---|"]
    for nm in a.sets:
        subj = {o["mail"]["id"]: o["mail"]["subject"] for o in data[nm]["gold"]}
        for mid, x in data[nm]["rule_pm"].items():
            c = data[nm]["rule_m"][mid]["conf"]
            if c >= 0.8 and not x["full"]:
                L.append(f"| {nm} | {mid} | {c:.2f} | {' · '.join(data[nm]['reasons'][mid])} | {', '.join(x['wrong'])} | {subj[mid].replace('|', '/')} |")

    # 6. 엑사원 효과: replay가 있는 세트에서 엑사원행 메일마다 규칙 vs 엑사원
    for nm in a.sets:
        d = data[nm]
        if not d["replay"]:
            continue
        L += ["", f"## 6. 엑사원이 고친 · 망친 메일 · {nm} (replay, 캐시 있는 메일만)", "",
              "| ID | 확신도 | 사유 | 규칙 완전 정답 | 엑사원 완전 정답 | 규칙 틀린 칸 → 엑사원 틀린 칸 |", "|---|---|---|---|---|---|"]
        fixed = broke = 0
        for mid in d["rule_pm"]:
            if d["all_m"][mid]["unknown"]:
                continue
            r0, r1 = d["rule_pm"][mid], d["all_pm"][mid]
            fixed += (not r0["full"]) and r1["full"]
            broke += r0["full"] and not r1["full"]
            L.append(f"| {mid} | {d['rule_m'][mid]['conf']:.2f} | {' · '.join(d['reasons'][mid])} | {'O' if r0['full'] else 'X'} | "
                     f"{'O' if r1['full'] else 'X'} | {', '.join(r0['wrong']) or '-'} → {', '.join(r1['wrong']) or '-'} |")
        L.append(f"\n- 엑사원이 고친 메일 {fixed}통 · 망친 메일 {broke}통")

    L += policies(data, a.sets)
    L += ["", "## 8. 완벽한 모델이 받아도 틀리는 메일 (합치기 규칙의 한계)", "",
          "엑사원 자리에 정답을 넣어도 완전 정답이 안 되는 메일. 이 메일들은 라우팅 기준을 바꿔도 고쳐지지 않는다 — 규칙 · 합치기를 고쳐야 한다.", "",
          "| 세트 | ID | 확신도 | 사유 | 규칙만 틀린 칸 | 정답 모델 넣어도 틀린 칸 |", "|---|---|---|---|---|---|"]
    for nm in a.sets:
        d = data[nm]
        for mid, x in d["ora_pm"].items():
            if not x["full"]:
                L.append(f"| {nm} | {mid} | {d['rule_m'][mid]['conf']:.2f} | {' · '.join(d['reasons'][mid])} | {', '.join(d['rule_pm'][mid]['wrong']) or '-'} | {', '.join(x['wrong'])} |")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"→ {a.out.relative_to(ROOT) if a.out.is_relative_to(ROOT) else a.out}")


if __name__ == "__main__":
    main()
