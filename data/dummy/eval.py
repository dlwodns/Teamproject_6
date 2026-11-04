# -*- coding: utf-8 -*-
"""메타데이터 추출 평가
시스템 출력(predictions)을 dummy_mails.json의 gold와 비교해 지표를 계산하고 eval_report_<이름>.md를 만든다.

사용:  python eval.py predictions.json      # -> eval_report_predictions.md
       python eval.py predictions.json test_mails.json   # 테스트셋 정답으로 채점
       python eval.py predictions.json <레포 밖 폴더>/testA_mails.json   # 봉인 세트는 절대 경로로(DE-D15)
       python eval.py --selfcheck            # 채점 로직 자체 점검

predictions.json 형식: gold와 같은 필드에 메일 id를 붙인 리스트. 빠진 필드·빠진 메일은 오답 처리.
  [{"id": "M-0001", "sender": {...}, "action_types": [...], "mentioned_me": true,
    "tasks": [{"action": "...", "format": "xlsx", "due_at": "2026-10-21T18:00"}],
    "urgent": false, "is_follow_up": false, "priority": "P3"}, ...]
  checks(선택): 확인 칸 [{"text", "reason", "source"}]. Task 지표에는 넣지 않고 '확인 칸' 절에서만 센다(사용자 항목 2, 11/3).
보낸 메일(from == mailbox.owner, S-번호)은 채점하지 않는다. 응답 대기 재료라 분류 대상이 아니다(DE-D10 · DE-4).
보고서(DE-5): 0절 한눈 요약(개수로 나눠 적기, pr_review 3-1절) → 1~8절 코드 채점(정답이 하나인 칸) → 9 · 10절 참고값(확인 칸 임시 기준 · 판정).
  시험 · 봉인 세트(test · test3 · 레포 밖 정답)는 오답 메일 ID · 제목을 적지 않는다(plan 8.5절). 틀린 칸별 통수만 0절에 남는다.
"""
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).parent
FIELDS = ["주 유형", "Task 여부", "Task 수", "마감", "지목", "긴급", "재요청", "우선순위"]  # 메일 완전 정답 판정 기준
SEALED = {"test_mails.json", "test3_mails.json"}  # 레포 안 시험 · 봉인 세트. 레포 밖 정답(봉인 테스트 A · B)도 같이 숨긴다
TARGET_PRECISION = 0.95  # DE-D13: 놓침 0 · 할 일 메일 정밀도 95% 이상
PLAIN = {"Task 여부": "할 일 여부", "Task 수": "할 일 수"}  # 0절 요약에 쓰는 쉬운 이름(pr_review 3-1절)


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
    groups = {"있음": Counter(), "없음": Counter()}  # 정답 할 일 있음 · 없음 → 맞음(모든 칸) · 일부 칸 틀림 · 오답(할 일 여부부터 틀림)
    wrong_fields = Counter()
    # 확인 칸(임시 기준: gold에 확인 정답 칸이 없다). 기대: gold 할 일 없음 · 주 유형 회신 → 받음, 참조 · 기타 → 안 받음, 공지 → 대상자 당부만
    chk_n, chk_hit, chk_reason = Counter(), Counter(), Counter()
    chk_harm, chk_shown = [], []  # gold 할 일 메일인데 할 일이 비고 확인 칸에만 있다: 엑사원 할 일을 옮긴 것(재현율 피해) / 규칙이 이미 놓친 것
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

        pc = [c for c in (p.get("checks") or []) if isinstance(c, dict)]
        chk_reason.update(c.get("reason") for c in pc)
        if not gt:
            grp = gtypes[0] if gtypes[0] in ("회신", "공지") else "참조 · 기타"
            chk_n[grp] += 1
            chk_hit[grp] += bool(pc)
        elif pc and not pt:
            (chk_harm if any(c.get("source") == "exaone" for c in pc) else chk_shown).append(ml["id"])

        all_ok = all(ok[k] for k in FIELDS)
        grp = groups["있음" if gt else "없음"]
        grp["n"] += 1
        grp["ok" if all_ok else "part" if ok["Task 여부"] else "wrong"] += 1
        wrong_fields.update(k for k in FIELDS if not ok[k])
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
                rows=rows, groups=groups, wrong_fields=wrong_fields,
                checks=dict(mails=sum(1 for p in preds if p.get("checks")), reasons=dict(chk_reason),
                            no_task={k: (chk_hit[k], chk_n[k]) for k in ("회신", "공지", "참조 · 기타")},
                            harm=chk_harm, shown=chk_shown))


