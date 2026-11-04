"""더미 메일 세트를 ai 분류 파이프라인에 넣어 predictions.json을 만든다 (DE-4 · AI-18 공용, 관리는 데이터 · 평가 DE-D8).

사용 (레포 루트에서, ai/.venv 파이썬으로):
  ai/.venv/bin/python eval/runners/run_dummy.py                 # 규칙만 (엑사원 없이)
  ai/.venv/bin/python eval/runners/run_dummy.py --llm           # 확신도 낮은 메일은 엑사원 (ollama 필요)
  ai/.venv/bin/python eval/runners/run_dummy.py --set test      # 테스트셋 test-v1 (규칙 수정에 쓰지 않는 세트, eval/datasets/README.md)
  ai/.venv/bin/python eval/runners/run_dummy.py --set dev2      # 보조 개발셋 dev2-v1 47건 (dev 100건에 맞춘 개선이 일반화되는지 확인)
  ai/.venv/bin/python eval/runners/run_dummy.py --set dev4      # 개발셋 v2 100통 (DE-3에서 build.py dev4로 만든다)
  ai/.venv/bin/python eval/runners/run_dummy.py --file <레포 밖 폴더>/testA_mails.json --llm   # 봉인 테스트 A · B (DE-D15)
    --file은 레포 밖 세트 파일을 읽고, 결과 · 보고서 · 모델 출력 캐시를 그 파일 옆에 남긴다(레포 안 --out은 거부).
보낸 메일(from == mailbox.owner, S-번호)은 분류에 넣지 않고 채점에서도 뺀다(DE-D10: 응답 대기 재료, 분류 대상 아님).
결과: eval/reports/predictions_<rule|llm>.json(테스트셋은 predictions_test_<rule|llm>.json)
      + 채점 보고서 eval_report_<같은 이름>.md (data/dummy/eval.py 채점기)
실행기는 LLM_BACKEND(ollama 기본 | llamacpp)로 고른다. 예: LLM_BACKEND=llamacpp ... --llm
--llm은 엑사원 호출마다 응답 시간 · JSON 형식 오류 · 시간 내역(로딩 · 입력 읽기 · 출력 생성)을 재서 보고서에 붙인다.
첫 호출은 모델 로딩이라 평균에서 뺀다. 모델 출력은 llm_cache_<같은 이름>.json에 남는다.
  --replay eval/reports/llm_cache_predictions_llm.json   # 남긴 모델 출력으로 다시 채점(모델 없이). 후처리 · 합치기 규칙 실험용
    프롬프트가 한 글자라도 다르면 캐시에 없어 규칙 결과로 대신한다(보고서에 건수를 적는다). temperature 0이라 출력은 같다고 본다.

eval → ai 방향으로만 부른다(ai/README 규칙). 개인정보 가리기는 하지 않는다(더미는 가상 인물).
"""
import argparse
import hashlib
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
from app.pipeline import kinds  # noqa: E402
from app.pipeline.classify import PROMPT, classify, route  # noqa: E402
from app.pipeline.rules.mail_rules_v1 import RULES_VERSION, judge  # noqa: E402
from eval import evaluate, is_sealed, load_gold, pct, received, report  # noqa: E402  data/dummy/eval.py
from app.schemas.classify import ClassifyRequest, OwnerProfile, SenderFlags  # noqa: E402


def signature_sender(body: str) -> dict:
    """서명란 첫 줄 '박지영 팀장 / Jiyoung Park'과 조직 줄 마지막 칸에서 발신자를 읽는다(채점용)."""
    sig = re.split(r"\n\*{5,}\n", body)
    lines = sig[1].split("\n") if len(sig) > 1 else []
    m = re.match(r"(\S+)\s+(\S+)\s*/", lines[0]) if lines else None
    team = lines[1].split("/")[-1].strip() if len(lines) > 1 and "/" in lines[1] else None
    return {"name": m[1] if m else None, "position": m[2] if m else None, "team": team}


