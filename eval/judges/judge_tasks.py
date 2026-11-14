"""할 일 문장 판정(DE-6) — 분류기가 뽑은 할 일이 정답 할 일과 같은 일인지 판정자 모델이 본다. 참고값이고 정답이 아니다(plan 10절).

코드 채점(data/dummy/eval.py)은 할 일 여부 · 수 · 마감 · 유형처럼 정답이 하나인 칸만 맞힌다. 할 일 문장은 표현이 여러 가지라
글자 유사도(difflib)로 짝만 짓고 내용은 채점하지 않았다 — '설명서 송부'와 '아키텍처 문서 보내기'는 같은 일인데 유사도가 낮다.
여기서는 짝지어진 할 일마다 판정자에게 메일 · 정답 할 일 · 예측 할 일을 주고 같음 · 일부 · 다름을 받는다.

사용(레포 루트, ai/.venv 파이썬 — 키는 .env의 OPENROUTER_API_KEY):
  python eval/judges/judge_tasks.py eval/reports/predictions_dev4_or-anthropic-claude-haiku-5.5.json --set dev4
  python eval/judges/judge_tasks.py <레포 밖 폴더>/predictions_testA_api-k-exaone_v2.5.json --file <레포 밖 폴더>/testA_mails.json
  --dry        판정 없이 짝 수 · 새로 부를 횟수만
  --model      판정자(기본 anthropic/claude-haiku-5.5, 오픈라우터 · eval 전용, D26 · DE-D24)
  --selfcheck  가짜 판정자로 짝짓기 · 집계 · 보고서 · 봉인 숨김 · 캐시를 점검(네트워크 없음)
결과: 예측 파일 옆에 judge_<예측 이름>.md(보고서) · judge_cache_<예측 이름>.json(판정 캐시 — 같은 짝은 다시 부르지 않는다).
  같은 예측의 eval_report가 있으면 10절 '할 일 문장 내용이 맞는지' 칸을 개수로 채운다.
봉인 세트(레포 밖 정답)는 개수만 적고 메일 ID · 문장을 적지 않는다(plan 8.5절). 보고서 · 캐시도 그 폴더에만 남는다.
"""
import argparse
import hashlib
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai"))
sys.path.insert(0, str(ROOT / "data/dummy"))
sys.path.insert(0, str(ROOT / "eval/runners"))

from eval import is_sealed, load_gold, pair_tasks  # noqa: E402  data/dummy/eval.py

PROMPT_VERSION = "judge_tasks_v1"
DEFAULT_MODEL = "anthropic/claude-haiku-5.5"
VERDICTS = ("같음", "일부", "다름")
SYSTEM = """너는 업무 메일 평가의 판정자다. 메일 한 통과, 그 메일에서 사람이 정한 정답 할 일 하나, 분류기가 뽑은 할 일 하나가 주어진다.
두 할 일이 같은 일인지 판정해 JSON 하나만 낸다.
- 같음: 해야 하는 일(무엇을 · 어떻게 · 누구에게)이 같다. 표현 · 어순 · 줄임 · 높임말 차이는 상관없다.
- 일부: 같은 요청을 가리키지만 핵심 하나가 빠지거나 다르다(두 가지 중 하나만 적음, 대상 · 산출물이 다름, 검토를 단순 회신으로 적음 등).
- 다름: 다른 일이거나 메일에 없는 일이다.
기한 · 파일 형식 · 유형은 다른 곳에서 따로 채점하니 판정에 넣지 않는다. reason은 한국어 한 줄(40자 안)."""
SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string", "enum": list(VERDICTS)}, "reason": {"type": "string"}},
          "required": ["verdict", "reason"]}
BANDS = ((0.7, "0.7 이상"), (0.4, "0.4~0.7"), (0.0, "0.4 미만"))  # difflib 유사도 구간 — 글자 유사도가 내용 판정과 어긋나는 곳을 본다
ROW = "| 할 일 문장 내용이 맞는지 | 독립 에이전트 판정(`eval/judges/`) |"  # eval_report 10절의 칸(data/dummy/eval.py)


