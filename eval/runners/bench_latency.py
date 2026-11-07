"""엑사원 응답 시간 벤치 (AI-1 · 미결 #6 GPU 서빙 판단용). scripts/gpu/run_all.sh가 부르고, PC(CPU)에서도 같은 명령으로 잰다.

분류는 실제 파이프라인(classify)을, 명령은 실제 명령 해석(plan)을 그대로 부른다 — 프롬프트 · 규칙이 바뀌어도 이 파일은 그대로 쓴다.
시나리오 (--scenarios, 쉼표로 여럿)
  classify-warm  분류 시스템 프롬프트를 미리 읽힌 뒤 라우터행 메일 N통. ollama 프리픽스 캐시가 맞는 평소 상황
  agent-warm     명령 시스템 프롬프트를 미리 읽힌 뒤 모델 경로로 가는 명령 M개
  alternate      분류 1통 → 명령 1개를 K번 번갈아. OLLAMA_NUM_PARALLEL=1이면 바뀔 때마다 시스템 프롬프트를 처음부터 읽는다
                 (11/3 PC: 분류 채점 직후 명령 1건 70.6초 — 명령 시스템 프롬프트 857토큰을 다시 읽음)
  cold-load      모델을 내린 뒤(keep_alive 0) 분류 1통. 모델 로딩 + 시스템 프롬프트 전체 읽기 (11/3 PC 첫 호출 117초)
결과: --out 마크다운(## 요약 표) + 같은 이름 .json(호출별 원자료)

사용 (레포 루트에서):
  ai/.venv/bin/python eval/runners/bench_latency.py --set dev3 --n 20 --m 20 --k 10 --out eval/reports/bench_cpu.md
  scripts/exaone-pc.sh run ai/.venv/bin/python eval/runners/bench_latency.py ...   # PC 엑사원으로 같은 벤치
  ai/.venv/bin/python eval/runners/bench_latency.py --fake --out <scratch>/bench_fake.md    # 모델 없이 코드 경로만 확인(수치는 가짜)
"""
import argparse
import json
import math
import statistics
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai"))
sys.path.insert(0, str(ROOT / "eval/runners"))

from app.agent.plan import plan  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.llm.client import LLMError, build_client  # noqa: E402
from app.pipeline.classify import PROMPT, classify  # noqa: E402
from app.prompts import agent_v1  # noqa: E402
from app.schemas.agent import PlanContext, PlanRequest  # noqa: E402
from app.schemas.classify import ClassifyRequest, OwnerProfile, SenderFlags  # noqa: E402
from run_agent_commands import ACTIONS  # noqa: E402  backend 행동 레지스트리와 같은 목록 한 곳

SETS = {"dev": "dummy_mails.json", "dev2": "dev2_mails.json", "dev3": "dev3_mails.json"}  # 시험 세트(test · test3)는 쓰지 않는다
SCENARIOS = ["classify-warm", "agent-warm", "alternate", "cold-load"]


class Probe:
    """모델 경로로 가는지만 본다. 부르면 기록하고 LLMError로 돌려보낸다(규칙 결과로 대신)."""

    def __init__(self, model):
        self.model, self.called = model, False

    def chat_json(self, system, user, schema):
        self.called = True
        raise LLMError("probe")


class Timed:
    """호출마다 걸린 시간 · ollama 시간 내역(last_stats)을 남긴다."""

    def __init__(self, inner):
        self.inner, self.model, self.rows, self.tag = inner, inner.model, [], ("", "")

    def chat_json(self, system, user, schema):
        t = time.perf_counter()
        err = None
        try:
            return self.inner.chat_json(system, user, schema)
        except LLMError as e:
            err = str(e)
            raise
        finally:
            st = dict(getattr(self.inner, "last_stats", {}) or {}) if err is None else {}
            self.rows.append({"scenario": self.tag[0], "kind": self.tag[1], "wall_s": time.perf_counter() - t, "error": err, **st})