SETS = {"dev": "dummy_mails.json", "test": "test_mails.json", "dev2": "dev2_mails.json", "dev3": "dev3_mails.json", "test3": "test3_mails.json",
        "dev4": "dev4_mails.json"}  # 봉인 테스트 A · B는 레포 밖이라 SETS에 없다 → --file


def set_file(a) -> Path:
    """--file(레포 밖 봉인 세트 등)이 있으면 그 파일, 없으면 data/dummy의 --set 파일."""
    src = a.file.expanduser().resolve() if a.file else ROOT / "data/dummy" / SETS[a.set]
    if not src.is_file():
        sys.exit(f"세트 파일이 없다: {src.name}" + (" — dev4는 DE-3에서 만든다(data/dummy/build.py dev4)" if a.set == "dev4" and not a.file else ""))
    return src


def prompt_key(system: str, user: str) -> str:
    return hashlib.sha256(f"{system}\0{user}".encode()).hexdigest()[:24]


class TimedClient:
    """엑사원 호출마다 걸린 시간 · 실패 사유 · 시간 내역을 남긴다. 실패는 그대로 올려 파이프라인이 규칙 결과로 대신하게 한다."""

    def __init__(self, inner):
        self.inner, self.model, self.calls, self.cache = inner, inner.model, [], {}

    def chat_json(self, system, user, schema):
        t = time.perf_counter()
        try:
            out = self.inner.chat_json(system, user, schema)
            self.calls.append((time.perf_counter() - t, None, dict(getattr(self.inner, "last_stats", {}))))
            self.cache[prompt_key(system, user)] = out
            return out
        except LLMError as e:
            self.calls.append((time.perf_counter() - t, str(e), {}))
            raise


class ReplayClient:
    """--replay: 앞선 --llm 실행이 남긴 모델 출력을 돌려준다. 없는 프롬프트는 LLMError → 규칙 결과로 대신한다."""

    def __init__(self, path: Path, model: str):
        self.model, self.cache, self.misses = model, json.loads(path.read_text(encoding="utf-8")), 0

    def chat_json(self, system, user, schema):
        out = self.cache.get(prompt_key(system, user))
        if out is None:
            self.misses += 1
            raise LLMError("replay: 캐시에 없는 프롬프트")
        return out


def runtime_version(settings, health) -> str:
    """보고서 머리에 적을 실행기 이름 · 버전. llama.cpp는 /props의 build_info, ollama는 health의 버전 · 모델 digest."""
    if settings.llm_backend != "llamacpp":  # Unix 소켓(OLLAMA_UDS)으로 붙어도 읽히도록 클라이언트가 잰 값을 쓴다
        return f"ollama {health.get('version') or '?'} · digest {(health.get('digest') or '?')[:12]}"
    try:
        return f"llama.cpp {httpx.get(f'{settings.llamacpp_base_url}/props', timeout=5).json().get('build_info', '?')}"
    except (httpx.HTTPError, ValueError):
        return f"{settings.llm_backend} 버전 확인 실패"


def stats_rows(stats: list[dict]) -> list[str]:
    """호출 시간을 로딩 · 입력 읽기 · 출력 생성으로 나눈다. 초당 토큰이 PC 탓인지(속도) 방식 탓인지(토큰 수) 가른다."""
    if not stats:
        return []
    avg = {k: sum(x[k] for x in stats) / len(stats) for k in stats[0]}
    total = avg["load_s"] + avg["prompt_s"] + avg["gen_s"] or 1
    gen_tps = sum(x["gen_tokens"] for x in stats) / (sum(x["gen_s"] for x in stats) or 1)
    return [f"| 입력 토큰 (시스템 프롬프트 포함) · 입력 읽기 | {avg['prompt_tokens']:.0f}개 · {avg['prompt_s']:.1f}초 ({avg['prompt_s'] / total:.0%}) |",
            f"| 출력 토큰 · 출력 생성 | {avg['gen_tokens']:.0f}개 · {avg['gen_s']:.1f}초 ({avg['gen_s'] / total:.0%}) · 초당 {gen_tps:.1f}개 |",
            f"| 모델 로딩 | {avg['load_s']:.1f}초 ({avg['load_s'] / total:.0%}) |"]