def band(s: float) -> str:
    return next(name for lo, name in BANDS if s >= lo)


def body_text(body: str) -> str:
    """서명란(별표 줄 아래)은 판정에 필요 없어 뺀다. 입력 토큰을 줄인다."""
    return body.split("\n**********")[0].strip()


def pairs_of(gold: list[dict], preds: list[dict]) -> list[dict]:
    """정답 할 일과 예측 할 일의 짝(같은 메일 안, eval.py와 같은 difflib 1:1 짝짓기). 분류 실패 메일은 뺀다."""
    by_id = {p.get("id"): p for p in preds}
    out = []
    for o in gold:
        m, g = o["mail"], o["gold"]
        p = by_id.get(m["id"])
        if not p or p.get("_source") == "failed" or not g["tasks"] or not p.get("tasks"):
            continue
        for gt, pt, s in pair_tasks(g["tasks"], p["tasks"]):
            out.append({"id": m["id"], "subject": m["subject"], "body": body_text(m["body"]),
                        "gold": gt["action"], "pred": pt.get("action") or "", "sim": round(s, 3)})
    return out


def cache_key(model: str, x: dict) -> str:
    raw = "\0".join([PROMPT_VERSION, model, x["id"], x["gold"], x["pred"], x["body"]])
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def user_text(x: dict) -> str:
    return f"제목: {x['subject']}\n본문:\n{x['body']}\n\n정답 할 일: {x['gold']}\n분류기 할 일: {x['pred']}"


def judge(pairs: list[dict], client, model: str, cache: dict) -> tuple[list[dict], int, int]:
    """짝마다 판정. 캐시에 있으면 다시 부르지 않는다. (판정 붙인 짝, 새로 부른 수, 실패 수)"""
    from app.llm.client import LLMError
    called = failed = 0
    for x in pairs:
        k = cache_key(model, x)
        if k not in cache:
            called += 1
            try:
                out = client.chat_json(SYSTEM, user_text(x), SCHEMA)
            except LLMError as e:  # 실패는 캐시에 넣지 않는다 — 다음 실행에서 다시 부른다
                failed += 1
                x.update(verdict="판정 실패", reason=str(e)[:80])
                continue
            v = out.get("verdict")
            cache[k] = {"verdict": v if v in VERDICTS else "판정 실패", "reason": str(out.get("reason", ""))[:80]}
        x.update(cache[k])
    return pairs, called, failed


def summary_cell(c: Counter, n: int, model: str, report_name: str) -> str:
    fail = f" · 판정 실패 {c['판정 실패']}" if c["판정 실패"] else ""
    return f"같음 {c['같음']} · 일부 {c['일부']} · 다름 {c['다름']}{fail} (짝 {n}개, 판정 {model.split('/')[-1]}, `{report_name}`)"


