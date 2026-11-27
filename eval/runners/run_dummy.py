"""더미 메일 세트를 ai 분류 파이프라인에 넣어 predictions.json을 만든다 (DE-4 · AI-18 공용, 관리는 데이터 · 평가 DE-D8).

사용 (레포 루트에서, ai/.venv 파이썬으로):
  ai/.venv/bin/python eval/runners/run_dummy.py                 # 모델 없이: 조건만(할 일 없음 · 분류 실패). 실행기 점검용, 점수 비교에 쓰지 않는다
  ai/.venv/bin/python eval/runners/run_dummy.py --llm           # 모든 메일을 모델이 판단 (.env의 LLM_BACKEND로 부른다 — 서비스와 같은 exaone_api, D52)
  ai/.venv/bin/python eval/runners/run_dummy.py --set test      # 테스트셋 test-v1 (규칙 수정에 쓰지 않는 세트, eval/datasets/README.md)
  ai/.venv/bin/python eval/runners/run_dummy.py --set dev2      # 보조 개발셋 dev2-v1 47건 (dev 100건에 맞춘 개선이 일반화되는지 확인)
  ai/.venv/bin/python eval/runners/run_dummy.py --set dev4      # 개발셋 v2 100통 (DE-3에서 build.py dev4로 만든다)
  ai/.venv/bin/python eval/runners/run_dummy.py --file <레포 밖 폴더>/testA_mails.json --llm   # 봉인 테스트 A · B (DE-D15)
  ai/.venv/bin/python eval/runners/run_dummy.py --set dev4 --or anthropic/claude-haiku-5.5   # 오픈라우터 모델로 평가(DE-D24: 이것과 deepseek/deepseek-v4.1-flash 2종)
    --or는 레포 맨 위 .env의 OPENROUTER_API_KEY를 읽는다(.env.example 참고, .env는 깃에 안 올라감). 결과 이름에 모델이 붙는다(predictions_<세트>_or-<모델>.json).
    --file은 레포 밖 세트 파일을 읽고, 결과 · 보고서 · 모델 출력 캐시를 그 파일 옆에 남긴다(레포 안 --out은 거부).
보낸 메일(from == mailbox.owner, S-번호)은 분류에 넣지 않고 채점에서도 뺀다(DE-D10: 응답 대기 재료, 분류 대상 아님).
결과: eval/reports/predictions_<rule|llm>.json(테스트셋은 predictions_test_<rule|llm>.json)
      + 채점 보고서 eval_report_<같은 이름>.md (data/dummy/eval.py 채점기)
      + 요약 보고서 summary.md 하나: 실행마다 그 세트 · 방식 줄만 덮어쓴다(놓침 · 할 일로 잡음 · 정밀도 · 메일 1통 시간 · 놓친 메일 ID)
실행기는 LLM_BACKEND(exaone_api 기본 | ollama | llamacpp)로 고른다. 서비스와 같은 호출부(ai/app/llm/client.py)를 그대로 쓴다(D52).
  예: LLM_BACKEND=exaone_api ... --llm → predictions_<세트>_api-k-exaone_v2.5.json(로컬 결과 predictions_<세트>_llm.json을 덮어쓰지 않는다)
    추론 강도가 기본(max)이 아니면 이름에 붙는다(EXAONE_REASONING_EFFORT=low → api-k-exaone_v2.5@low). 강도가 다른 결과끼리 덮어쓰거나 이어 붙지 않는다
  엑사원 API 하루 한도를 다 쓰면 받은 출력을 남기고 멈춘다 → 다음 날 같은 명령 + --resume
  모델이 판단하지 못한 메일(호출 실패 · 형식 오류)은 끝난 뒤 그 메일만 2번까지 다시 부른다(--retry, 서비스는 backend가 3번). 보고서에 1차와 다시 부른 뒤를 나란히 적는다
--llm은 엑사원 호출마다 응답 시간 · JSON 형식 오류 · 시간 내역(로딩 · 입력 읽기 · 출력 생성)을 재서 보고서에 붙인다.
첫 호출은 모델 로딩이라 평균에서 뺀다. 모델 출력은 llm_cache_<같은 이름>.json에 남는다.
  --replay eval/reports/llm_cache_predictions_llm.json   # 남긴 모델 출력으로 다시 채점(모델 없이). 후처리 실험용
    결과 이름에 캐시가 붙는다(predictions_<세트>_replay-<캐시 이름>.json, 예: replay-or-anthropic-claude-haiku-5.5) — 모델마다 따로 남는다.
    프롬프트가 한 글자라도 다르면 캐시에 없어 분류 실패로 남는다(보고서에 건수를 적는다). temperature 0이라 출력은 같다고 본다.

  --model openrouter:anthropic/claude-haiku-5.5   # 모델 비교(AI-21): 엑사원 대신 OpenRouter 모델로 같은 프롬프트 · 조건을 돌린다(eval 전용, D41)
eval → ai 방향으로만 부른다(ai/README 규칙). 개인정보 가리기는 하지 않는다(더미는 가상 인물).
"""
import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai"))
sys.path.insert(0, str(ROOT / "data/dummy"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # openrouter.py

from app.core.config import get_settings  # noqa: E402
from app.llm.client import LLMError, LLMQuotaError, build_client  # noqa: E402
from app.pipeline.classify import PROMPT, classify  # noqa: E402
from app.pipeline.conditions import CONDITIONS_VERSION  # noqa: E402
from eval import evaluate, is_sealed, load_gold, pct, received, report, score_row, write_summary  # noqa: E402  data/dummy/eval.py
from openrouter_client import MAX_TOKENS as OR_MAX_TOKENS, REASONING_EFFORT as OR_EFFORT, OpenRouterClient, load_key  # noqa: E402  평가 전용 오픈라우터(DE-D24)
import pii_mask  # noqa: E402  서비스와 같은 개인정보 가리기(BE-6 · #94)
from app.schemas.classify import ClassifyRequest, OwnerProfile, SenderFlags  # noqa: E402


def signature_sender(body: str) -> dict:
    """서명란 첫 줄 '박지영 팀장 / Jiyoung Park'과 조직 줄 마지막 칸에서 발신자를 읽는다(채점용)."""
    sig = re.split(r"\n\*{5,}\n", body)
    lines = sig[1].split("\n") if len(sig) > 1 else []
    m = re.match(r"(\S+)\s+(\S+)\s*/", lines[0]) if lines else None
    team = lines[1].split("/")[-1].strip() if len(lines) > 1 and "/" in lines[1] else None
    return {"name": m[1] if m else None, "position": m[2] if m else None, "team": team}


SETS = {"core": "core50_mails.json",  # 11/11 핵심 회귀 세트 50통(make_core.py): 프롬프트 · 모델이 바뀔 때마다 이것만 새로 부른다
        "dev": "dummy_mails.json", "test": "test_mails.json", "dev2": "dev2_mails.json", "dev3": "dev3_mails.json", "test3": "test3_mails.json",
        "dev4": "dev4_mails.json",
        # 11/5(AI-18): test · test3는 오답을 열어 고쳤으므로 개발 세트다. 같은 파일을 dev5 · dev6으로도 부른다(이름은 호환용으로 둠)
        "dev5": "test_mails.json", "dev6": "test3_mails.json", "dev7": "dev7_mails.json", "dev8": "dev8_mails.json",
        "dev9": "dev9_mails.json", "dev10": "dev10_mails.json"}  # dev10: 11/22 외국어 · 스팸 · 피싱 32통(DE-13 후속). dev9: 11/14 길고 복잡한 메일 20통(DE-11). 봉인 테스트 A · B는 레포 밖이라 SETS에 없다 → --file


def set_file(a) -> Path:
    """--file(레포 밖 봉인 세트 등)이 있으면 그 파일, 없으면 data/dummy의 --set 파일."""
    src = a.file.expanduser().resolve() if a.file else ROOT / "data/dummy" / SETS[a.set]
    if not src.is_file():
        sys.exit(f"세트 파일이 없다: {src.name}" + (" — dev4는 DE-3에서 만든다(data/dummy/build.py dev4)" if a.set == "dev4" and not a.file else ""))
    return src


def requests(data: dict) -> list[tuple[dict, ClassifyRequest]]:
    """받은 메일마다 (메일 묶음, 분류 요청). 보낸 메일은 뺀다. compare_models.py도 같은 요청으로 모델 원출력을 본다."""
    box, me = data["mailbox"], data["people"]["me"]
    owner = OwnerProfile(email=box["owner"], name=me["name"], position=me["position"], team=me["team"], member_of=box["member_of"],
                         role_lists=box.get("role_lists", []), team_lists=box.get("team_lists", []))
    out = []
    for o in received(data):
        m = o["mail"]
        out.append((o, ClassifyRequest(**{"from": m["from"]}, mail_id=m["id"], to=m["to"], cc=m["cc"], subject=m["subject"],
                                       body=m["body"], attachments=m["attachments"], received_at=m["received_at"], owner=owner,
                                       sender=SenderFlags(is_superior=m["from"] in box["superiors"], is_favorite=m["from"] in box["favorites"]))))
    return out


def secs(x: float) -> str:
    """시간 표기. 규칙만은 메일 1통이 1밀리초 안팎이라 밀리초로 적는다."""
    return f"{x:.1f}초" if x >= 1 else f"{x:.2f}초" if x >= 0.1 else f"{x * 1000:.1f}밀리초"


def timing_text(elapsed: float, n: int, calls=None, replay=False, who: str = "엑사원") -> str:
    """분류 시간 문장(#15 문규남 리뷰: 메일 분류 시간도 지표로). 엑사원 호출 평균은 첫 호출(모델 로딩) 제외."""
    if not n:
        return "기록 없음"
    t = f"메일 1통 평균 {secs(elapsed / n)} (전체 {secs(elapsed)} · {n}통)"
    ok = [s for s, e, _ in calls or [] if e is None][1:]
    if ok:
        t += f" · {who} 호출 1회 평균 {secs(sum(ok) / len(ok))} ({len(ok)}회, 첫 호출 제외)"
    return t + (" · replay라 모델을 부르지 않은 시간" if replay else "")


def prompt_key(system: str, user: str) -> str:
    return hashlib.sha256(f"{system}\0{user}".encode()).hexdigest()[:24]


class TimedClient:
    """엑사원 호출마다 걸린 시간 · 실패 사유 · 시간 내역을 남긴다. 실패는 그대로 올려 파이프라인이 규칙 결과(분류 실패)로 남게 한다."""

    def __init__(self, inner, prior: dict | None = None):
        self.inner, self.model, self.calls, self.cache = inner, inner.model, [], {}
        self.prior, self.reused = prior or {}, 0  # --resume: 같은 프롬프트로 이미 받은 출력(다시 부르지 않는다)

    def chat_json(self, system, user, schema):
        key = prompt_key(system, user)
        if key in self.prior:
            self.reused += 1
            self.cache[key] = self.prior[key]
            return json.loads(json.dumps(self.prior[key]))
        t = time.perf_counter()
        if hasattr(self.inner, "last_stats"):
            self.inner.last_stats = {}  # 실패한 호출에 앞 호출의 토큰 수가 묻지 않게
        try:
            out = self.inner.chat_json(system, user, schema)
            self.calls.append((time.perf_counter() - t, None, dict(getattr(self.inner, "last_stats", {}))))
            self.cache[key] = out
            return out
        except LLMQuotaError as e:  # 파이프라인은 LLMError를 규칙 결과로 삼킨다 → 평가에서는 실행을 멈추게 바꿔 올린다
            from openrouter import QuotaExhausted
            raise QuotaExhausted(str(e)) from e
        except LLMError as e:  # 빈 답(finish=length)은 응답이 와서 토큰 수가 있다 — 출력 상한에 걸린 호출이 쓴 토큰을 남긴다(#210)
            self.calls.append((time.perf_counter() - t, str(e), dict(getattr(self.inner, "last_stats", None) or {})))
            raise


class RuleOnlyClient:
    """모델 없이: 모델을 부르지 않는다(실제 ollama가 켜져 있어도). 결과는 조건만 · 분류 실패다(AI-D15)."""

    def __init__(self, model: str):
        self.model = model

    def chat_json(self, system, user, schema):
        raise LLMError("모델 없이 실행")


class ReplayClient:
    """--replay: 앞선 --llm 실행이 남긴 모델 출력을 돌려준다. 없는 프롬프트는 LLMError → 분류 실패로 남는다."""

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
    if settings.llm_backend == "exaone_api":
        return health.get("version") or "엑사원 API"
    if settings.llm_backend != "llamacpp":  # Unix 소켓(OLLAMA_UDS)으로 붙어도 읽히도록 클라이언트가 잰 값을 쓴다
        return f"ollama {health.get('version') or '?'} · digest {(health.get('digest') or '?')[:12]}"
    try:
        return f"llama.cpp {httpx.get(f'{settings.llamacpp_base_url}/props', timeout=5).json().get('build_info', '?')}"
    except (httpx.HTTPError, ValueError):
        return f"{settings.llm_backend} 버전 확인 실패"


def stats_rows(stats: list[dict]) -> list[str]:
    """호출 시간을 로딩 · 입력 읽기 · 출력 생성으로 나눈다. 초당 토큰이 PC 탓인지(속도) 방식 탓인지(토큰 수) 가른다."""
    if stats and "load_s" not in stats[0]:  # OpenRouter: 시간 내역 대신 토큰 수 · 비용
        n = len(stats)
        return [f"| 입력 토큰 · 출력 토큰 (평균, 추론 토큰 포함) | {sum(x['prompt_tokens'] for x in stats) / n:.0f}개 · {sum(x['gen_tokens'] for x in stats) / n:.0f}개"
                f" (추론 {sum(x.get('reasoning_tokens', 0) for x in stats) / n:.0f}개) |",
                f"| 비용 (첫 호출 제외 {n}건) | ${sum(x['cost'] for x in stats):.4f} |"]
    if not stats:
        return []
    avg = {k: sum(x[k] for x in stats) / len(stats) for k in stats[0]}
    total = avg["load_s"] + avg["prompt_s"] + avg["gen_s"] or 1
    gen_tps = sum(x["gen_tokens"] for x in stats) / (sum(x["gen_s"] for x in stats) or 1)
    return [f"| 입력 토큰 (시스템 프롬프트 포함) · 입력 읽기 | {avg['prompt_tokens']:.0f}개 · {avg['prompt_s']:.1f}초 ({avg['prompt_s'] / total:.0%}) |",
            f"| 출력 토큰 · 출력 생성 | {avg['gen_tokens']:.0f}개 · {avg['gen_s']:.1f}초 ({avg['gen_s'] / total:.0%}) · 초당 {gen_tps:.1f}개 |",
            f"| 모델 로딩 | {avg['load_s']:.1f}초 ({avg['load_s'] / total:.0%}) |"]


def call_kind(e: str | None) -> str:
    """호출 1회의 결과 종류(짧은 코드): ok · length(빈 답 finish=length) · timeout · format(응답 · JSON 형식) · call(연결 · HTTP 등)."""
    if not e:
        return "ok"
    if "finish=length" in e:
        return "length"
    if "초과" in e or "Timeout" in e:
        return "timeout"
    if "형식" in e or "JSON" in e:
        return "format"
    return "call"


def fail_causes(errors) -> str:
    """실패 원인을 나눈다(#195 리뷰 3): 시간 초과 · 출력 한도(finish=length) · 그 밖(형식 오류 · HTTP 등)."""
    c = Counter("시간 초과" if ("초과" in e or "Timeout" in e) else "출력 한도(finish=length)" if "finish=length" in e else "그 밖"
                for e in errors)
    return f"({' · '.join(f'{k} {v}' for k, v in c.items())})" if c else ""


def llm_section(calls, title: str = "엑사원 호출", extra: str = "") -> str:
    ok = [s for s, e, _ in calls if e is None]
    timed = ok[1:] if len(ok) > 1 else ok  # 첫 호출은 모델 로딩 시간이 섞인다
    stats = [st for _, e, st in calls if e is None and st][1:]
    call_err = [e for _, e, _ in calls if e and "호출 실패" in e]
    fmt_err = [e for _, e, _ in calls if e and "호출 실패" not in e]
    L = ["", f"## {title}", "", "| 항목 | 값 |", "|---|---|",
         f"| 호출 수 | {len(calls)} |",
         f"| 메일 1통 평균 응답 시간 (첫 호출 제외) | {sum(timed) / len(timed):.1f}초 |" if timed else "| 메일 1통 평균 응답 시간 | - |",
         f"| 최소 / 최대 | {min(timed):.1f}초 / {max(timed):.1f}초 |" if timed else "| 최소 / 최대 | - |",
         f"| 첫 호출 (로딩 포함) | {ok[0]:.1f}초 |" if ok else "| 첫 호출 | - |",
         *stats_rows(stats),
         f"| JSON 형식 오류 | {len(fmt_err)}건 |",
         f"| 호출 실패 (연결 · 시간 초과) | {len(call_err)}건 |", *([extra] if extra else [])]
    L += [f"- {e}" for e in sorted(set(fmt_err + call_err))]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="모델 사용 (기본: 조건만, 점수 비교용 아님)")
    ap.add_argument("--set", choices=SETS, default="dev", help="dev: 더미 v1 100건(개발 세트) · test: test-v1(테스트셋) · dev2: dev2-v1(보조 개발셋, 과적합 확인용) · dev4: 개발셋 v2(DE-3)")
    ap.add_argument("--file", type=Path, default=None, help="레포 밖 세트 파일(봉인 테스트 A · B). 주면 --set은 무시하고 결과를 그 파일 옆에 남긴다")
    ap.add_argument("--replay", type=Path, default=None, help="남긴 모델 출력(llm_cache_*.json)으로 채점, 모델 호출 없음")
    ap.add_argument("--or", dest="openrouter", default=None, metavar="모델ID",
                    help="오픈라우터 모델로 평가(DE-D24: anthropic/claude-haiku-5.5 · deepseek/deepseek-v4.1-flash). 키는 .env의 OPENROUTER_API_KEY")
    ap.add_argument("--out", default=None)
    ap.add_argument("--retry", type=int, default=2, help="모델이 판단하지 못한 메일만 끝난 뒤 다시 부르는 횟수(기본 2, 0이면 안 함). 보고서에 1차와 다시 부른 뒤를 나란히 적는다")
    ap.add_argument("--mask", action="store_true", help="서비스처럼 이름 · 메일 주소 · 전화번호를 가려 모델에 보내고 응답은 되돌린다(BE-6 · #94, backend 가리개 그대로). 결과 이름에 _mask가 붙는다")
    ap.add_argument("--resume", action="store_true", help="같은 이름의 모델 출력 캐시가 있으면 그 메일은 다시 부르지 않는다(하루 한도로 멈춘 실행 이어 돌리기)")
    ap.add_argument("--prompt", default=None, help="분류 프롬프트 버전 바꿔 끼우기(예: classify_v6) — 프롬프트 전후 비교용(eval 전용)")
    ap.add_argument("--model", default=None, help="openrouter:<모델 ID> · exaone:k-exaone_v2.5 — 로컬 엑사원 대신 외부 API 모델(모델 비교 AI-21, eval 전용)")
    a = ap.parse_args()
    if a.prompt:
        import importlib
        import app.pipeline.classify as _cls
        _cls.PROMPT = importlib.import_module(f"app.prompts.{a.prompt}")
        globals()["PROMPT"] = _cls.PROMPT
    if a.model:
        a.llm = True
    if a.openrouter and (a.llm or a.replay):
        sys.exit("--or는 --llm · --model · --replay와 함께 쓰지 않는다")
    use_model = a.llm or bool(a.openrouter)  # 모델을 실제로 부르는 실행(엑사원 · --model · 오픈라우터 --or)
    src = set_file(a)
    outside = not src.is_relative_to(ROOT)
    out_dir = src.parent if a.file and outside else ROOT / "eval/reports"
    if a.file and outside and a.out and Path(a.out).resolve().is_relative_to(ROOT):
        sys.exit("레포 밖 세트의 결과는 레포 안에 쓰지 않는다(DE-D15). --out을 빼거나 레포 밖 경로로")

    settings = replace(get_settings(), llm_enabled=use_model)
    warm_s = None
    llm = build_client(settings)
    if a.model:
        from openrouter import make_client  # eval/runners/openrouter.py (eval 전용)
        llm = TimedClient(make_client(a.model))
        h = llm.inner.health()
    elif a.openrouter:  # 평가 전용 외부 모델(DE-D24). 준비가 안 되면 분류 실패가 모델 점수처럼 보이지 않게 멈춘다
        settings = replace(settings, model=a.openrouter)
        try:
            llm = OpenRouterClient(a.openrouter, load_key(), settings.llm_timeout_s)
        except LLMError as e:
            sys.exit(str(e))
        h = llm.health()
        if not h.get("model_ready"):
            sys.exit(f"오픈라우터 준비 안 됨({a.openrouter}): {h.get('error')}")
        if h.get("balance") is not None and h["balance"] <= 0:
            print(f"알림: 이 키로 본 계정 잔액이 {h['balance']}로 보인다. 첫 호출에서 확인하고, 크레딧이 없으면(HTTP 402) 바로 멈춘다")
        llm = TimedClient(llm)
    elif a.replay:
        a.llm, llm = False, ReplayClient(a.replay, settings.model)
    elif not a.llm:
        llm = RuleOnlyClient(settings.model)
    elif a.llm:
        h = llm.health()
        if not h.get("model_ready"):  # 연결이 안 되면 전부 분류 실패로 남아 '엑사원 점수'처럼 보이게 된다
            url = {"llamacpp": settings.llamacpp_base_url, "exaone_api": settings.exaone_api_base_url}.get(
                settings.llm_backend, settings.ollama_uds or settings.ollama_base_url)
            sys.exit(f"엑사원 준비 안 됨({settings.llm_backend} {url} · {llm.model}): {h}")
        if hasattr(llm, "warm"):  # ai 서비스 시작 때처럼 시스템 프롬프트를 미리 읽힌다. 안 하면 첫 메일이 캐시 미적중으로 120초 제한에 걸린다(11/3 dev2 M-0001)
            t = time.perf_counter()
            llm.warm(PROMPT.SYSTEM)
            warm_s = time.perf_counter() - t
        llm = TimedClient(llm)
    data = json.loads(src.read_text(encoding="utf-8"))
    mails = requests(data)  # 보낸 메일은 건너뛴다
    skipped = len(data["mails"]) - len(mails)

    tag = src.stem.removesuffix("_mails") if a.file else "" if a.set == "dev" else a.set
    mtag = re.sub(r"[^A-Za-z0-9._@]+", "-", a.model.split(":", 1)[1].split("/")[-1]) if a.model else None  # 'claude-haiku-5.5'
    if a.llm and not a.model and settings.llm_backend == "exaone_api":  # 서비스 호출부로 부른 엑사원 API(D52)
        mtag = f"api-{re.sub(r'[^A-Za-z0-9._@]+', '-', llm.model)}"
        if settings.exaone_reasoning_effort not in ("", "max"):  # 기본(max)이 아닌 강도는 이름에 붙인다 — 강도가 다른 결과끼리 덮어쓰거나 --resume으로 이어 붙지 않게(#64 리뷰)
            mtag += f"@{settings.exaone_reasoning_effort}"
    slug = re.sub(r"[^A-Za-z0-9.]+", "-", a.openrouter or "").strip("-")
    if a.openrouter and OR_MAX_TOKENS != 2000:  # 출력 상한이 기본과 다르면 이름에 붙인다(--resume로 섞이지 않게)
        slug += f"-cap{OR_MAX_TOKENS}"
    if a.openrouter and OR_EFFORT != "low":  # 추론 강도도 기본(low)과 다르면 이름에 붙인다
        slug += f"-{OR_EFFORT}"
    # replay는 어느 캐시를 썼는지 이름에 붙인다(llm_cache_predictions_dev4_or-X.json → replay-or-X). 두 모델 캐시가 서로 덮어쓰지 않게(#38 리뷰)
    rp = a.replay.stem.removeprefix("llm_cache_predictions_").removeprefix(f"{tag}_") if a.replay else ""
    name = (f"predictions_{tag + '_' if tag else ''}"
            f"{mtag or ('or-' + slug if a.openrouter else 'llm' if a.llm else 'replay-' + rp if a.replay else 'rule')}"
            f"{'_mask' if a.mask else ''}{'_' + a.prompt if a.prompt else ''}.json")
    out = Path(a.out) if a.out else out_dir / name
    cache_file = out.with_name(f"llm_cache_{out.stem}.json")
    if a.resume and use_model and cache_file.is_file():
        llm.prior = json.loads(cache_file.read_text(encoding="utf-8"))
    try:
        from openrouter import QuotaExhausted
    except ImportError:  # 외부 API를 쓰지 않는 실행
        QuotaExhausted = RuntimeError

    Masker = pii_mask.load_masker() if a.mask else None  # 서비스와 같은 가리개(backend/app/privacy/mask.py)
    mask_names = pii_mask.names_of(data) if a.mask else []
    mask_stats = {}  # 메일마다 (가린 값 수, 되돌리지 못한 대체어 수) — 다시 부르면 마지막 값
    times = []  # 메일마다 걸린 시간(다시 부른 것 포함) — 제한 시간을 정하는 근거(11/15 문규남 요청). timing_<결과 이름>.json
    timing_file = out.with_name(f"timing_{out.stem}.json")
    if a.resume and timing_file.is_file():  # 하루 한도로 나눠 잰 앞 실행의 시간도 잇는다(DE-13 리뷰: 엑사원 FINAL TEST 시간이 남지 않음)
        times = [x for x in json.loads(timing_file.read_text(encoding="utf-8")) if x.get("calls")]

    def one(o, req, n_done):
        """메일 1통 분류(걸린 시간을 남긴다)."""
        t = time.perf_counter()
        k = len(llm.calls) if use_model else 0
        p = one_mail(o, req, n_done)
        if use_model:  # 호출마다 출력 · 추론 토큰과 실패 사유(빈 답 · 시간 초과) — 강도 · 길이 구간별 표(#210, effort_table.py)
            new = llm.calls[k:]
            times.append({"id": p["id"], "s": round(time.perf_counter() - t, 1), "chars": len(o["mail"]["body"]),
                          "failed": p["_source"] == "failed", "error": (p["_fallback"] or "")[:80] if p["_source"] == "failed" else "",
                          "calls": len(new), "gen": sum(st.get("gen_tokens", 0) for _, _, st in new),
                          "reasoning": sum(st.get("reasoning_tokens", 0) for _, _, st in new),
                          "call_errors": [e[:80] for _, e, _ in new if e],
                          # 호출마다 시간 · 종류 · 토큰(#237 리뷰): 'N초 넘음'은 호출 기준, 토큰은 응답이 온 호출(gen이 None이 아님)만 센다
                          "call": [{"s": round(sec, 1), "kind": call_kind(e), "gen": st.get("gen_tokens") if st else None,
                                    "reasoning": st.get("reasoning_tokens") if st else None} for sec, e, st in new]})
        return p

    def one_mail(o, req, n_done):
        """메일 1통 분류 → 예측 한 줄. 모델이 판단하지 못하면(LLMError) '분류 실패' 줄, 하루 한도면 받은 출력을 남기고 멈춘다."""
        m = o["mail"]
        try:
            if Masker:  # 서비스처럼 가려 보내고(backend/app/jobs/classify.py) 응답은 원래 값으로 되돌린다
                mk = Masker(mask_names)
                masked_req = ClassifyRequest.model_validate(mk.mask_obj(req.model_dump(mode="json", by_alias=True)))
                mask_stats[m["id"]] = (mk.masked, 0)  # 모델이 실패해도 가린 수는 남긴다
                r = mk.unmask_model(classify(masked_req, llm, settings))
                mask_stats[m["id"]] = (mk.masked, Masker.leftover(r.model_dump(by_alias=True)))
            else:
                r = classify(req, llm, settings)
        except LLMError as e:  # AI-D19: 모델이 판단하지 못한 메일은 규칙으로 메우지 않는다 → '분류 실패'로 채점(정답으로 세지 않는다)
            return {"id": m["id"], "sender": signature_sender(m["body"]), "action_types": ["분류 실패"], "mentioned_me": False,
                    "urgent": False, "is_follow_up": False, "priority": "P3", "tasks": [], "checks": [], "lane": "분류 실패",
                    "_source": "failed", "_confidence": None, "_fallback": str(e)}
        except QuotaExhausted as e:  # 받은 출력은 남기고 멈춘다 → 한도가 풀리면 같은 명령 + --resume으로 남은 메일만 부른다
            out.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps({**llm.prior, **llm.cache}, ensure_ascii=False), encoding="utf-8")
            timing_file.write_text(json.dumps(times, ensure_ascii=False, indent=1), encoding="utf-8")  # 멈춘 실행의 시간도 남긴다 → --resume이 잇는다
            sys.exit(f"{e}\n{n_done}/{len(mails)}통까지 받은 출력을 {cache_file.name}에 남겼다. 같은 명령에 --resume을 붙여 이어서 돌린다")
        return {
            "id": m["id"], "sender": signature_sender(m["body"]), "action_types": r.action_types,
            "mentioned_me": r.mentioned_me, "urgent": r.urgent, "is_follow_up": r.is_follow_up, "priority": r.priority,
            "tasks": [{"type": t.type, "action": t.text, "format": t.format, "due_raw": t.due_raw, "deliver_to": t.deliver_to,
                       "due_at": t.due_at.strftime("%Y-%m-%dT%H:%M") if t.due_at else None, "evidence": t.evidence} for t in r.tasks],
            "checks": [{"text": c.text, "reason": c.reason, "source": c.source, "evidence": c.evidence} for c in r.checks],
            "lane": r.lane,
            "_source": r.source, "_confidence": r.confidence, "_fallback": r.fallback,
        }

    t0 = time.perf_counter()
    preds = []
    for n, (o, req) in enumerate(mails):
        preds.append(one(o, req, n))
        if use_model and ((n + 1) % 10 == 0 or n + 1 == len(mails)):  # 모델 실행은 몇 분 걸리니 진행 상황을 보여 준다
            print(f"  {n + 1}/{len(mails)}통 · {secs(time.perf_counter() - t0)}", flush=True)
    first_failed = sum(p["_source"] == "failed" for p in preds)
    first = [dict(p) for p in preds]  # 1차 결과(다시 부르기 전) — 보고서에 나란히 적는다
    # 서비스처럼 실패한 메일만 다시 부른다(#67 리뷰: backend는 3번까지, 평가는 끝난 뒤 --retry번). 같은 프롬프트라 replay · 조건만은 다시 불러도 같아 건너뛴다
    retried = 0
    for _ in range(a.retry if use_model else 0):
        todo = [i for i, p in enumerate(preds) if p["_source"] == "failed"]
        if not todo:
            break
        retried += len(todo)
        for i in todo:
            preds[i] = one(*mails[i], len(mails))

    failed_n = sum(p["_source"] == "failed" for p in preds)
    routed = sum(p["_source"] == "exaone" for p in preds)  # 모델 판단을 쓴 메일(실패하면 조건만)
    body = {o["mail"]["id"]: o["mail"]["body"] for o, _ in mails}
    tasks = [(t, body[p["id"]]) for p in preds for t in p["tasks"]]  # AI-15 근거 문장: 할 일마다 있나 · 줄마다 본문에 글자 그대로 있나(화면 형광펜이 찾을 수 있나)
    ev_tasks, ev_has = len(tasks), sum(bool(t["evidence"]) for t, _ in tasks)
    ev_body = sum(bool(t["evidence"]) and all(x in b for x in t["evidence"].split("\n")) for t, b in tasks)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(preds, ensure_ascii=False, indent=1), encoding="utf-8")
    elapsed = time.perf_counter() - t0
    if times:  # 메일마다 걸린 시간 · 본문 길이 · 실패 여부(봉인 세트는 레포 밖 결과 폴더에만 남는다)
        timing_file.write_text(json.dumps(times, ensure_ascii=False, indent=1), encoding="utf-8")

    res = evaluate(load_gold(src), preds, data["mailbox"]["owner"])
    head = (f"- 버전: 조건 {CONDITIONS_VERSION} · 프롬프트 {PROMPT.PROMPT_VERSION if use_model or a.replay else '미사용'} · "
            f"모델 {llm.model if use_model else '미사용(조건만)'} · "
            f"실행기 {'오픈라우터 API(평가 전용, DE-D24)' if a.openrouter else (h['version'] if a.model else runtime_version(settings, h)) if a.llm else '미사용'} · "
            f"데이터 {data['meta']['version']}({src.name}) · "
            f"판단은 모델 · 조건은 규칙(AI-D15)\n"
            f"- 모델 판단을 쓴 메일 {routed}건 · 분류 실패(모델이 판단하지 못함, 오답으로 채점) {failed_n}건 · 실행 {secs(elapsed)}(메일 1통 평균 {secs(elapsed / max(len(preds), 1))})"
            f"{f' · 보낸 메일 {skipped}통은 분류 · 채점에서 뺌' if skipped else ''}"
            f"{f' · 시작 전 시스템 프롬프트 미리 읽기 {warm_s:.1f}초(실행 시간 제외)' if warm_s is not None else ''}\n"
            f"- 근거 문장(AI-15): 예측 할 일 {ev_tasks}개 중 근거 있음 {ev_has}개 · 본문에 그대로 있음 {ev_body}개"
            f" (내용이 그 할 일 문장인지는 코드로 채점하지 않는다)\n")
    if a.mask:
        left = [v[1] for v in mask_stats.values()]
        head += (f"- 개인정보 가리기(--mask, BE-6 · #94 — backend 가리개 그대로, 이름 {len(set(filter(None, mask_names)))}개 · 메일 주소 · 전화번호): "
                 f"가린 값 {sum(v[0] for v in mask_stats.values())}개(메일 {len(mask_stats)}통) · "
                 f"되돌리지 못한 대체어 {sum(left)}개(그 메일 {sum(x > 0 for x in left)}통)\n")
    ts = sorted(x["s"] for x in times if x["calls"])  # calls 0 = --resume로 앞 실행 출력을 다시 쓴 메일(시간은 앞 실행 줄에 있다)
    if ts:  # 제한 시간(LLM_TIMEOUT_S) 근거: 메일 1통 처리 시간 분포 · 120초를 넘은 횟수
        q = lambda f: ts[min(len(ts) - 1, int(f * len(ts)))]  # noqa: E731
        head += (f"- 메일 1통 처리 시간(다시 부른 것 포함 {len(ts)}회{'' if a.openrouter or a.model else f', 제한 LLM_TIMEOUT_S {settings.llm_timeout_s:.0f}초'}): 중앙 {q(0.5):.1f}초 · 90% {q(0.9):.1f}초 · "
                 f"최대 {ts[-1]:.1f}초 · 120초 넘음 {sum(x > 120 for x in ts)}회 · 실패 {sum(x['failed'] for x in times)}회"
                 f"{fail_causes(x['error'] for x in times if x['failed'])} (메일마다 `timing_{out.stem}.json`)\n")
    if first_failed:  # 1차와 다시 부른 뒤를 나란히(#67 리뷰) — 서비스 점수는 '다시 부른 뒤'와 같다
        r1 = evaluate(load_gold(src), first, data["mailbox"]["owner"])
        head += (f"- 다시 부르기(--retry {a.retry}): 1차 분류 실패 {first_failed}통 → 다시 부른 뒤 {failed_n}통 (다시 부른 호출 {retried}회) · "
                 f"모든 칸 정답 1차 {r1['full']}/{r1['n']} → 다시 부른 뒤 {res['full']}/{res['n']} · "
                 f"놓친 할 일 메일 1차 {r1['bin']['Task 여부'][3]}통 → 다시 부른 뒤 {res['bin']['Task 여부'][3]}통\n")
    hide = is_sealed(src)  # 시험 · 봉인 세트는 오답 메일 ID 숨김
    timing = timing_text(elapsed, len(preds), llm.calls if use_model else None, bool(a.replay), "모델" if a.openrouter or a.model else "엑사원")
    md = report(res, out, src.name, hide=hide, timing=timing).replace("\n\n", "\n\n" + head, 1)
    if use_model:
        md += llm_section(llm.calls, f"오픈라우터 호출 ({a.openrouter})" if a.openrouter else f"모델 호출 ({llm.model})" if a.model else "엑사원 호출",
                          f"| 사용량 · 비용 | {llm.inner.cost_text()} |\n| 응답 형식 | {llm.inner.format_text()} |\n"
                          f"| 출력 상한(추론 포함) · 추론 강도 | {OR_MAX_TOKENS:,}토큰 · {OR_EFFORT} |" if a.openrouter else "")
        if a.model:
            md += (f"| 총 비용 | ${llm.inner.cost:.4f} |\n| 429 · 5xx 다시 부름 | {llm.inner.retries}회 |\n"
                   f"| JSON 뒤 글 붙음(첫 객체만 씀, 추론 off) | {llm.inner.loose}건 |\n")
        cache_file.write_text(json.dumps(llm.cache, ensure_ascii=False), encoding="utf-8")
        if llm.reused:
            md += f"\n- 이어 돌리기(--resume): 이전 실행 출력 {llm.reused}통 재사용 · 새로 부른 메일 {len(llm.calls)}통\n"
    if a.replay:
        md += f"\n- replay: {a.replay.name} · 캐시에 없어 분류 실패로 남은 메일 {llm.misses}건\n"
    rep = out.with_name(f"eval_report_{out.stem}.md")
    rep.write_text(md, encoding="utf-8")
    mode = mtag if a.model else f"오픈라우터 {a.openrouter.split('/')[-1]}" if a.openrouter else "엑사원" if a.llm else f"replay {rp}" if a.replay else "조건만"
    mode += " 가림" if a.mask else ""
    label = src.stem.removesuffix("_mails") if a.file else a.set
    order = (len(SETS) if a.file else list(SETS).index(a.set)) * 10 + (5 if a.model else 3 if a.openrouter else 2 if a.llm else 1 if a.replay else 0)  # 요약 줄 순서
    write_summary(out.parent / "summary.md", f"{label}·{mode}",
                  dict(score_row(res, hide), set=label, mode=mode, at=f"{time.strftime('%m-%d %H:%M')}", sec=secs(elapsed / max(len(preds), 1)),
                       version=f"조건 {CONDITIONS_VERSION} · 프롬프트 {PROMPT.PROMPT_VERSION if use_model or a.replay else '-'}"
                               f"{f' · 모델 {a.openrouter or a.model}' if a.openrouter or a.model else ''}", report=rep.name, order=order))
    failed = failed_n if use_model else 0  # 다시 불러도 실패한 메일은 분류 실패(할 일 없음)로 남아 모델 점수가 낮게 보일 수 있다
    print(f"{len(preds)}건 · {'모델' if a.openrouter or a.model else '엑사원'} 대상 {routed}건 · 완전 정답 {res['full']}/{res['n']} · "
          f"Task 재현율 {pct(res['bin']['Task 여부'][1])} · 놓친 Task 메일 {res['bin']['Task 여부'][3]}건"
          f"{f' · replay 캐시 없음 {llm.misses}건' if a.replay else ''}"
          f"{f' · {llm.inner.cost_text()}' if a.openrouter else ''}"
          f"{f' · 알림: 응답 형식 낮춤({llm.inner.format_text()})' if a.openrouter and llm.inner.format_changes else ''}"
          f"{f' · 경고: 다시 불러도 분류 실패 {failed}통(1차 {first_failed}통, 보고서 끝 참고)' if failed else ''} → {rep}")
    day = getattr(getattr(llm, "inner", None), "day_limit", None)
    if day and day.get("limit"):  # 엑사원 API 하루 한도(응답 머리글) — 키를 나눠 쓸 때 다음 실행을 어느 키로 할지 본다(DE-D24)
        print(f"하루 한도: {day['limit']}회 중 {day['remaining']}회 남음")

if __name__ == "__main__":
    main()
