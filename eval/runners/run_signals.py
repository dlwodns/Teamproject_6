"""리마인더 신호 개발 세트(eval/datasets/signals_dev_v1.jsonl)로 `/signals` 파이프라인을 채점한다 (AI-24 · AI-D20).

사용 (레포 루트에서):
  ai/.venv/bin/python eval/runners/run_signals.py                 # 자체 점검: 정답을 그대로 돌려주는 가짜 모델 → 모두 '맞음'이어야 한다
  ai/.venv/bin/python eval/runners/run_signals.py --llm           # 실제 모델(LLM_BACKEND 설정, 기본 엑사원 API). 메일 1통에 1회 호출
  ai/.venv/bin/python eval/runners/run_signals.py --replay <출력.json>   # 남긴 모델 출력으로 다시 채점(모델을 부르지 않음)

자체 점검은 정답 라벨이 코드 규칙(근거 문장 · 날짜 계산 · task_id)을 통과하는지와 채점기를 함께 확인한다.
--llm은 하루 호출 한도(엑사원 API 100회)를 39회 쓴다. 한도 소진(quota)이 나오면 멈추고 그때까지 낸 출력을 남긴다.

채점(신호 종류마다):
- 약속: 같은 who이고 근거 문장이 겹치면 같은 신호. 기한 날짜(due_at)까지 같으면 '맞음', 다르면 '일부 틀림'
- 기한 변경: 같은 task_id면 같은 신호. 새 기한 날짜가 같으면 '맞음', 다르면 '일부 틀림'
- 해결: 같은 task_id면 같은 신호. 이유(reason)가 같으면 '맞음', 다르면 '일부 틀림'
- 질문: 정답이 true인 메일만 정답으로 센다. 정답이 false인데 true면 '오답'
- 정답에 없는데 낸 신호는 '오답', 정답인데 못 낸 신호는 '놓침'
정밀도 = (맞음 + 일부 틀림) / 낸 신호, 재현율 = (맞음 + 일부 틀림) / 정답. 일부 틀림은 신호는 찾았지만 칸 하나가 틀린 것이다.
"""
import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai"))

from app.core.config import get_settings  # noqa: E402
from app.llm.client import LLMError, build_client  # noqa: E402
from app.pipeline.signals import extract  # noqa: E402
from app.prompts.signals_v1 import VERSION  # noqa: E402
from app.schemas.signals import SignalsRequest  # noqa: E402

DATASET = ROOT / "eval/datasets/signals_dev_v1.jsonl"
KINDS = [("commitments", "약속"), ("due_changes", "기한 변경"), ("resolved", "해결"), ("asks", "나에게 온 질문")]


def _ws(s: str | None) -> str:
    return re.sub(r"\s+", "", s or "")


class Recorder:
    """모델 호출을 감싸 원출력을 남긴다(다시 채점용)."""

    def __init__(self, inner):
        self.inner, self.model, self.last = inner, inner.model, None

    def chat_json(self, system, user, schema):
        self.last = None
        out = self.inner.chat_json(system, user, schema)
        self.last = out
        return out


class Replay:
    """정해 둔 원출력을 돌려준다. 없으면(호출 실패였던 메일) 그때의 실패를 다시 낸다."""

    def __init__(self, model: str, out):
        self.model, self.out = model, out

    def chat_json(self, system, user, schema):
        if isinstance(self.out, dict) and "__error__" in self.out:
            raise LLMError(self.out["__error__"])
        return self.out


def gold_as_model(exp: dict) -> dict:
    """자체 점검용: 정답을 모델 출력 형식으로."""
    return {"commitments": [{k: c[k] or "" for k in ("who", "text", "due_raw", "evidence")} for c in exp["commitments"]],
            "due_changes": [{k: d[k] for k in ("task_id", "new_due_raw", "evidence")} for d in exp["due_changes"]],
            "resolved": [{k: r[k] for k in ("task_id", "reason", "evidence")} for r in exp["resolved"]],
            "asks_me_question": exp["asks_me_question"]}


def _overlap(a: str, b: str) -> bool:
    la, lb = [_ws(x) for x in a.split("\n") if x.strip()], [_ws(x) for x in b.split("\n") if x.strip()]
    return any(x in y or y in x for x in la for y in lb)