def report(pairs: list[dict], pred_name: str, gold_name: str, model: str, hide: bool, cost: str) -> str:
    c = Counter(x["verdict"] for x in pairs)
    n = len(pairs)

    def pct(k):
        return f"{c[k] / n:.0%}" if n else "-"

    L = [f"# 할 일 문장 판정 (DE-6, 참고값) · {pred_name}", "",
         f"- 판정자 {model} · 프롬프트 {PROMPT_VERSION} · 정답 {gold_name} · 판정 비용 {cost}",
         "- 정답이 아니다. 코드 채점(eval_report 0~8절)과 사람 검수가 우선한다(plan 10절). 할 일 여부 · 수 · 마감 · 유형은 여기서 보지 않는다.",
         "- 짝: 정답 할 일과 예측 할 일이 모두 있는 메일에서 eval.py와 같은 글자 유사도 1:1 짝. 놓친 할 일 · 더 만든 할 일 · 분류 실패 메일은 짝이 없어 빠진다.",
         "", "## 1. 판정 개수", "", "| 판정 | 짝(개) | 비율 |", "|---|---|---|"]
    L += [f"| {k} | {c[k]} | {pct(k)} |" for k in (*VERDICTS, "판정 실패") if k in VERDICTS or c[k]]
    L += [f"| 합계 | {n} | |", "",
          "## 2. 글자 유사도와 판정 (difflib이 내용과 어긋나는 곳)", "",
          "| 글자 유사도 | 짝 | 같음 | 일부 | 다름 |", "|---|---|---|---|---|"]
    for _, name in BANDS:
        b = Counter(x["verdict"] for x in pairs if band(x["sim"]) == name)
        L.append(f"| {name} | {sum(b.values())} | {b['같음']} | {b['일부']} | {b['다름']} |")
    L += ["", "- 유사도가 낮은데 '같음'이면 글자 유사도가 같은 일을 놓친 것, 높은데 '일부 · 다름'이면 글자만 비슷한 것이다.",
          "", "## 3. 일부 · 다름 목록", ""]
    if hide:
        L += ["- 봉인 세트라 메일 ID · 문장을 적지 않는다(plan 8.5절)."]
    else:
        rows = [x for x in pairs if x["verdict"] != "같음"]
        L += ["| 메일 | 판정 | 정답 할 일 | 예측 할 일 | 유사도 | 이유 |", "|---|---|---|---|---|---|"]
        L += [f"| {x['id']} | {x['verdict']} | {x['gold']} | {x['pred']} | {x['sim']:.2f} | {x.get('reason', '')} |" for x in rows] or ["| 없음 | | | | | |"]
    return "\n".join(L) + "\n"


def fill_eval_report(pred: Path, cell: str) -> bool:
    """같은 예측의 eval_report 10절 칸을 판정 개수로 채운다. 칸이 없으면 그대로 둔다."""
    rep = pred.with_name(f"eval_report_{pred.stem}.md")
    if not rep.is_file():
        return False
    lines = rep.read_text(encoding="utf-8").split("\n")
    hit = [i for i, line in enumerate(lines) if line.startswith(ROW)]
    if not hit:
        return False
    lines[hit[0]] = f"{ROW} {cell} |"
    rep.write_text("\n".join(lines), encoding="utf-8")
    return True


def run(pred: Path, gold_path, model: str, client=None, dry: bool = False) -> dict:
    gold = load_gold(str(gold_path))
    hide = is_sealed(gold_path)
    if hide and pred.resolve().is_relative_to(ROOT):
        sys.exit("봉인 세트의 예측 · 판정은 레포 밖 세트 폴더에만 둔다(DE-D15). 예측 파일을 그 폴더에서 준다")
    pairs = pairs_of(gold, json.loads(pred.read_text(encoding="utf-8")))
    cache_file = pred.with_name(f"judge_cache_{pred.stem}.json")
    cache = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.is_file() else {}
    todo = sum(cache_key(model, x) not in cache for x in pairs)
    if dry:
        return {"pairs": len(pairs), "to_call": todo}
    if client is None and todo:
        from openrouter_client import OpenRouterClient, load_key  # 평가 전용(DE-D24). 키는 .env
        client = OpenRouterClient(model, load_key())
    pairs, called, failed = judge(pairs, client, model, cache)
    cache_file.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    cost = client.cost_text() if client is not None and hasattr(client, "cost_text") else "새 호출 없음(캐시)"
    rep_name = f"judge_{pred.stem}.md"
    pred.with_name(rep_name).write_text(report(pairs, pred.name, Path(str(gold_path)).name, model, hide, cost), encoding="utf-8")
    c = Counter(x["verdict"] for x in pairs)
    filled = fill_eval_report(pred, summary_cell(c, len(pairs), model, rep_name))
    return {"pairs": len(pairs), "called": called, "failed": failed, "counts": dict(c), "report": rep_name, "filled": filled}


class FakeJudge:
    """selfcheck용: 글자가 같으면 같음, 같은 낱말이 하나라도 있으면 일부, 아니면 다름."""
    model = "fake"

    def __init__(self):
        self.calls = 0

    def chat_json(self, system, user, schema):
        self.calls += 1
        g = user.split("정답 할 일: ")[1].split("\n")[0]
        p = user.split("분류기 할 일: ")[1].strip()
        v = "같음" if g == p else "일부" if set(g.split()) & set(p.split()) else "다름"
        return {"verdict": v, "reason": "가짜"}


