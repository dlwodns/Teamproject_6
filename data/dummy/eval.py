# -*- coding: utf-8 -*-
"""메타데이터 추출 평가
시스템 출력(predictions)을 dummy_mails.json의 gold와 비교해 지표를 계산하고 eval_report_<이름>.md를 만든다.

사용:  python eval.py predictions.json      # -> eval_report_predictions.md
       python eval.py predictions.json test_mails.json   # 테스트셋 정답으로 채점
       python eval.py --selfcheck            # 채점 로직 자체 점검

predictions.json 형식: gold와 같은 필드에 메일 id를 붙인 리스트. 빠진 필드·빠진 메일은 오답 처리.
  [{"id": "M-0001", "sender": {...}, "action_types": [...], "mentioned_me": true,
    "tasks": [{"action": "...", "format": "xlsx", "due_at": "2026-10-21T18:00"}],
    "urgent": false, "is_follow_up": false, "priority": "P3"}, ...]
"""
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).parent
FIELDS = ["주 유형", "Task 여부", "Task 수", "마감", "지목", "긴급", "재요청", "우선순위"]  # 메일 완전 정답 판정 기준


def due(s):  # 초·타임존 표기 차이는 무시하고 분 단위로 비교
    try:
        return datetime.fromisoformat(s).strftime("%Y-%m-%dT%H:%M") if s else None
    except (TypeError, ValueError):
        return "INVALID"


def fmt(s):  # "pptx/drawio" == "drawio, .PPTX"
    return frozenset(x.strip().lstrip(".").lower() for x in s.replace(",", "/").split("/") if x.strip()) if s else frozenset()


def sim(a, b):
    # ponytail: 글자 단위 difflib 유사도. 표현이 크게 달라도 같은 할 일이면 낮게 나오므로, 필요하면 임베딩/LLM 판정으로 교체
    return SequenceMatcher(None, a or "", b or "").ratio()


def pair_tasks(gt, pt):  # action 유사도가 높은 순으로 1:1 매칭 (메일당 Task 최대 2개라 전수 비교로 충분)
    cand = sorted(((sim(g["action"], p.get("action")), i, j) for i, g in enumerate(gt) for j, p in enumerate(pt)), reverse=True)
    used_g, used_p, pairs = set(), set(), []
    for s, i, j in cand:
        if i not in used_g and j not in used_p:
            used_g.add(i), used_p.add(j), pairs.append((gt[i], pt[j], s))
    return pairs


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def evaluate(mails, preds):
    by_id = {p.get("id"): p for p in preds}
    bin_cnt = {k: Counter() for k in ("Task 여부", "지목", "긴급", "재요청")}
    lab = Counter()  # action_types 다중 라벨 micro
    type_cnt = defaultdict(Counter)  # 유형별 tp/fp/fn
    acc = Counter()
    conf = Counter()  # 우선순위 (정답, 예측)
    task = Counter()
    sims = []
    tag_ok, tag_n = Counter(), Counter()
    rows = []
    for o in mails:
        ml, g = o["mail"], o["gold"]
        p = by_id.get(ml["id"], {})
        sp, sg = p.get("sender") or {}, g["sender"]
        gt, pt = g["tasks"], [t for t in (p.get("tasks") or []) if isinstance(t, dict)]
        gtypes, ptypes = g["action_types"], p.get("action_types") or []

        ok = {"주 유형": bool(ptypes) and ptypes[0] == gtypes[0],
              "Task 여부": bool(pt) == bool(gt),
              "Task 수": len(pt) == len(gt),
              "마감": sorted(map(str, (due(t["due_at"]) for t in gt))) == sorted(map(str, (due(t.get("due_at")) for t in pt))),
              "지목": p.get("mentioned_me") == g["mentioned_me"],
              "긴급": p.get("urgent") == g["urgent"],
              "재요청": p.get("is_follow_up") == g["is_follow_up"],
              "우선순위": p.get("priority") == g["priority"],
              "발신자 이름": sp.get("name") == sg["name"],
              "발신자 직급": sp.get("position") == sg["position"],
              "발신자 팀": sp.get("team") == sg["team"]}
        for k, v in ok.items():
            acc[k] += v

        for k, gv, pv in (("Task 여부", bool(gt), bool(pt)), ("지목", g["mentioned_me"], p.get("mentioned_me") is True),
                          ("긴급", g["urgent"], p.get("urgent") is True), ("재요청", g["is_follow_up"], p.get("is_follow_up") is True)):
            bin_cnt[k]["tp" if gv and pv else "fn" if gv else "fp" if pv else "tn"] += 1

        gs, ps = set(gtypes), set(ptypes)
        lab.update(tp=len(gs & ps), fp=len(ps - gs), fn=len(gs - ps))
        for t in gs | ps:
            type_cnt[t]["tp" if t in gs & ps else "fn" if t in gs else "fp"] += 1
        conf[(g["priority"], p.get("priority"))] += 1

        pairs = pair_tasks(gt, pt)
        task["gold"] += len(gt)
        task["pred"] += len(pt)
        task["paired"] += len(pairs)
        for gt_, pt_, s in pairs:
            sims.append(s)
            task["due_ok"] += due(gt_["due_at"]) == due(pt_.get("due_at"))
            task["fmt_ok"] += fmt(gt_["format"]) == fmt(pt_.get("format"))

        all_ok = all(ok[k] for k in FIELDS)
        for t in g["tags"] or ["(태그 없음)"]:
            tag_n[t] += 1
            tag_ok[t] += all_ok
        wrong = [k for k, v in ok.items() if not v]
        if wrong:
            rows.append((ml["id"], ml["subject"], ", ".join(g["tags"]), wrong, g, p, ml["id"] not in by_id))

    n = len(mails)
    return dict(n=n, missing=sum(1 for o in mails if o["mail"]["id"] not in by_id),
                full=n - sum(1 for r in rows if set(r[3]) & set(FIELDS)),
                acc={k: v / n for k, v in acc.items()},
                bin={k: prf(c["tp"], c["fp"], c["fn"]) + (c["fn"],) for k, c in bin_cnt.items()},
                lab=prf(lab["tp"], lab["fp"], lab["fn"]),
                types={t: prf(c["tp"], c["fp"], c["fn"]) + (c["tp"] + c["fn"],) for t, c in sorted(type_cnt.items())},
                conf=conf, task=task, sim=sum(sims) / len(sims) if sims else 0.0,
                tags={t: (tag_ok[t], tag_n[t]) for t in sorted(tag_n, key=lambda t: (t == "(태그 없음)", t))},
                rows=rows)