class Fake:
    """--fake: 모델 없이 코드 경로를 확인한다. 시간 · 토큰은 지어낸 값이다."""

    def __init__(self, model):
        self.model, self.last_stats, self.n = model, {}, 0

    def chat_json(self, system, user, schema):
        self.n += 1
        time.sleep(0.01)
        cls = "action_types" in schema.get("properties", {})
        self.last_stats = {"load_s": 0.0, "prompt_tokens": 900 if cls else 860, "prompt_s": 0.1 + 0.01 * (self.n % 3),
                           "gen_tokens": 40 if cls else 12, "gen_s": 0.4 if cls else 0.15}
        return {"action_types": ["기타"], "tasks": []} if cls else {"action": "unsupported"}

    def warm(self, system=None):
        pass


def mail_requests(set_name: str):
    data = json.loads((ROOT / "data/dummy" / SETS[set_name]).read_text(encoding="utf-8"))
    box, me = data["mailbox"], data["people"]["me"]
    owner = OwnerProfile(email=box["owner"], name=me["name"], position=me["position"], team=me["team"], member_of=box["member_of"])
    for o in data["mails"]:
        m = o["mail"]
        yield ClassifyRequest(**{"from": m["from"]}, mail_id=m["id"], to=m["to"], cc=m["cc"], subject=m["subject"], body=m["body"],
                              attachments=m["attachments"], received_at=m["received_at"], owner=owner,
                              sender=SenderFlags(is_superior=m["from"] in box["superiors"], is_favorite=m["from"] in box["favorites"]))


def routed_mails(set_name: str, n: int):
    """모델에 묻는 메일(AI-D15부터 전부). 모자라면 처음부터 다시 쓴다."""
    reqs = list(mail_requests(set_name))
    return [reqs[i % len(reqs)] for i in range(n)] if reqs else []


def model_path_commands(dataset: Path, m: int):
    """규칙이 정하지 못해 모델로 가는 명령만 고른다(Probe로 확인)."""
    out = []
    for ln in dataset.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        r = json.loads(ln)
        req = PlanRequest(text=r["text"], actions=ACTIONS, context=PlanContext(
            now=r["now"], selected_mail_ids=r.get("selected_mail_ids", []), last_result_ids=r.get("last_result_ids", [])))
        probe = Probe("probe")
        plan(req, probe)
        if probe.called:
            out.append(req)
    return [out[i % len(out)] for i in range(m)] if out else []


def unload(settings):
    """모델을 메모리에서 내린다(cold-load용). ollama만 지원."""
    import httpx
    transport = httpx.HTTPTransport(uds=settings.ollama_uds) if settings.ollama_uds else None
    with httpx.Client(base_url=settings.ollama_base_url, timeout=60, transport=transport) as c:
        c.post("/api/generate", json={"model": settings.model, "keep_alive": 0})
    time.sleep(2)


def pctl(xs: list[float], q: float) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, max(0, math.ceil(q * len(s)) - 1))]


