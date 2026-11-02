"""더미 메일 v1을 ai 분류 파이프라인에 넣어 predictions.json을 만든다 (DE-4 · AI-18 공용).

사용 (레포 루트에서, ai/.venv 파이썬으로):
  ai/.venv/bin/python eval/runners/run_dummy.py                 # 규칙만 (엑사원 없이)
  ai/.venv/bin/python eval/runners/run_dummy.py --llm           # 확신도 낮은 메일은 엑사원 (ollama 필요)
  ai/.venv/bin/python eval/runners/run_dummy.py --set test      # 테스트셋 test-v1 (규칙 수정에 쓰지 않는 세트, eval/datasets/README.md)
결과: eval/reports/predictions_<rule|llm>.json(테스트셋은 predictions_test_<rule|llm>.json)
      + 채점 보고서 eval_report_<같은 이름>.md (data/dummy/eval.py 채점기)
실행기는 LLM_BACKEND(ollama 기본 | llamacpp)로 고른다. 예: LLM_BACKEND=llamacpp ... --llm
--llm은 엑사원 호출마다 응답 시간 · JSON 형식 오류를 재서 보고서에 붙인다. 첫 호출은 모델 로딩이라 평균에서 뺀다.

eval → ai 방향으로만 부른다(ai/README 규칙). 개인정보 가리기는 하지 않는다(더미는 가상 인물).
"""
import argparse
import json
import re
import sys
import time
from dataclasses import replace
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai"))
sys.path.insert(0, str(ROOT / "data/dummy"))

from app.core.config import get_settings  # noqa: E402
from app.llm.client import LLMError, build_client  # noqa: E402
from app.pipeline.classify import classify  # noqa: E402
from app.pipeline.rules.mail_rules_v1 import RULES_VERSION  # noqa: E402
from app.prompts.classify_v2 import PROMPT_VERSION  # noqa: E402
from eval import evaluate, load_gold, pct, report  # noqa: E402  data/dummy/eval.py
from app.schemas.classify import ClassifyRequest, OwnerProfile, SenderFlags  # noqa: E402


def signature_sender(body: str) -> dict:
    """서명란 첫 줄 '박지영 팀장 / Jiyoung Park'과 조직 줄 마지막 칸에서 발신자를 읽는다(채점용)."""
    sig = re.split(r"\n\*{5,}\n", body)
    lines = sig[1].split("\n") if len(sig) > 1 else []
    m = re.match(r"(\S+)\s+(\S+)\s*/", lines[0]) if lines else None
    team = lines[1].split("/")[-1].strip() if len(lines) > 1 and "/" in lines[1] else None
    return {"name": m[1] if m else None, "position": m[2] if m else None, "team": team}


SETS = {"dev": "dummy_mails.json", "test": "test_mails.json"}


class TimedClient:
    """엑사원 호출마다 걸린 시간과 실패 사유를 남긴다. 실패는 그대로 올려 파이프라인이 규칙 결과로 대신하게 한다."""

    def __init__(self, inner):
        self.inner, self.model, self.calls = inner, inner.model, []

    def chat_json(self, system, user, schema):
        t = time.perf_counter()
        try:
            out = self.inner.chat_json(system, user, schema)
            self.calls.append((time.perf_counter() - t, None))
            return out
        except LLMError as e:
            self.calls.append((time.perf_counter() - t, str(e)))
            raise


def runtime_version(settings, health) -> str:
    """보고서 머리에 적을 실행기 이름 · 버전. llama.cpp는 /props의 build_info, ollama는 health의 버전 · 모델 digest."""
    if settings.llm_backend != "llamacpp":  # Unix 소켓(OLLAMA_UDS)으로 붙어도 읽히도록 클라이언트가 잰 값을 쓴다
        return f"ollama {health.get('version') or '?'} · digest {(health.get('digest') or '?')[:12]}"
    try:
        return f"llama.cpp {httpx.get(f'{settings.llamacpp_base_url}/props', timeout=5).json().get('build_info', '?')}"
    except (httpx.HTTPError, ValueError):
        return f"{settings.llm_backend} 버전 확인 실패"