def pct(x):
    return f"{x * 100:.1f}%"


def report(r, pred_path, gold_name="dummy_mails.json"):
    t = r["task"]
    L = [f"# 추출 평가 결과 · {pred_path.name}", "",
         f"- 평가 시각: {datetime.now():%Y-%m-%d %H:%M} · 정답: {gold_name} ({r['n']}건)",
         f"- 예측 누락 메일: {r['missing']}건 (누락은 전 필드 오답 처리)",
         f"- **메일 완전 정답: {r['full']}/{r['n']} ({pct(r['full'] / r['n'])})** — 기준: {', '.join(FIELDS)} 모두 일치",
         "", "## 1. 핵심 지표", "",
         "| 지표 | 값 | 설명 |", "|---|---|---|",
         f"| Task 메일 재현율 | **{pct(r['bin']['Task 여부'][1])}** | 할 일이 있는 메일을 놓치지 않은 비율 (누락 방지 핵심) |",
         f"| Task 메일 정밀도 | {pct(r['bin']['Task 여부'][0])} | Task로 잡은 메일 중 실제 Task 메일 비율 |",
         f"| 주 유형 정확도 | {pct(r['acc']['주 유형'])} | action_types 첫 번째 값 일치 |",
         f"| 유형 다중 라벨 F1 | {pct(r['lab'][2])} | micro P {pct(r['lab'][0])} / R {pct(r['lab'][1])} |",
         f"| 마감 정확도 (Task 단위) | {pct(t['due_ok'] / t['gold'] if t['gold'] else 0)} | 정답 Task {t['gold']}개 중 매칭되고 due_at이 분 단위까지 일치 |",
         f"| 우선순위 정확도 | {pct(r['acc']['우선순위'])} | P1/P2/P3 일치 |",
         "", "## 2. 필드별 정확도 (메일 단위)", "", "| 필드 | 정확도 |", "|---|---|"]
    L += [f"| {k} | {pct(v)} |" for k, v in r["acc"].items()]
    L += ["", "## 3. 이진 판정 (양성 = true)", "", "| 항목 | 정밀도 | 재현율 | F1 | 놓친 건수 |", "|---|---|---|---|---|"]
    L += [f"| {k} | {pct(p)} | {pct(rc)} | {pct(f)} | {fn} |" for k, (p, rc, f, fn) in r["bin"].items()]
    L += ["", "## 4. Task 추출", "",
          f"- 정답 {t['gold']}개 / 예측 {t['pred']}개 / 매칭 {t['paired']}개 (매칭: 메일 안에서 action 유사도 순 1:1)",
          f"- 매칭된 Task의 마감 일치 {t['due_ok']}/{t['paired']} · 형식 일치 {t['fmt_ok']}/{t['paired']}",
          f"- action 문장 평균 유사도 {r['sim']:.2f} (difflib, 0~1 · 참고용)",
          "", "## 5. 행동 유형별", "", "| 유형 | 정답 건수 | 정밀도 | 재현율 | F1 |", "|---|---|---|---|---|"]
    L += [f"| {k} | {n} | {pct(p)} | {pct(rc)} | {pct(f)} |" for k, (p, rc, f, n) in r["types"].items()]
    L += ["", "## 6. 우선순위 혼동 행렬 (행: 정답, 열: 예측)", "", "| 정답＼예측 | P1 | P2 | P3 | 없음/기타 |", "|---|---|---|---|---|"]
    for gp in ("P1", "P2", "P3"):
        other = sum(v for (a, b), v in r["conf"].items() if a == gp and b not in ("P1", "P2", "P3"))
        L.append(f"| {gp} | " + " | ".join(str(r["conf"][(gp, pp)]) for pp in ("P1", "P2", "P3")) + f" | {other} |")
    L += ["", "## 7. 엣지케이스 태그별 완전 정답", "", "| 태그 | 정답/건수 | 비율 |", "|---|---|---|"]
    L += [f"| {k} | {ok}/{n} | {pct(ok / n)} |" for k, (ok, n) in r["tags"].items()]
    L += ["", f"## 8. 오답 목록 ({len(r['rows'])}건)", "", "| ID | 제목 | 태그 | 틀린 필드 | 정답 → 예측 (주요) |", "|---|---|---|---|---|"]
    for mid, subj, tags, wrong, g, p, miss in r["rows"]:
        if miss:
            diff = "예측 없음"
        else:
            d = []
            if "주 유형" in wrong:
                d.append(f"유형 {g['action_types'][0]}→{(p.get('action_types') or ['-'])[0]}")
            if "Task 수" in wrong or "Task 여부" in wrong:
                d.append(f"Task {len(g['tasks'])}→{len(p.get('tasks') or [])}")
            if "마감" in wrong:
                d.append(f"마감 {[due(x['due_at']) for x in g['tasks']]}→{[due(x.get('due_at')) for x in (p.get('tasks') or []) if isinstance(x, dict)]}")
            if "우선순위" in wrong:
                d.append(f"{g['priority']}→{p.get('priority')}")
            diff = " · ".join(d)
        L.append(f"| {mid} | {subj.replace('|', '/')} | {tags} | {', '.join(wrong)} | {diff} |")
    return "\n".join(L) + "\n"