def summarize(rows: list[dict]) -> list[str]:
    head = ["| 시나리오 | 종류 | 호출 | 평균 | p50 | p95 | 최소 / 최대 | 로딩 | 입력 읽기 | 입력 토큰 | 출력 생성 · 초당 | 실패 |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    out = []
    for sc in dict.fromkeys(r["scenario"] for r in rows):
        for kind in dict.fromkeys(r["kind"] for r in rows if r["scenario"] == sc):
            g = [r for r in rows if r["scenario"] == sc and r["kind"] == kind]
            ok = [r for r in g if r["error"] is None]
            if not ok:
                out.append(f"| {sc} | {kind} | {len(g)} | - | - | - | - | - | - | - | - | {len(g)} |")
                continue
            w = [r["wall_s"] for r in ok]
            avg = lambda k: statistics.mean(r.get(k, 0) for r in ok)  # noqa: E731
            gen_tps = sum(r.get("gen_tokens", 0) for r in ok) / (sum(r.get("gen_s", 0) for r in ok) or 1)
            out.append(f"| {sc} | {kind} | {len(g)} | {statistics.mean(w):.2f}초 | {pctl(w, .5):.2f}초 | {pctl(w, .95):.2f}초 | "
                       f"{min(w):.2f} / {max(w):.2f}초 | {avg('load_s'):.2f}초 | {avg('prompt_s'):.2f}초 | {avg('prompt_tokens'):.0f}개 | "
                       f"{avg('gen_s'):.2f}초 · {gen_tps:.1f}개 | {len(g) - len(ok)} |")
    return head + out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", choices=SETS, default="dev3", help="분류 메일을 고를 개발 세트(시험 세트는 쓰지 않는다)")
    ap.add_argument("--commands", type=Path, default=ROOT / "eval/datasets/agent_commands_v2.jsonl", help="모델 경로 명령을 고를 세트")
    ap.add_argument("--n", type=int, default=20, help="classify-warm 메일 수")
    ap.add_argument("--m", type=int, default=20, help="agent-warm 명령 수")
    ap.add_argument("--k", type=int, default=10, help="alternate 왕복 수")
    ap.add_argument("--repeat", type=int, default=1, help="시나리오 묶음 반복 횟수")
    ap.add_argument("--scenarios", default=",".join(SCENARIOS))
    ap.add_argument("--label", default="", help="보고서 머리에 적을 설명(예: GPU NUM_PARALLEL=2)")
    ap.add_argument("--fake", action="store_true", help="모델 없이 코드 경로만 확인")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    scen = [s for s in a.scenarios.split(",") if s]
    bad = set(scen) - set(SCENARIOS)
    if bad:
        sys.exit(f"모르는 시나리오: {bad}")

    settings = replace(get_settings(), llm_enabled=True)
    inner = Fake(settings.model) if a.fake else build_client(settings)
    health = {} if a.fake else inner.health()
    if not a.fake and not health.get("model_ready"):
        sys.exit(f"엑사원 준비 안 됨: {health}")
    llm = Timed(inner)
    commands = a.commands if a.commands.is_absolute() else ROOT / a.commands
    mails = routed_mails(a.set, max(a.n, a.k, 1))
    cmds = model_path_commands(commands, max(a.m, a.k, 1))
    agent_system = agent_v1.render_system(ACTIONS)
    warm = getattr(inner, "warm", None)

    def run_mail(req, sc):
        llm.tag = (sc, "분류")
        classify(req, llm, settings)

    def run_cmd(req, sc):
        llm.tag = (sc, "명령")
        plan(req, llm)

    t0 = time.perf_counter()
    for _ in range(a.repeat):
        if "classify-warm" in scen and mails:
            warm and warm(PROMPT.SYSTEM)
            for r in mails[:a.n]:
                run_mail(r, "classify-warm")
        if "agent-warm" in scen and cmds:
            warm and warm(agent_system)
            for r in cmds[:a.m]:
                run_cmd(r, "agent-warm")
        if "alternate" in scen and mails and cmds:
            warm and warm(PROMPT.SYSTEM)
            for i in range(a.k):
                run_mail(mails[i], "alternate")
                run_cmd(cmds[i], "alternate")
        if "cold-load" in scen and mails:
            if not a.fake and settings.llm_backend == "ollama":
                unload(settings)
            run_mail(mails[0], "cold-load")
            warm and warm(PROMPT.SYSTEM)
    elapsed = time.perf_counter() - t0

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(llm.rows, ensure_ascii=False, indent=1), encoding="utf-8")
    md = [f"# 응답 시간 벤치 · {out.stem}{' · ' + a.label if a.label else ''}", "",
          f"- 모델 {settings.model} · {'가짜 모델(--fake, 수치 무의미)' if a.fake else 'ollama ' + str(health.get('version')) + ' · digest ' + str(health.get('digest'))[:12]}",
          f"- 분류 프롬프트 {PROMPT.PROMPT_VERSION} · 명령 프롬프트 {agent_v1.PROMPT_VERSION}",
          f"- 분류 메일: {a.set} 라우터행 {len({r.mail_id for r in mails})}통에서 · 명령: {commands.name} 모델 경로 {len({r.text for r in cmds})}개에서 · 반복 {a.repeat}회 · 전체 {elapsed:.0f}초",
          "- 입력 토큰은 프리픽스 캐시로 다시 읽지 않은 토큰까지 센다 → 캐시 적중 여부는 '입력 읽기' 초로 본다(client.ollama_stats).",
          "", "## 요약", "", *summarize(llm.rows), ""]
    out.write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