def pct(x):
    return f"{x * 100:.1f}%"


def is_sealed(gold) -> bool:
    """시험 · 봉인 세트인가: 레포 안 test · test3, 또는 레포 밖 정답 파일(봉인 테스트 A · B)."""
    path = Path(gold)
    return path.name in SEALED or (path.is_absolute() and not path.resolve().is_relative_to(HERE.resolve().parents[1]))


def summary(r):
    """0절 한눈 요약. 비율만 적지 않고 개수로 나눈다(pr_review 3-1절)."""
    y, n, t = r["groups"]["있음"], r["groups"]["없음"], r["task"]
    found, caught = y["n"] - y["wrong"], n["wrong"]
    prec = found / (found + caught) if found + caught else 0.0
    L = ["## 0. 한눈 요약 (코드 채점)", "",
         "할 일이 있는 메일을 놓치지 않았는지, 할 일이 없는 메일을 할 일로 잡지 않았는지를 개수로 본다.",
         "맞음 = 1절 기준 모든 칸 정답, 일부 칸 틀림 = 할 일 여부는 맞았지만 다른 칸이 틀림, 오답 = 할 일 여부부터 틀림.", "",
         "| 정답 | 메일(통) | 맞음 ↑ | 일부 칸 틀림 | 오답 ↓ | 오답의 뜻 |", "|---|---|---|---|---|---|",
         f"| 할 일 있음 | {y['n']} | {y['ok']} | {y['part']} | {y['wrong']} | 놓침 |",
         f"| 할 일 없음 | {n['n']} | {n['ok']} | {n['part']} | {n['wrong']} | 할 일로 잡음 |",
         f"| 합계 | {y['n'] + n['n']} | {y['ok'] + n['ok']} | {y['part'] + n['part']} | {y['wrong'] + n['wrong']} | |", "",
         f"- 놓친 할 일 메일 **{y['wrong']}통** · 할 일로 잡은 메일 **{caught}통** · 할 일 메일 정밀도 **{pct(prec)}** ({found}/{found + caught})",
         f"- 목표(DE-D13, 시험 세트 기준): 놓침 0통 → {'달성' if y['wrong'] == 0 else '**미달**'} · 정밀도 {TARGET_PRECISION:.0%} 이상 → {'달성' if prec >= TARGET_PRECISION else '**미달**'}", "",
         "| 할 일 단위 | 개 |", "|---|---|",
         f"| 정답 할 일 | {t['gold']} |",
         f"| 짝지어짐 · 마감 맞음 ↑ | {t['due_ok']} |",
         f"| 짝지어짐 · 마감 틀림 | {t['paired'] - t['due_ok']} |",
         f"| 놓친 할 일 (정답에만 있음) ↓ | {t['gold'] - t['paired']} |",
         f"| 더 만든 할 일 (예측에만 있음) ↓ | {t['pred'] - t['paired']} |", "",
         "짝짓기는 같은 메일 안에서 문장이 가장 비슷한 할 일끼리 1:1로 묶는다. 정답 할 일 = 마감 맞음 + 마감 틀림 + 놓친 할 일.", "",
         "| 틀린 칸 | 메일(통) |", "|---|---|"]
    L += [f"| {PLAIN.get(k, k)} | {r['wrong_fields'][k]} |" for k in FIELDS]
    return L