def llm_section(calls) -> str:
    ok = [s for s, e, _ in calls if e is None]
    timed = ok[1:] if len(ok) > 1 else ok  # 첫 호출은 모델 로딩 시간이 섞인다
    stats = [st for _, e, st in calls if e is None and st][1:]
    call_err = [e for _, e, _ in calls if e and "호출 실패" in e]
    fmt_err = [e for _, e, _ in calls if e and "호출 실패" not in e]
    L = ["", "## 엑사원 호출", "", "| 항목 | 값 |", "|---|---|",
         f"| 호출 수 | {len(calls)} |",
         f"| 메일 1통 평균 응답 시간 (첫 호출 제외) | {sum(timed) / len(timed):.1f}초 |" if timed else "| 메일 1통 평균 응답 시간 | - |",
         f"| 최소 / 최대 | {min(timed):.1f}초 / {max(timed):.1f}초 |" if timed else "| 최소 / 최대 | - |",
         f"| 첫 호출 (로딩 포함) | {ok[0]:.1f}초 |" if ok else "| 첫 호출 | - |",
         *stats_rows(stats),
         f"| JSON 형식 오류 | {len(fmt_err)}건 |",
         f"| 호출 실패 (연결 · 시간 초과) | {len(call_err)}건 |"]
    L += [f"- {e}" for e in sorted(set(fmt_err + call_err))]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="엑사원 사용 (기본: 규칙만)")
    ap.add_argument("--set", choices=SETS, default="dev", help="dev: 더미 v1 100건(개발 세트) · test: test-v1(테스트셋) · dev2: dev2-v1(보조 개발셋, 과적합 확인용) · dev4: 개발셋 v2(DE-3)")
    ap.add_argument("--file", type=Path, default=None, help="레포 밖 세트 파일(봉인 테스트 A · B). 주면 --set은 무시하고 결과를 그 파일 옆에 남긴다")
    ap.add_argument("--replay", type=Path, default=None, help="남긴 모델 출력(llm_cache_*.json)으로 채점, 모델 호출 없음")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    src = set_file(a)
    outside = not src.is_relative_to(ROOT)
    out_dir = src.parent if a.file and outside else ROOT / "eval/reports"
    if a.file and outside and a.out and Path(a.out).resolve().is_relative_to(ROOT):
        sys.exit("레포 밖 세트의 결과는 레포 안에 쓰지 않는다(DE-D15). --out을 빼거나 레포 밖 경로로")

    settings = replace(get_settings(), llm_enabled=a.llm)
    warm_s = None
    llm = build_client(settings)
    if a.replay:
        a.llm, llm = False, ReplayClient(a.replay, settings.model)
    elif a.llm:
        h = llm.health()
        if not h.get("model_ready"):  # 연결이 안 되면 전부 규칙 결과로 대신해 '엑사원 점수'처럼 보이게 된다
            url = settings.llamacpp_base_url if settings.llm_backend == "llamacpp" else (settings.ollama_uds or settings.ollama_base_url)
            sys.exit(f"엑사원 준비 안 됨({settings.llm_backend} {url} · {settings.model}): {h}")
        if hasattr(llm, "warm"):  # ai 서비스 시작 때처럼 시스템 프롬프트를 미리 읽힌다. 안 하면 첫 메일이 캐시 미적중으로 120초 제한에 걸린다(11/3 dev2 M-0001)
            t = time.perf_counter()
            llm.warm(PROMPT.SYSTEM)
            warm_s = time.perf_counter() - t
        llm = TimedClient(llm)
    data = json.loads(src.read_text(encoding="utf-8"))
    box, me = data["mailbox"], data["people"]["me"]
    mails = received(data)  # 보낸 메일은 건너뛴다
    skipped = len(data["mails"]) - len(mails)
    owner = OwnerProfile(email=box["owner"], name=me["name"], position=me["position"], team=me["team"], member_of=box["member_of"])

    preds, routed, t0 = [], 0, time.perf_counter()
    for o in mails:
        m = o["mail"]
        req = ClassifyRequest(**{"from": m["from"]}, mail_id=m["id"], to=m["to"], cc=m["cc"], subject=m["subject"],
                              body=m["body"], attachments=m["attachments"], received_at=m["received_at"], owner=owner,
                              sender=SenderFlags(is_superior=m["from"] in box["superiors"], is_favorite=m["from"] in box["favorites"]))
        r = classify(req, llm, settings)
        rr = judge(req)
        routed += route(rr, kinds.classify_kind(req, rr), settings.router_threshold)  # 문지기 라우터(v3.2)
        preds.append({
            "id": m["id"], "sender": signature_sender(m["body"]), "action_types": r.action_types,
            "mentioned_me": r.mentioned_me, "urgent": r.urgent, "is_follow_up": r.is_follow_up, "priority": r.priority,
            "tasks": [{"action": t.text, "format": t.format, "due_raw": t.due_raw,
                       "due_at": t.due_at.strftime("%Y-%m-%dT%H:%M") if t.due_at else None} for t in r.tasks],
            "checks": [{"text": c.text, "reason": c.reason, "source": c.source, "evidence": c.evidence} for c in r.checks],
            "kind": r.kind, "kind_sure": r.kind_sure, "lane": r.lane,
            "_source": r.source, "_confidence": r.confidence, "_fallback": r.fallback,
        })

    tag = src.stem.removesuffix("_mails") if a.file else "" if a.set == "dev" else a.set
    name = f"predictions_{tag + '_' if tag else ''}{'llm' if a.llm else 'replay' if a.replay else 'rule'}.json"
    out = Path(a.out) if a.out else out_dir / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(preds, ensure_ascii=False, indent=1), encoding="utf-8")
    elapsed = time.perf_counter() - t0

    res = evaluate(load_gold(src), preds)
    head = (f"- 버전: 규칙 {RULES_VERSION} · 프롬프트 {PROMPT.PROMPT_VERSION if a.llm or a.replay else '미사용'} · "
            f"모델 {settings.model if a.llm else '미사용(규칙만)'} · "
            f"실행기 {runtime_version(settings, h) if a.llm else '미사용'} · "
            f"데이터 {data['meta']['version']}({src.name}) · 라우터 기준 {settings.router_threshold}\n"
            f"- 라우터가 엑사원으로 보낸(보낼) 메일 {routed}건 · 실행 {elapsed:.1f}초"
            f"{f' · 보낸 메일 {skipped}통은 분류 · 채점에서 뺌' if skipped else ''}"
            f"{f' · 시작 전 시스템 프롬프트 미리 읽기 {warm_s:.1f}초(실행 시간 제외)' if warm_s is not None else ''}\n")
    md = report(res, out, src.name, hide=is_sealed(src)).replace("\n\n", "\n\n" + head, 1)  # 시험 · 봉인 세트는 오답 ID 숨김
    if a.llm:
        md += llm_section(llm.calls)
        out.with_name(f"llm_cache_{out.stem}.json").write_text(json.dumps(llm.cache, ensure_ascii=False), encoding="utf-8")
    if a.replay:
        md += f"\n- replay: {a.replay.name} · 캐시에 없어 규칙 결과로 대신한 메일 {llm.misses}건\n"
    rep = out.with_name(f"eval_report_{out.stem}.md")
    rep.write_text(md, encoding="utf-8")
    print(f"{len(preds)}건 · 엑사원 대상 {routed}건 · 완전 정답 {res['full']}/{res['n']} · "
          f"Task 재현율 {pct(res['bin']['Task 여부'][1])} · 놓친 Task 메일 {res['bin']['Task 여부'][3]}건"
          f"{f' · replay 캐시 없음 {llm.misses}건' if a.replay else ''} → {rep}")

if __name__ == "__main__":
    main()