def selfcheck():
    gold = {"meta": {}, "mailbox": {"owner": "me@x.example"}, "people": {}, "mails": [
        {"mail": {"id": "M-0001", "from": "a@x.example", "subject": "자료 요청", "body": "보고서 보내 주세요.\n**********\n서명"},
         "gold": {"tasks": [{"action": "보고서 송부"}], "action_types": ["자료제출요청"]}},
        {"mail": {"id": "M-0002", "from": "b@x.example", "subject": "검토", "body": "설계서 검토 부탁드립니다."},
         "gold": {"tasks": [{"action": "설계서 검토 후 의견 회신"}], "action_types": ["검토승인요청"]}},
        {"mail": {"id": "M-0003", "from": "c@x.example", "subject": "공지", "body": "점검 안내"},
         "gold": {"tasks": [], "action_types": ["공지"]}},
        {"mail": {"id": "M-0004", "from": "d@x.example", "subject": "회의", "body": "회의 참석 부탁"},
         "gold": {"tasks": [{"action": "주간 회의 참석"}], "action_types": ["일정참석"]}},
        {"mail": {"id": "S-0001", "from": "me@x.example", "subject": "보낸", "body": "내가 보냄"}, "gold": {"tasks": [], "action_types": ["회신"]}}]}
    preds = [{"id": "M-0001", "tasks": [{"action": "보고서 송부"}]},
             {"id": "M-0002", "tasks": [{"action": "설계서 회신"}]},
             {"id": "M-0003", "tasks": []},
             {"id": "M-0004", "tasks": [{"action": "출장비 정산"}], "_source": "failed"}]
    with tempfile.TemporaryDirectory() as d:
        dp = Path(d)
        gp, pp = dp / "x_mails.json", dp / "predictions_x_fake.json"
        gp.write_text(json.dumps(gold, ensure_ascii=False), encoding="utf-8")
        pp.write_text(json.dumps(preds, ensure_ascii=False), encoding="utf-8")
        (dp / "eval_report_predictions_x_fake.md").write_text(f"## 10\n{ROW} 기록 없음 |\n", encoding="utf-8")
        fj = FakeJudge()
        r = run(pp, gp, "fake", client=fj)
        assert r["pairs"] == 2 and r["counts"] == {"같음": 1, "일부": 1}, r  # 분류 실패 · 할 일 없는 메일 · 보낸 메일은 빠진다
        md = (dp / r["report"]).read_text(encoding="utf-8")
        assert "봉인 세트라" in md and "설계서" not in md, "레포 밖 정답 = 봉인 세트: 문장을 적지 않는다"
        assert "같음 1 · 일부 1 · 다름 0" in (dp / "eval_report_predictions_x_fake.md").read_text(encoding="utf-8")
        r2 = run(pp, gp, "fake", client=fj)
        assert r2["called"] == 0 and fj.calls == 2, "같은 짝은 캐시에서 — 다시 부르지 않는다"
        assert run(pp, gp, "other-model", dry=True)["to_call"] == 2, "판정자가 바뀌면 다시 판정한다"
        assert band(0.75) == "0.7 이상" and band(0.5) == "0.4~0.7" and band(0.1) == "0.4 미만"
    print("selfcheck OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pred", type=Path, nargs="?", help="run_dummy가 만든 predictions_*.json")
    ap.add_argument("--set", default=None, help="개발 세트 이름(run_dummy와 같음: dev4 · dev7 · core …)")
    ap.add_argument("--file", type=Path, default=None, help="레포 밖 봉인 세트 정답 파일(testA_mails.json 등)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        return selfcheck()
    if not a.pred or not (a.set or a.file):
        ap.error("예측 파일과 --set 또는 --file이 필요하다")
    if a.file:
        gold_path = a.file.expanduser().resolve()
    else:
        from run_dummy import SETS  # 세트 이름 → 파일(run_dummy와 같은 표)
        gold_path = SETS[a.set]
    r = run(a.pred.expanduser().resolve(), gold_path, a.model, dry=a.dry)
    print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