def load_gold(name="dummy_mails.json"):
    return json.loads((HERE / name).read_text(encoding="utf-8"))["mails"]


def selfcheck():
    mails = load_gold()
    perfect = [{"id": o["mail"]["id"], **o["gold"]} for o in mails]
    r = evaluate(mails, perfect)
    assert r["full"] == r["n"] and all(v == 1 for v in r["acc"].values()) and r["lab"][2] == 1, r["acc"]
    assert r["task"]["due_ok"] == r["task"]["gold"] == r["task"]["fmt_ok"]
    # Task 메일 하나의 tasks를 지우고, 하나는 예측 자체를 빼면: 둘 다 Task 재현율에서 빠져야 함
    tid = [o["mail"]["id"] for o in mails if o["gold"]["tasks"]][:2]
    broken = [dict(p, tasks=[]) if p["id"] == tid[0] else p for p in perfect if p["id"] != tid[1]]
    r = evaluate(mails, broken)
    assert r["missing"] == 1 and r["full"] == r["n"] - 2 and r["bin"]["Task 여부"][3] == 2, r["bin"]
    assert due("2026-10-21T18:00:00+09:00") == "2026-10-21T18:00" and fmt("pptx/drawio") == fmt(".DRAWIO, pptx")
    print("selfcheck OK")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    if sys.argv[1] == "--selfcheck":
        selfcheck()
        sys.exit()
    path = Path(sys.argv[1])
    preds = json.loads(path.read_text(encoding="utf-8"))
    gold = sys.argv[2] if len(sys.argv) == 3 else "dummy_mails.json"
    res = evaluate(load_gold(gold), preds)
    out = HERE / f"eval_report_{path.stem}.md"
    out.write_text(report(res, path, gold), encoding="utf-8")
    print(f"완전 정답 {res['full']}/{res['n']} · Task 재현율 {pct(res['bin']['Task 여부'][1])} · "
          f"주 유형 {pct(res['acc']['주 유형'])} · 우선순위 {pct(res['acc']['우선순위'])} -> {out.name}")
