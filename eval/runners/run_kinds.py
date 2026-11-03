"""메일 성격(kind) 채점 (유형 체계 kinds-v1, 2026-11-03). 엑사원을 부르지 않는다 — 규칙 v1.5 + kind 점수기만.

사용 (레포 루트에서):
  ai/.venv/bin/python eval/runners/run_kinds.py                    # dev · dev2 · dev3
  ai/.venv/bin/python eval/runners/run_kinds.py --sets dev,dev2    # 맞추기용 세트만
결과: eval/reports/kinds_<세트>.md + 표준출력 요약. 정답: data/dummy/kinds_gold.json(kind) · <세트>_mails.json(유형 · 할 일)

보는 것
- kind 정확도, kind로 정한 주 유형 vs 규칙 v1.5 주 유형(같은 정답 대비), kind가 확신할 때만 kind를 쓰는 섞기(hybrid)
- Task 여부(규칙 할 일 그대로) 재현율 · 정밀도, '참고' 칸 kind가 규칙 할 일을 지우면 어떻게 되는지(veto, 채택 여부 판단용)
- 엑사원행: 규칙 라우터(확신도 < 기준) · kind 애매 · 둘 합친 것 · 문지기(kind가 '할 일 없음'을 확신하면 규칙 라우터행이어도 건너뜀).
  규칙 오답 · 누락을 얼마나 덮는지, 문지기가 건너뛴 메일에 정답 할 일이 있는지(0이어야 한다)
- --llm-preds dev3=eval/reports/predictions_dev3_llm.json: 이미 남은 엑사원 실행 결과에 문지기 · kind 유형을 얹으면 어떻게 되는지(엑사원 재호출 없음)
테스트셋(test · test3)은 넣지 않는다(봉인, kinds_gold에도 라벨이 없다).
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai"))

from app.pipeline.kinds import BY_ID, MARGIN_MIN, SCORE_MIN, classify_kind, kind_types  # noqa: E402
from app.pipeline.rules.mail_rules_v1 import RULES_VERSION, judge  # noqa: E402
from app.schemas.classify import ClassifyRequest, OwnerProfile, SenderFlags  # noqa: E402

SETS = {"dev": "dummy_mails.json", "dev2": "dev2_mails.json", "dev3": "dev3_mails.json"}
VETO_KINDS = {"K14", "K15", "K16", "K19", "K20"}  # '참고' 칸에서 규칙 할 일을 지워 볼 kind (채택 여부는 재현율로 판단, 기본은 채택 안 함)


def requests(set_name: str):
    data = json.loads((ROOT / "data/dummy" / SETS[set_name]).read_text(encoding="utf-8"))
    box, me = data["mailbox"], data["people"]["me"]
    owner = OwnerProfile(email=box["owner"], name=me["name"], position=me["position"], team=me["team"], member_of=box["member_of"])
    for o in data["mails"]:
        m = o["mail"]
        req = ClassifyRequest(**{"from": m["from"]}, mail_id=m["id"], to=m["to"], cc=m["cc"], subject=m["subject"], body=m["body"],
                              attachments=m["attachments"], received_at=m["received_at"], owner=owner,
                              sender=SenderFlags(is_superior=m["from"] in box["superiors"], is_favorite=m["from"] in box["favorites"]))
        yield req, o["gold"]


def pct(a, b):
    return f"{a / b:.1%}" if b else "-"


def run(set_name: str, gold_kinds: dict, threshold: float) -> dict:
    rows = []
    for req, g in requests(set_name):
        r = judge(req)
        k = classify_kind(req, r)
        kt = kind_types(k, r.action_types)
        gk = gold_kinds.get(req.mail_id)
        rows.append({
            "id": req.mail_id, "subject": req.subject, "gold_kind": gk, "kind": k.kind.id if k.kind else None,
            "second": k.second.id if k.second else None, "score": k.score, "margin": k.margin, "needs_model": k.needs_model, "why": k.why,
            "gold_type": g["action_types"][0], "rule_type": r.action_types[0], "kind_type": kt[0],
            "hybrid_type": r.action_types[0] if k.needs_model else kt[0],
            "gold_task": bool(g["tasks"]), "rule_task": bool(r.tasks), "lane": k.lane,
            "rule_conf": r.confidence, "routed_rule": r.confidence < threshold,
            # 충돌(규칙 할 일 vs '참고' kind)이어도 kind 여유가 충분하면 지운다 — 채택 여부 판단용 가정
            "veto": bool(r.tasks) and k.kind is not None and k.kind.id in VETO_KINDS and k.margin >= MARGIN_MIN and k.score >= SCORE_MIN,
            # 문지기: kind가 '할 일 없음'을 확신하고 나를 향한 요청 문장도 없으면 규칙 라우터행이어도 엑사원에 묻지 않는다
            "sure_no_task": k.kind is not None and not k.needs_model and k.lane != "할 일" and "request_loose" not in k.signals.on,
        })
        rows[-1]["routed_gate"] = k.needs_model or (rows[-1]["routed_rule"] and not rows[-1]["sure_no_task"])
    return {"set": set_name, "rows": rows}


def task_pr(rows, key):
    tp = sum(1 for x in rows if x["gold_task"] and key(x))
    fp = sum(1 for x in rows if not x["gold_task"] and key(x))
    fn = sum(1 for x in rows if x["gold_task"] and not key(x))
    return tp, fp, fn


def summarize(res: dict) -> dict:
    rows = res["rows"]
    n = len(rows)
    s = {"n": n,
         "kind": sum(x["kind"] == x["gold_kind"] for x in rows),
         "rule_type": sum(x["rule_type"] == x["gold_type"] for x in rows),
         "kind_type": sum(x["kind_type"] == x["gold_type"] for x in rows),
         "hybrid_type": sum(x["hybrid_type"] == x["gold_type"] for x in rows),
         "task": task_pr(rows, lambda x: x["rule_task"]),
         "task_veto": task_pr(rows, lambda x: x["rule_task"] and not x["veto"]),
         "routed_rule": sum(x["routed_rule"] for x in rows),
         "routed_kind": sum(x["needs_model"] for x in rows),
         "routed_union": sum(x["routed_rule"] or x["needs_model"] for x in rows),
         "routed_gate": sum(x["routed_gate"] for x in rows),
         "gate_skipped_task": [x["id"] for x in rows if x["routed_rule"] and not x["routed_gate"] and x["gold_task"]]}
    rule_wrong = [x for x in rows if x["rule_type"] != x["gold_type"] or x["rule_task"] != x["gold_task"]]
    missed = [x for x in rows if x["gold_task"] and not x["rule_task"]]
    s["rule_wrong"] = len(rule_wrong)
    s["rule_wrong_routed_rule"] = sum(x["routed_rule"] for x in rule_wrong)
    s["rule_wrong_routed_union"] = sum(x["routed_rule"] or x["needs_model"] for x in rule_wrong)
    s["missed"] = len(missed)
    s["missed_routed_rule"] = sum(x["routed_rule"] for x in missed)
    s["missed_routed_union"] = sum(x["routed_rule"] or x["needs_model"] for x in missed)
    s["missed_routed_gate"] = sum(x["routed_gate"] for x in missed)
    s["lanes"] = Counter(x["lane"] for x in rows)
    # 확신한 kind의 정확도(엑사원에 안 보내는 kind가 얼마나 맞나)
    sure = [x for x in rows if not x["needs_model"]]
    s["sure"] = len(sure)
    s["sure_kind"] = sum(x["kind"] == x["gold_kind"] for x in sure)
    s["sure_type"] = sum(x["kind_type"] == x["gold_type"] for x in sure)
    return s


def with_llm(res: dict, path: Path) -> list[str]:
    """이미 남은 엑사원 실행(predictions_<세트>_llm.json)에 문지기 · kind 유형을 얹는다. 엑사원을 다시 부르지 않는다.
    문지기가 건너뛴 메일은 규칙 결과(할 일 없음)를, kind가 확신하면 주 유형은 kind 부모를 쓴다.
    kind만 엑사원행으로 보낸 메일은 기존 실행에 엑사원 출력이 없어 기존 결과(규칙 경로)를 그대로 쓴다(건수를 적는다)."""
    preds = {p["id"]: p for p in json.loads(path.read_text(encoding="utf-8"))}
    rows = res["rows"]

    def tally(pick):
        tp = fp = fn = typ = 0
        for x in rows:
            has, t0 = pick(x)
            tp += has and x["gold_task"]
            fp += has and not x["gold_task"]
            fn += (not has) and x["gold_task"]
            typ += t0 == x["gold_type"]
        return tp, fp, fn, typ

    def base(x):
        p = preds[x["id"]]
        return bool(p["tasks"]), p["action_types"][0]

    def gated(x):
        p = preds[x["id"]]
        has = bool(p["tasks"])
        if p.get("_source") == "exaone" and not x["routed_gate"]:  # 문지기가 건너뜀 → 규칙 결과
            has = x["rule_task"]
        sure = not x["needs_model"]
        return has, (x["kind_type"] if sure else p["action_types"][0])

    only_kind = sum(1 for x in rows if x["routed_gate"] and preds[x["id"]].get("_source") != "exaone")
    skipped = [x["id"] for x in rows if preds[x["id"]].get("_source") == "exaone" and not x["routed_gate"]]
    n = len(rows)
    L = ["", f"## 기존 엑사원 실행에 얹기 · {path.name} (엑사원 재호출 없음)", "",
         "| 방식 | 엑사원 호출 | Task 재현율 | Task 정밀도 | 누락 | 주 유형 |", "|---|---|---|---|---|---|"]
    for name, f, calls in (("기존(규칙 v1.5 라우터 + 엑사원)", base, sum(1 for p in preds.values() if p.get("_source") == "exaone")),
                           ("문지기 + kind 유형", gated, sum(1 for x in rows if x["routed_gate"]))):
        tp, fp, fn, typ = tally(f)
        L.append(f"| {name} | {calls} | {pct(tp, tp + fn)} | {pct(tp, tp + fp)} | {fn} | {pct(typ, n)} |")
    L += [f"- 문지기가 건너뛴 기존 엑사원 메일 {len(skipped)}통: {' '.join(skipped)}",
          f"- kind만 엑사원행으로 보낸 메일 {only_kind}통은 기존 실행에 엑사원 출력이 없어 기존 결과를 썼다(엑사원 실측 필요)"]
    return L


def report(res: dict, s: dict, threshold: float) -> str:
    rows, n = res["rows"], s["n"]
    tp, fp, fn = s["task"]
    vtp, vfp, vfn = s["task_veto"]
    L = [f"# 메일 성격(kind) 채점 · {res['set']}", "",
         f"- 버전: 규칙 {RULES_VERSION} · kinds-v1(21종) · 애매 기준 margin < {MARGIN_MIN} 또는 점수 < {SCORE_MIN} · 라우터 기준 {threshold}",
         f"- 정답: data/dummy/kinds_gold.json(kind, Claude 라벨 · 사람 검수 전) · {SETS[res['set']]}(유형 · 할 일)", "",
         "| 지표 | 값 |", "|---|---|",
         f"| kind 정확도 | {s['kind']}/{n} ({pct(s['kind'], n)}) |",
         f"| 주 유형 · 규칙 v1.5 | {s['rule_type']}/{n} ({pct(s['rule_type'], n)}) |",
         f"| 주 유형 · kind 부모 | {s['kind_type']}/{n} ({pct(s['kind_type'], n)}) |",
         f"| 주 유형 · 섞기(kind 확신 시 kind, 아니면 규칙) | {s['hybrid_type']}/{n} ({pct(s['hybrid_type'], n)}) |",
         f"| kind 확신(엑사원 안 보냄) 메일 · 그중 kind 정답 · 주 유형 정답 | {s['sure']} · {s['sure_kind']} · {s['sure_type']} |",
         f"| Task 여부(규칙 할 일) 재현율 · 정밀도 · 누락 | {pct(tp, tp + fn)} · {pct(tp, tp + fp)} · {fn} |",
         f"| (가정) '참고' kind가 규칙 할 일을 지우면 재현율 · 정밀도 · 누락 | {pct(vtp, vtp + vfn)} · {pct(vtp, vtp + vfp)} · {vfn} |",
         f"| 엑사원행 · 규칙 라우터 / kind 애매 / 합침 / 문지기 | {s['routed_rule']} / {s['routed_kind']} / {s['routed_union']} / {s['routed_gate']} |",
         f"| 문지기가 건너뛴 메일 중 정답 할 일 메일 (0이어야) | {len(s['gate_skipped_task'])} {' '.join(s['gate_skipped_task'])} |",
         f"| 규칙 오답(주 유형 또는 Task 여부) 중 엑사원행 · 라우터 / 합침 | {s['rule_wrong_routed_rule']}/{s['rule_wrong']} · {s['rule_wrong_routed_union']}/{s['rule_wrong']} |",
         f"| 규칙 할 일 누락 중 엑사원행 · 라우터 / 합침 / 문지기 | {s['missed_routed_rule']}/{s['missed']} · {s['missed_routed_union']}/{s['missed']} · {s['missed_routed_gate']}/{s['missed']} |",
         f"| 칸 분포 | {' · '.join(f'{k} {v}' for k, v in sorted(s['lanes'].items(), key=lambda kv: str(kv[0])))} |",
         "", "## kind 혼동 (정답 → 예측, 틀린 것만)", "", "| 정답 | 예측 | 건수 |", "|---|---|---|"]
    conf = Counter((x["gold_kind"], x["kind"]) for x in rows if x["gold_kind"] != x["kind"])
    L += [f"| {g} {BY_ID[g].name if g in BY_ID else ''} | {p} {BY_ID[p].name if p in BY_ID else ''} | {c} |" for (g, p), c in conf.most_common()]
    L += ["", "## 틀린 메일 (kind 또는 kind 주 유형)", "",
          "| ID | 제목 | 정답 kind → 예측 (2등) | 점수 · 차이 | 주 유형 정답 / 규칙 / kind | 엑사원행 사유 |", "|---|---|---|---|---|---|"]
    for x in rows:
        if x["kind"] != x["gold_kind"] or x["kind_type"] != x["gold_type"]:
            L.append(f"| {x['id']} | {x['subject'][:36]} | {x['gold_kind']} → {x['kind']} ({x['second']}) | {x['score']:.1f} · {x['margin']:.1f} | "
                     f"{x['gold_type']} / {x['rule_type']} / {x['kind_type']} | {' · '.join(x['why'])} |")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", default="dev,dev2,dev3")
    ap.add_argument("--threshold", type=float, default=0.8, help="규칙 라우터 기준(ai 설정 ROUTER_THRESHOLD 기본값과 같게)")
    ap.add_argument("--dump", type=Path, default=None, help="메일별 결과 JSON을 이 폴더에 남긴다(분석용)")
    ap.add_argument("--llm-preds", action="append", default=[], help="세트=기존 엑사원 predictions 경로 (예: dev3=eval/reports/predictions_dev3_llm.json)")
    a = ap.parse_args()
    gold = json.loads((ROOT / "data/dummy/kinds_gold.json").read_text(encoding="utf-8"))["labels"]
    out_dir = ROOT / "eval/reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in a.sets.split(","):
        res = run(name, gold[name], a.threshold)
        s = summarize(res)
        md = report(res, s, a.threshold)
        llm_preds = dict(x.split("=", 1) for x in a.llm_preds)
        if name in llm_preds:
            md += "\n".join(with_llm(res, ROOT / llm_preds[name])) + "\n"
        (out_dir / f"kinds_{name}.md").write_text(md, encoding="utf-8")
        if a.dump:
            a.dump.mkdir(parents=True, exist_ok=True)
            (a.dump / f"kinds_{name}.json").write_text(json.dumps(res["rows"], ensure_ascii=False, indent=1), encoding="utf-8")
        tp, fp, fn = s["task"]
        n = s["n"]
        print(f"{name}: kind {s['kind']}/{n} · 주 유형 규칙 {pct(s['rule_type'], n)} → kind {pct(s['kind_type'], n)} · 섞기 {pct(s['hybrid_type'], n)} · "
              f"Task 재현율 {pct(tp, tp + fn)} 정밀도 {pct(tp, tp + fp)} · 엑사원행 규칙 {s['routed_rule']} / kind {s['routed_kind']} / 합침 {s['routed_union']} / 문지기 {s['routed_gate']} · "
              f"누락 {s['missed']} 중 합침 엑사원행 {s['missed_routed_union']} → eval/reports/kinds_{name}.md")


if __name__ == "__main__":
    main()