def report(r, pred_path, gold_name="dummy_mails.json", hide=None):
    """hide: 오답 메일 ID · 제목을 숨긴다. None이면 정답 이름으로 정한다(is_sealed)."""
    t = r["task"]
    hide = is_sealed(gold_name) if hide is None else hide
    L = [f"# 추출 평가 결과 · {pred_path.name}", "",
         f"- 평가 시각: {datetime.now():%Y-%m-%d %H:%M} · 정답: {Path(gold_name).name} ({r['n']}건)",
         f"- 예측 누락 메일: {r['missing']}건 (누락은 전 필드 오답 처리)",
         f"- **메일 완전 정답: {r['full']}/{r['n']} ({pct(r['full'] / r['n'])})** — 기준: {', '.join(FIELDS)} 모두 일치",
         "- 읽는 법: 0절 요약 → 1~8절 코드 채점(정답이 하나인 칸) → 9 · 10절 참고값(확인 칸 임시 기준 · 판정, 정답 아님)"
         + (" · 시험 · 봉인 세트라 오답 메일 ID · 제목은 적지 않는다" if hide else ""), "",
         *summary(r),
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
          "- 할 일 문장 내용이 맞는지는 코드로 채점하지 않는다 → 10절(판정)",
          "", "## 5. 행동 유형별", "", "| 유형 | 정답 건수 | 정밀도 | 재현율 | F1 |", "|---|---|---|---|---|"]
    L += [f"| {k} | {n} | {pct(p)} | {pct(rc)} | {pct(f)} |" for k, (p, rc, f, n) in r["types"].items()]
    L += ["", "## 6. 우선순위 혼동 행렬 (행: 정답, 열: 예측)", "", "| 정답＼예측 | P1 | P2 | P3 | 없음/기타 |", "|---|---|---|---|---|"]
    for gp in ("P1", "P2", "P3"):
        other = sum(v for (a, b), v in r["conf"].items() if a == gp and b not in ("P1", "P2", "P3"))
        L.append(f"| {gp} | " + " | ".join(str(r["conf"][(gp, pp)]) for pp in ("P1", "P2", "P3")) + f" | {other} |")
    L += ["", "## 7. 엣지케이스 태그별 완전 정답", "", "| 태그 | 정답/건수 | 비율 |", "|---|---|---|"]
    L += [f"| {k} | {ok}/{n} | {pct(ok / n)} |" for k, (ok, n) in r["tags"].items()]
    L += ["", f"## 8. 오답 목록 ({len(r['rows'])}건)", ""]
    if hide:
        L.append("시험 · 봉인 세트라 메일 ID · 제목 · 내용을 적지 않는다(plan 8.5절). 틀린 칸별 통수는 0절, 유형 · 태그별 정답률은 5 · 7절.")
    else:
        L += ["| ID | 제목 | 태그 | 틀린 필드 | 정답 → 예측 (주요) |", "|---|---|---|---|---|"]
    for mid, subj, tags, wrong, g, p, miss in [] if hide else r["rows"]:
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
    c = r.get("checks")
    if c:
        why = " · ".join(f"{k} {v}" for k, v in sorted(c["reasons"].items())) or "-"
        L += ["", "## 9. 확인 칸 (임시 기준)", "",
              "할 일은 아니지만 읽고 확인할 메일(사용자 항목 2). Task 지표에는 넣지 않는다. gold에 확인 정답 칸이 없어 기준은 임시다:",
              "회신(할 일 없음)은 받아야 하고, 참조 · 기타는 받지 않아야 한다. 공지는 대상자 당부('미이수자 · 해당자')만 받는다.", "",
              f"- 확인 항목이 붙은 메일: {c['mails']}통 ({why})",
              f"- **재현율 피해(gold 할 일 메일인데 엑사원 할 일이 확인 칸으로 옮겨져 할 일이 빈 메일): {len(c['harm'])}통** (0이어야 함){'' if hide else ''.join(' ' + i for i in c['harm'])}",
              f"- 참고: 규칙 · 모델이 이미 놓친 할 일 메일 중 확인 칸에라도 보인 메일 {len(c['shown'])}통{'' if hide else ''.join(' ' + i for i in c['shown'])}", "",
              "| gold 주 유형 (할 일 없음) | 메일 | 확인 항목 받음 | 기대 |", "|---|---|---|---|"]
        exp = {"회신": "모두 받음", "공지": "대상자 당부만", "참조 · 기타": "받지 않음"}
        L += [f"| {k} | {n} | {h} | {exp[k]} |" for k, (h, n) in c["no_task"].items()]
    L += ["", "## 10. 판정 (참고값 · 정답 아님)", "",
          "표현이 여러 가지라 코드로 정답을 정할 수 없는 항목이다. 점수는 참고값이고, 정답은 코드 채점과 사람 검수가 정한다(DE-D12 · plan 10절).", "",
          "| 항목 | 방식 | 값 |", "|---|---|---|",
          f"| 할 일 문장 비슷한 정도 | 글자 유사도(difflib, 0~1). 뜻이 같아도 표현이 다르면 낮다 | {r['sim']:.2f} (짝지어진 할 일 {t['paired']}개 평균) |",
          "| 할 일 문장 내용이 맞는지 | 독립 에이전트 판정(`eval/judges/`) | 기록 없음 |",
          "| 사람 검수 | 보고서를 사람이 확인 | 기록 없음 |",
          "| 요약 · 회신 초안 품질 | 판정(DE-6) | 기록 없음 |"]
    return "\n".join(L) + "\n"