def score_mail(exp: dict, got: dict) -> dict:
    """신호 종류마다 {ok, partial, wrong, miss, n, notes}."""
    res = {}
    # 약속
    s = {"ok": 0, "partial": 0, "wrong": 0, "miss": 0, "n": len(exp["commitments"]), "notes": []}
    pred = list(got["commitments"])
    for g in exp["commitments"]:
        m = next((p for p in pred if p["who"] == g["who"] and _overlap(p["evidence"], g["evidence"])), None)
        if m is None:
            s["miss"] += 1
            s["notes"].append(f"놓침 약속 '{g['text']}'")
            continue
        pred.remove(m)
        if m["due_at"] == g["due_at"]:
            s["ok"] += 1
        else:
            s["partial"] += 1
            s["notes"].append(f"일부 틀림 약속 '{g['text']}' 기한 {g['due_at']} → {m['due_at']}(문구 {m['due_raw']!r})")
    s["wrong"] = len(pred)
    s["notes"] += [f"오답 약속 '{p['text']}' ({p['who']}, 기한 {p['due_raw']!r})" for p in pred]
    res["commitments"] = s
    # 기한 변경 · 해결
    for key, field in (("due_changes", "new_due_at"), ("resolved", "reason")):
        s = {"ok": 0, "partial": 0, "wrong": 0, "miss": 0, "n": len(exp[key]), "notes": []}
        pred = {p["task_id"]: p for p in got[key]}
        for g in exp[key]:
            p = pred.pop(g["task_id"], None)
            if p is None:
                s["miss"] += 1
                s["notes"].append(f"놓침 {key} {g['task_id']}")
            elif p[field] == g[field]:
                s["ok"] += 1
            else:
                s["partial"] += 1
                s["notes"].append(f"일부 틀림 {key} {g['task_id']} {field} {g[field]} → {p[field]}")
        s["wrong"] = len(pred)
        s["notes"] += [f"오답 {key} {tid}" for tid in pred]
        res[key] = s
    # 질문
    g, p = exp["asks_me_question"], got["asks_me_question"]
    res["asks"] = {"ok": int(g and p), "partial": 0, "wrong": int(p and not g), "miss": int(g and not p), "n": int(g),
                   "notes": (["놓침 질문"] if g and not p else []) + (["오답 질문"] if p and not g else [])}
    return res


def pct(a: int, b: int) -> str:
    return f"{a / b * 100:.1f}%" if b else "—"