def llm_section(calls) -> str:
    ok = [s for s, e in calls if e is None]
    timed = ok[1:] if len(ok) > 1 else ok  # 첫 호출은 모델 로딩 시간이 섞인다
    call_err = [e for _, e in calls if e and "호출 실패" in e]
    fmt_err = [e for _, e in calls if e and "호출 실패" not in e]
    L = ["", "## 엑사원 호출", "", "| 항목 | 값 |", "|---|---|",
         f"| 호출 수 | {len(calls)} |",
         f"| 메일 1통 평균 응답 시간 (첫 호출 제외) | {sum(timed) / len(timed):.1f}초 |" if timed else "| 메일 1통 평균 응답 시간 | - |",
         f"| 최소 / 최대 | {min(timed):.1f}초 / {max(timed):.1f}초 |" if timed else "| 최소 / 최대 | - |",
         f"| 첫 호출 (로딩 포함) | {ok[0]:.1f}초 |" if ok else "| 첫 호출 | - |",
         f"| JSON 형식 오류 | {len(fmt_err)}건 |",
         f"| 호출 실패 (연결 · 시간 초과) | {len(call_err)}건 |"]
    L += [f"- {e}" for e in sorted(set(fmt_err + call_err))]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="엑사원 사용 (기본: 규칙만)")
    ap.add_argument("--set", choices=SETS, default="dev", help="dev: 더미 v1 100건(개발 세트) · test: test-v1(테스트셋)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    settings = replace(get_settings(), llm_enabled=a.llm)
    llm = build_client(settings)
    if a.llm:
        h = llm.health()
        if not h.get("model_ready"):  # 연결이 안 되면 전부 규칙 결과로 대신해 '엑사원 점수'처럼 보이게 된다
            url = settings.llamacpp_base_url if settings.llm_backend == "llamacpp" else (settings.ollama_uds or settings.ollama_base_url)
            sys.exit(f"엑사원 준비 안 됨({settings.llm_backend} {url} · {settings.model}): {h}")
        llm = TimedClient(llm)
    data = json.loads((ROOT / "data/dummy" / SETS[a.set]).read_text(encoding="utf-8"))
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

    name = f"predictions_{'test_' if a.set == 'test' else ''}{'llm' if a.llm else 'rule'}.json"
    out = Path(a.out) if a.out else ROOT / "eval/reports" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(preds, ensure_ascii=False, indent=1), encoding="utf-8")
    elapsed = time.perf_counter() - t0

    res = evaluate(load_gold(SETS[a.set]), preds)
    head = (f"- 버전: 규칙 {RULES_VERSION} · 프롬프트 {PROMPT_VERSION if a.llm else '미사용'} · "
            f"모델 {settings.model if a.llm else '미사용(규칙만)'} · "
            f"실행기 {runtime_version(settings, h) if a.llm else '미사용'} · "
            f"데이터 {data['meta']['version']}({SETS[a.set]}) · 라우터 기준 {settings.router_threshold}\n"
            f"- 라우터가 엑사원으로 보낸(보낼) 메일 {routed}건 · 실행 {elapsed:.1f}초\n")
    md = report(res, out, SETS[a.set]).replace("\n\n", "\n\n" + head, 1)
    if a.llm:
        md += llm_section(llm.calls)
    rep = out.with_name(f"eval_report_{out.stem}.md")
    rep.write_text(md, encoding="utf-8")
    print(f"{len(preds)}건 · 엑사원 대상 {routed}건 · 완전 정답 {res['full']}/{res['n']} · "
          f"Task 재현율 {pct(res['bin']['Task 여부'][1])} · 놓친 Task 메일 {res['bin']['Task 여부'][3]}건 → {rep.relative_to(ROOT)}")

if __name__ == "__main__":
    main()