def received(data):
    """받은 메일만. 보낸 메일(from == mailbox.owner)은 응답 대기 재료라 분류 · 채점에서 뺀다(DE-D10 · DE-4)."""
    owner = data["mailbox"]["owner"]
    return [o for o in data["mails"] if o["mail"]["from"] != owner]


def load_gold(name="dummy_mails.json"):
    """이름만 주면 data/dummy에서, 절대 경로면 그 파일(레포 밖 봉인 세트, DE-D15)을 읽는다."""
    path = Path(name)
    return received(json.loads((path if path.is_absolute() else HERE / path).read_text(encoding="utf-8")))


def selfcheck():
    mails = load_gold()
    perfect = [{"id": o["mail"]["id"], **o["gold"]} for o in mails]
    r = evaluate(mails, perfect)
    assert r["full"] == r["n"] and all(v == 1 for v in r["acc"].values()) and r["lab"][2] == 1, r["acc"]
    assert r["groups"]["있음"]["ok"] + r["groups"]["없음"]["ok"] == r["n"] and not r["wrong_fields"]
    assert r["task"]["due_ok"] == r["task"]["gold"] == r["task"]["fmt_ok"]
    # Task 메일 하나의 tasks를 지우고, 하나는 예측 자체를 빼면: 둘 다 Task 재현율에서 빠져야 함
    tid = [o["mail"]["id"] for o in mails if o["gold"]["tasks"]][:2]
    broken = [dict(p, tasks=[]) if p["id"] == tid[0] else p for p in perfect if p["id"] != tid[1]]
    r = evaluate(mails, broken)
    assert r["missing"] == 1 and r["full"] == r["n"] - 2 and r["bin"]["Task 여부"][3] == 2, r["bin"]
    # 0절 요약: 놓친 2통은 '할 일 있음'의 오답, 합계는 전체 메일 수. 시험 · 봉인 세트는 오답 ID를 숨긴다
    y, n = r["groups"]["있음"], r["groups"]["없음"]
    assert y["wrong"] == 2 and y["n"] + n["n"] == r["n"] == sum(y[k] + n[k] for k in ("ok", "part", "wrong"))
    assert tid[0] in report(r, Path("p.json"), hide=False) and tid[0] not in report(r, Path("p.json"), hide=True)
    outside = Path(HERE.resolve().anchor) / "sealed" / "testA_mails.json"
    assert is_sealed("test_mails.json") and is_sealed(outside) and not is_sealed("dummy_mails.json") and not is_sealed(HERE.resolve() / "dev3_mails.json")
    assert due("2026-10-21T18:00:00+09:00") == "2026-10-21T18:00" and fmt("pptx/drawio") == fmt(".DRAWIO, pptx")
    # 확인 칸: 할 일을 비우고 엑사원 출처 확인 항목만 남기면 재현율 피해로 센다. 확인 칸은 Task 지표를 바꾸지 않는다
    moved = [dict(p, tasks=[], checks=[{"text": "x", "reason": "읽고 확인", "source": "exaone"}]) if p["id"] == tid[0] else p
             for p in perfect]
    r = evaluate(mails, moved)
    assert r["checks"]["harm"] == [tid[0]] and r["checks"]["mails"] == 1 and r["bin"]["Task 여부"][3] == 1
    # 보낸 메일: 받은 메일 수는 그대로, 절대 경로로 읽어도 같다
    data = json.loads((HERE / "dummy_mails.json").read_text(encoding="utf-8"))
    sent = dict(data["mails"][0], mail=dict(data["mails"][0]["mail"], id="S-0001", **{"from": data["mailbox"]["owner"]}))
    assert received(dict(data, mails=data["mails"] + [sent])) == data["mails"] == load_gold((HERE / "dummy_mails.json").resolve())
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
    out = (path.parent if Path(gold).is_absolute() else HERE) / f"eval_report_{path.stem}.md"  # 레포 밖 정답이면 결과 옆에(DE-D15)
    out.write_text(report(res, path, gold), encoding="utf-8")
    print(f"완전 정답 {res['full']}/{res['n']} · Task 재현율 {pct(res['bin']['Task 여부'][1])} · "
          f"주 유형 {pct(res['acc']['주 유형'])} · 우선순위 {pct(res['acc']['우선순위'])} -> {out.name}")