def report(rows: list[dict], results: list[dict], mode: str, model: str, elapsed: list[float]) -> str:
    tot = {k: {"ok": 0, "partial": 0, "wrong": 0, "miss": 0, "n": 0} for k, _ in KINDS}
    for r in results:
        if r["score"] is None:
            continue
        for k, _ in KINDS:
            for f in tot[k]:
                tot[k][f] += r["score"][k][f]
    scored = [r for r in results if r["score"] is not None]
    perfect = sum(all(not r["score"][k]["notes"] for k, _ in KINDS) for r in scored)
    neg = [r for r, row in zip(results, rows) if not any(row["expected"][k] for k in ("commitments", "due_changes", "resolved"))
           and not row["expected"]["asks_me_question"]]
    neg_clean = sum(r["score"] is not None and all(not r["score"][k]["notes"] for k, _ in KINDS) for r in neg)
    fb = {}
    for r in results:
        if r["out"]["fallback"]:
            fb[r["out"]["fallback"]] = fb.get(r["out"]["fallback"], 0) + 1
    md = [f"# 리마인더 신호 채점 — {mode}", "",
          f"- 날짜 {date.today()} · 세트 `signals_dev_v1`({len(rows)}통, 개발 세트) · 프롬프트 `{VERSION}` · 모델 `{model}`",
          f"- 채점한 메일 {len(scored)}통 · 모델이 판단하지 못한 메일 {len(rows) - len(scored)}통"
          + (f" ({' · '.join(f'{k} {v}' for k, v in fb.items())})" if fb else ""),
          f"- 모든 신호가 맞은 메일 {perfect}/{len(scored)} · 신호가 없어야 하는 메일 {len(neg)}통 중 아무것도 내지 않은 메일 {neg_clean}통",
          f"- 코드가 버린 모델 신호(근거 없음 · 없는 task_id · 방향과 다른 who 등) {sum(r['out']['dropped'] for r in results)}개",
          ]
    if elapsed:
        md.append(f"- 호출 1회 평균 {sum(elapsed) / len(elapsed):.1f}초 (최소 {min(elapsed):.1f} · 최대 {max(elapsed):.1f})")
    md += ["", "| 신호 | 정답 | 맞음 | 일부 틀림 | 오답 | 놓침 | 정밀도 | 재현율 |", "|---|---|---|---|---|---|---|---|"]
    all_ = {"ok": 0, "partial": 0, "wrong": 0, "miss": 0, "n": 0}
    for k, name in KINDS:
        t = tot[k]
        for f in all_:
            all_[f] += t[f]
        found = t["ok"] + t["partial"]
        md.append(f"| {name} | {t['n']} | {t['ok']} | {t['partial']} | {t['wrong']} | {t['miss']} | "
                  f"{pct(found, found + t['wrong'])} | {pct(found, t['n'])} |")
    found = all_["ok"] + all_["partial"]
    md.append(f"| **합계** | {all_['n']} | {all_['ok']} | {all_['partial']} | {all_['wrong']} | {all_['miss']} | "
              f"{pct(found, found + all_['wrong'])} | {pct(found, all_['n'])} |")
    md += ["", "## 메일별 틀린 곳", ""]
    n_before = len(md)
    for r, row in zip(results, rows):
        if r["score"] is None:
            md.append(f"- {row['id']} ({row['kind']}): 판단 못 함 — {r['out']['fallback']} {r['out'].get('detail') or ''}")
            continue
        notes = [n for k, _ in KINDS for n in r["score"][k]["notes"]]
        if notes:
            md.append(f"- {row['id']} ({row['kind']}): " + " · ".join(notes))
    if len(md) == n_before:
        md.append("없음")
    return "\n".join(md) + "\n"


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--llm", action="store_true", help="실제 모델로 잰다(LLM_BACKEND · EXAONE_API_KEY 환경 변수)")
    g.add_argument("--replay", type=Path, help="남긴 모델 출력(json)으로 다시 채점")
    ap.add_argument("--dataset", type=Path, default=DATASET)
    ap.add_argument("--out", type=Path, default=None, help="보고서 경로(기본 eval/reports/signals_dev_v1_<모드>.md)")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    rows = [json.loads(ln) for ln in a.dataset.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if a.limit:
        rows = rows[: a.limit]
    mode = "llm" if a.llm else "replay" if a.replay else "selfcheck"
    out_md = a.out or ROOT / f"eval/reports/{a.dataset.stem}_{mode}.md"
    raw_path = out_md.with_suffix(".outputs.json")
    saved = json.loads(a.replay.read_text(encoding="utf-8")) if a.replay else {}
    rec = Recorder(build_client(get_settings())) if a.llm else None
    model = rec.model if rec else saved.get("__model__", "정답 그대로(가짜 모델)")

    results, raws, elapsed = [], {"__model__": model}, []
    for row in rows:
        req = SignalsRequest.model_validate(row["request"])
        if a.llm:
            t = time.perf_counter()
            out = extract(req, rec).model_dump(mode="json")
            if out["fallback"] in (None, "bad_output"):
                elapsed.append(time.perf_counter() - t)
            raws[row["id"]] = rec.last if rec.last is not None else {"__error__": f"{out['fallback']}: {out.get('detail')}"}
            print(f"{row['id']} {out['fallback'] or 'ok'} {time.perf_counter() - t:.1f}s", flush=True)
            if out["fallback"] == "quota":
                results.append({"out": out, "score": None})
                print("하루 호출 한도 소진 — 여기서 멈춘다", file=sys.stderr)
                rows = rows[: len(results)]
                break
        else:
            fake = Replay(model, saved.get(row["id"], {"__error__": "출력 없음"}) if a.replay else gold_as_model(row["expected"]))
            out = extract(req, fake).model_dump(mode="json")
        results.append({"out": out, "score": score_mail(row["expected"], out) if out["source"] == "exaone" else None})

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(report(rows, results, mode, model, elapsed), encoding="utf-8")
    if a.llm:
        raw_path.write_text(json.dumps(raws, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"모델 출력: {raw_path}")
        print(f"하루 한도: {getattr(rec.inner, 'day_limit', None)}")
    print(f"보고서: {out_md}")
    print("\n".join(out_md.read_text(encoding="utf-8").splitlines()[:16]))
    if mode == "selfcheck":
        bad = [r for r in results if r["score"] is None or any(r["score"][k]["notes"] for k, _ in KINDS)
               or r["out"]["dropped"]]
        print("selfcheck OK" if not bad else f"selfcheck 실패 {len(bad)}통")
        sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
