"""더미 메일 v1을 ai 분류 파이프라인에 넣어 predictions.json을 만든다 (DE-4 · AI-18 공용).

사용 (레포 루트에서, ai/.venv 파이썬으로):
  ai/.venv/bin/python eval/runners/run_dummy.py                 # 규칙만 (엑사원 없이)
  ai/.venv/bin/python eval/runners/run_dummy.py --llm           # 확신도 낮은 메일은 엑사원 (ollama 필요)
결과: eval/reports/predictions_<rule|llm>.json + 채점 보고서 eval_report_predictions_<rule|llm>.md (data/dummy/eval.py 채점기)

eval → ai 방향으로만 부른다(ai/README 규칙). 개인정보 가리기는 하지 않는다(더미는 가상 인물).
"""
import argparse
import json
import re
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai"))
sys.path.insert(0, str(ROOT / "data/dummy"))

from app.core.config import get_settings  # noqa: E402
from app.llm.client import build_client  # noqa: E402
from app.pipeline.classify import classify  # noqa: E402
from app.pipeline.rules.mail_rules_v1 import RULES_VERSION  # noqa: E402
from app.prompts.classify_v1 import PROMPT_VERSION  # noqa: E402
from eval import evaluate, load_gold, pct, report  # noqa: E402  data/dummy/eval.py
from app.schemas.classify import ClassifyRequest, OwnerProfile, SenderFlags  # noqa: E402


def signature_sender(body: str) -> dict:
    """서명란 첫 줄 '박지영 팀장 / Jiyoung Park'과 조직 줄 마지막 칸에서 발신자를 읽는다(채점용)."""
    sig = re.split(r"\n\*{5,}\n", body)
    lines = sig[1].split("\n") if len(sig) > 1 else []
    m = re.match(r"(\S+)\s+(\S+)\s*/", lines[0]) if lines else None
    team = lines[1].split("/")[-1].strip() if len(lines) > 1 and "/" in lines[1] else None
    return {"name": m[1] if m else None, "position": m[2] if m else None, "team": team}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="엑사원 사용 (기본: 규칙만)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    settings = replace(get_settings(), llm_enabled=a.llm)
    llm = build_client(settings)
    data = json.loads((ROOT / "data/dummy/dummy_mails.json").read_text(encoding="utf-8"))
    box, me = data["mailbox"], data["people"]["me"]
    owner = OwnerProfile(email=box["owner"], name=me["name"], position=me["position"], team=me["team"], member_of=box["member_of"])

    preds, routed, t0 = [], 0, time.perf_counter()
    for o in data["mails"]:
        m = o["mail"]
        req = ClassifyRequest(**{"from": m["from"]}, mail_id=m["id"], to=m["to"], cc=m["cc"], subject=m["subject"],
                              body=m["body"], attachments=m["attachments"], received_at=m["received_at"], owner=owner,
                              sender=SenderFlags(is_superior=m["from"] in box["superiors"], is_favorite=m["from"] in box["favorites"]))
        r = classify(req, llm, settings)
        routed += r.confidence < settings.router_threshold
        preds.append({
            "id": m["id"], "sender": signature_sender(m["body"]), "action_types": r.action_types,
            "mentioned_me": r.mentioned_me, "urgent": r.urgent, "is_follow_up": r.is_follow_up, "priority": r.priority,
            "tasks": [{"action": t.text, "format": t.format, "due_raw": t.due_raw,
                       "due_at": t.due_at.strftime("%Y-%m-%dT%H:%M") if t.due_at else None} for t in r.tasks],
            "_source": r.source, "_confidence": r.confidence, "_fallback": r.fallback,
        })

    out = Path(a.out) if a.out else ROOT / "eval/reports" / f"predictions_{'llm' if a.llm else 'rule'}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(preds, ensure_ascii=False, indent=1), encoding="utf-8")
    elapsed = time.perf_counter() - t0

    res = evaluate(load_gold(), preds)
    head = (f"- 버전: 규칙 {RULES_VERSION} · 프롬프트 {PROMPT_VERSION if a.llm else '미사용'} · "
            f"모델 {settings.model if a.llm else '미사용(규칙만)'} · 라우터 기준 {settings.router_threshold}\n"
            f"- 라우터가 엑사원으로 보낸(보낼) 메일 {routed}건 · 실행 {elapsed:.1f}초\n")
    md = report(res, out).replace("\n\n", "\n\n" + head, 1)
    rep = out.with_name(f"eval_report_{out.stem}.md")
    rep.write_text(md, encoding="utf-8")
    print(f"{len(preds)}건 · 엑사원 대상 {routed}건 · 완전 정답 {res['full']}/{res['n']} · "
          f"Task 재현율 {pct(res['bin']['Task 여부'][1])} · 놓친 Task 메일 {res['bin']['Task 여부'][3]}건 → {rep.relative_to(ROOT)}")

if __name__ == "__main__":
    main()
