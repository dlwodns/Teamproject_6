"""메일 요약 품질(DE-6) — ai `/summarize` mode=mail(요지 · 나에게 요청한 것 · 기한 문구)을 우리 정답으로 잰다.

코드 채점(정답이 있는 칸):
- 요청 찾음: 정답에 할 일이 있는 메일에서 asks가 1개 이상
- 요청 더 냄: 정답에 할 일이 없는 메일에서 asks가 1개 이상(지어낸 요청일 수 있다 — 판정에서 다시 본다)
- 요청 수 같음: asks 수 = 정답 할 일 수(할 일 메일)
- 기한 문구 맞음: 정답 할 일에 기한 원문이 있는 메일에서 due_text가 그 원문과 겹침(공백 · 끝의 '까지 · 중 · 내로 · 이내'를 빼고
  한쪽이 다른 쪽에 들어 있으면). 표현이 달라도 같은 날인 경우는 판정에서 본다
- 요약 실패: 모델이 요약하지 못해 코드 요약(한국어) 또는 빈 요약(외국어)이 된 메일
판정(--judge, 참고값): 판정자 모델(오픈라우터 Claude Haiku, DE-D29와 같은 판정자)이 메일 · 정답 할 일 · 요약을 보고
좋음 · 부족 · 틀림을 매긴다. 판정 캐시로 같은 요약은 다시 부르지 않는다.

사용(레포 루트, ai/.venv 파이썬):
  python eval/runners/run_mail_summary.py --set dev4 --llm --mask                     # 엑사원 API(메일 1통 1회)
  python eval/runners/run_mail_summary.py --set dev9 --or deepseek/deepseek-v4.1-flash --mask --judge
  python eval/runners/run_mail_summary.py --file <봉인 폴더>/testA_mails.json --llm --mask   # 봉인: 개수만
  python eval/runners/run_mail_summary.py --set dev4 --mask                           # 모델 없이 코드 요약만(점검용)
결과: eval/reports/summary_<세트>_<모델>[_mask].json(메일마다 요약 · 시간) · .md(보고서) · 판정 캐시.
봉인 세트는 세트 폴더(레포 밖)에 남기고, 보고서에 메일 번호 · 문장을 적지 않는다(plan 8.5절).
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai"))
sys.path.insert(0, str(ROOT / "data/dummy"))

from app.agent import assist  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.llm.client import LLMError, build_client  # noqa: E402
from app.schemas.assist import MailInput, SummarizeRequest  # noqa: E402
from eval import is_sealed, received  # noqa: E402  data/dummy/eval.py
from openrouter_client import OpenRouterClient, load_key  # noqa: E402  평가 전용 오픈라우터(DE-D24)
import pii_mask  # noqa: E402  서비스와 같은 개인정보 가리기(BE-6 · #94)

JUDGE_MODEL = "anthropic/claude-haiku-5.5"
VERDICTS = ("좋음", "부족", "틀림")
JUDGE_VERSION = "judge_summary_v1"
JUDGE_SYSTEM = """너는 업무 메일 요약을 채점한다. 메일 원문, 사람이 정한 정답 할 일(없을 수 있음), 요약기가 낸 요약
(요지 · 나에게 요청한 것 · 기한 문구)을 보고 셋 중 하나를 고른다.
- 좋음: 요지가 메일의 핵심(무엇에 관한 메일인지, 나에게 바라는 것이 있으면 그것)을 담았고 사실과 다른 내용이 없다.
  정답 할 일이 있으면 그 요청이 '나에게 요청한 것'이나 요지에 들어 있다.
- 부족: 틀린 내용은 없지만 정답 할 일(요청)이나 그 기한이 빠졌거나, 요지가 핵심을 놓쳤다.
- 틀림: 메일에 없는 내용, 사실과 다른 숫자 · 날짜 · 사람이 있거나, 다른 사람에게 한 요청 · 정답에 없는 요청을 내 요청으로 적었다.
보지 않는 것: 문장 다듬기 · 길이 · 말투 · 요청을 나눈 개수. 기한 문구는 원문 표현이 달라도 같은 때를 가리키면 맞다.
정답 할 일이 없는 메일은 '나에게 요청한 것'이 비어 있어야 좋음이다(공지 속 일반 안내는 요청이 아니다).
JSON 하나만: {"verdict": "좋음" | "부족" | "틀림", "reason": "한 문장"}"""
JUDGE_SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string", "enum": list(VERDICTS)}, "reason": {"type": "string"}},
                "required": ["verdict", "reason"]}


def norm_due(x: str | None) -> str:
    """기한 문구 비교용: 공백과 끝의 조사성 낱말을 뺀다(예: '10/23(금)까지' → '10/23(금)')."""
    s = re.sub(r"\s+", "", x or "")
    return re.sub(r"(까지|중으로|중|내로|이내|안으로)$", "", s)


def due_match(gold_raws: list[str], due_text: str | None) -> bool:
    d = norm_due(due_text)
    return bool(d) and any(len(g := norm_due(r)) >= 2 and (g in d or d in g) for r in gold_raws)


def person_label(data: dict, addr: str) -> str | None:
    """보낸 사람 표기(backend가 넘길 '이름 직급' 모양). 사람 목록에 없으면 주소."""
    for p in data["people"].values():
        if p.get("email") == addr:
            return " ".join(x for x in (p.get("name"), p.get("position")) if x) or addr
    return addr


def judge_text(m: dict, gold_tasks: list[dict], ms: dict | None) -> str:
    tasks = "\n".join(f"- {t['action']} (기한 원문: {t.get('due_raw') or '없음'})" for t in gold_tasks) or "없음"
    if not ms:
        summ = "(요약 없음)"
    else:
        summ = (f"요지: {ms['gist']}\n나에게 요청한 것: {' / '.join(ms['asks']) or '없음'}\n기한 문구: {ms.get('due_text') or '없음'}")
    return f"제목: {m['subject']}\n본문:\n{m['body']}\n\n[정답 할 일]\n{tasks}\n\n[요약]\n{summ}"


def run_judge(rows: list[dict], gold: dict, mails: dict, cache_file: Path, model: str, client=None) -> tuple[Counter, int]:
    cache = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.is_file() else {}
    client = client or OpenRouterClient(model, load_key())
    c, called = Counter(), 0
    for x in rows:
        text = judge_text(mails[x["id"]], gold[x["id"]], x["summary"])
        key = hashlib.sha256(f"{JUDGE_VERSION}|{model}|{text}".encode()).hexdigest()[:24]
        if key not in cache:
            try:
                out = client.chat_json(JUDGE_SYSTEM, text, JUDGE_SCHEMA)
                v = out.get("verdict")
                if v not in VERDICTS:
                    raise LLMError(f"판정 형식 오류: {v!r}")
                cache[key] = {"verdict": v, "reason": str(out.get("reason", ""))[:200]}
                called += 1
            except LLMError as e:  # 실패는 캐시에 남기지 않는다(다음 실행에서 다시 부른다)
                x["judge"] = {"verdict": "판정 실패", "reason": str(e)[:120]}
                c["판정 실패"] += 1
                continue
        x["judge"] = cache[key]
        c[cache[key]["verdict"]] += 1
    cache_file.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return c, called


def main(argv=None, llm=None, judge_client=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="dev4", help="개발 세트 이름(run_dummy와 같음)")
    ap.add_argument("--file", type=Path, default=None, help="레포 밖 봉인 세트 파일(결과는 그 옆에)")
    ap.add_argument("--llm", action="store_true", help="엑사원(LLM_BACKEND, 기본 엑사원 API)")
    ap.add_argument("--or", dest="openrouter", default=None, help="오픈라우터 모델(DE-D24, eval 전용)")
    ap.add_argument("--mask", action="store_true", help="서비스처럼 이름 · 메일 주소 · 전화번호를 가려 보내고 요약을 되돌린다(BE-6)")
    ap.add_argument("--judge", action="store_true", help="판정자 모델로 좋음 · 부족 · 틀림(참고값, 오픈라우터 키 필요)")
    ap.add_argument("--judge-model", default=JUDGE_MODEL)
    a = ap.parse_args(argv)

    from run_dummy import SETS  # 세트 이름 → 파일(run_dummy와 같은 표)
    src = a.file.expanduser().resolve() if a.file else ROOT / "data/dummy" / SETS[a.set]
    data = json.loads(src.read_text(encoding="utf-8"))
    hide = is_sealed(src)
    if hide and not a.file:
        sys.exit("봉인 세트는 --file로만 잰다")
    settings = get_settings()
    use_model = bool(a.llm or a.openrouter)
    if llm is None:
        llm = (OpenRouterClient(a.openrouter, load_key(), settings.llm_timeout_s) if a.openrouter
               else build_client(replace(settings, llm_enabled=a.llm)))
    if a.openrouter:
        tag = "or-" + re.sub(r"[^A-Za-z0-9.]+", "-", a.openrouter).strip("-")
    elif not a.llm:
        tag = "code"
    elif settings.llm_backend == "exaone_api":
        tag = f"api-{llm.model}" + (f"@{settings.exaone_reasoning_effort}" if settings.exaone_reasoning_effort not in ("", "max") else "")
    else:
        tag = "llm"
    stem = src.stem.removesuffix("_mails")
    folder = src.parent if a.file else ROOT / "eval/reports"
    out = folder / f"summary_{stem}_{tag}{'_mask' if a.mask else ''}.json"
    if hide and out.resolve().is_relative_to(ROOT):
        sys.exit("봉인 세트 결과는 레포 밖(세트 폴더)에만 남긴다")

    Masker = pii_mask.load_masker() if a.mask else None
    names = pii_mask.names_of(data) if a.mask else []
    gold, mails, rows = {}, {}, []
    items = received(data)
    for n, o in enumerate(items):
        m = o["mail"]
        gold[m["id"]], mails[m["id"]] = o["gold"].get("tasks", []), m
        mi = MailInput(subject=m["subject"], body=m["body"], sender=person_label(data, m["from"]))
        mk = Masker(names) if Masker else None
        if mk:
            mi = MailInput(**mk.mask_obj(mi.model_dump()))
        req = SummarizeRequest(mode="mail", now=m["received_at"], mail=mi, use_model=use_model)
        t0 = time.perf_counter()
        r = assist.summarize(req, llm)
        secs = round(time.perf_counter() - t0, 2)
        if "한도 소진" in (r.fallback or ""):  # summarize는 모델 실패를 코드 요약으로 삼키므로 한도 소진은 여기서 멈춘다
            sys.exit(f"{r.fallback}\n{n}/{len(items)}통에서 멈췄다. 한도가 풀리거나 키를 바꾼 뒤 다시 실행한다")
        ms = r.mail_summary.model_dump() if r.mail_summary else None
        left = 0
        if ms and mk:
            ms = mk.unmask_obj(ms)
            left = Masker.leftover(ms)
        rows.append({"id": m["id"], "source": r.source, "fallback": r.fallback, "summary": ms, "s": secs,
                     "chars": len(m["body"]), "leftover": left})
        if use_model and ((n + 1) % 10 == 0 or n + 1 == len(items)):
            print(f"  {n + 1}/{len(items)}통", flush=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")  # 보고서보다 먼저 남긴다

    # 코드 채점
    task_rows = [x for x in rows if gold[x["id"]]]
    none_rows = [x for x in rows if not gold[x["id"]]]
    asks = lambda x: (x["summary"] or {}).get("asks") or []  # noqa: E731
    due_rows = [x for x in task_rows if any(t.get("due_raw") for t in gold[x["id"]])]
    found = [x for x in task_rows if asks(x)]
    extra = [x for x in none_rows if asks(x)]
    same_n = [x for x in task_rows if len(asks(x)) == len(gold[x["id"]])]
    due_has = [x for x in due_rows if (x["summary"] or {}).get("due_text")]
    due_ok = [x for x in due_rows if due_match([t["due_raw"] for t in gold[x["id"]] if t.get("due_raw")], (x["summary"] or {}).get("due_text"))]
    nodue_extra = [x for x in rows if x not in due_rows and (x["summary"] or {}).get("due_text")]
    failed = [x for x in rows if use_model and (x["source"] != "exaone" or not x["summary"])]
    langs = Counter((x["summary"] or {}).get("lang", "요약 없음") for x in rows)
    gl = [len(x["summary"]["gist"]) for x in rows if x["summary"]]
    ts = sorted(x["s"] for x in rows)
    q = lambda f: ts[min(len(ts) - 1, int(f * len(ts)))]  # noqa: E731
    pct = lambda a_, b_: f"{a_}/{b_}" + (f" ({a_ / b_ * 100:.1f}%)" if b_ else "")  # noqa: E731

    jc, called = Counter(), 0
    if a.judge:
        jc, called = run_judge(rows, gold, mails, out.with_name(f"judge_cache_{out.stem}.json"), a.judge_model, judge_client)
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")

    model_name = a.openrouter or (llm.model if a.llm else "미사용(코드 요약)")
    md = [f"# 메일 요약 채점(DE-6) · {src.name}", "",
          f"- 버전: 프롬프트 {assist.prompts.PROMPT_VERSION if use_model else '미사용'} · 모델 {model_name}"
          f"{' (오픈라우터, 평가 전용 DE-D24)' if a.openrouter else ''} · 데이터 {data['meta']['version']} · "
          f"{'개인정보 가림(BE-6) · ' if a.mask else ''}{time.strftime('%Y-%m-%d %H:%M')}"
          + (" · 봉인 세트: 메일 번호 · 문장 없이 개수만" if hide else ""),
          f"- 받은 메일 {len(rows)}통(할 일 있음 {len(task_rows)} · 없음 {len(none_rows)}) · 요약 실패(코드 요약 · 빈 요약) {len(failed)}통"
          + (f" · 되돌리지 못한 대체어 {sum(x['leftover'] for x in rows)}개" if a.mask else ""),
          f"- 메일 1통 처리 시간: 중앙 {q(0.5):.1f}초 · 90% {q(0.9):.1f}초 · 최대 {ts[-1]:.1f}초"
          + (f" · {llm.cost_text()}" if a.openrouter else ""),
          f"- 원문 언어(코드 판별): {' · '.join(f'{k} {v}' for k, v in langs.most_common())} · 요지 길이 평균 {sum(gl) / max(len(gl), 1):.0f}자 · 최대 {max(gl, default=0)}자",
          "", "| 칸 | 값 | 뜻 |", "|---|---|---|",
          f"| 요청 찾음 ↑ | **{pct(len(found), len(task_rows))}** | 정답에 할 일이 있는 메일에서 '나에게 요청한 것'이 1개 이상 |",
          f"| 요청 더 냄 ↓ | {pct(len(extra), len(none_rows))} | 정답에 할 일이 없는 메일에서 요청을 냄(지어냄일 수 있음) |",
          f"| 요청 수 같음 | {pct(len(same_n), len(task_rows))} | 요청 개수 = 정답 할 일 개수 |",
          f"| 기한 문구 있음 · 맞음 ↑ | {len(due_has)} · **{len(due_ok)}** / {len(due_rows)} | 정답 할 일에 기한 원문이 있는 메일. 맞음은 원문과 겹칠 때(표현이 다른 같은 날은 판정에서) |",
          f"| 기한 문구 더 냄 | {len(nodue_extra)}통 | 정답에 기한이 없는 메일에서 기한 문구를 냄(행사 날짜 등 맞는 경우도 있음) |"]
    if a.judge:
        md += ["", f"## 판정(참고값, {a.judge_model}, {JUDGE_VERSION})", "",
               f"- {' · '.join(f'{v} {jc[v]}' for v in (*VERDICTS, '판정 실패') if jc[v])} / {len(rows)}통 · 새로 부른 판정 {called}회"]
    if not hide:
        md += ["", "## 다시 볼 메일", "", "| 메일 | 문제 | 요지 | 나에게 요청한 것 | 기한 문구 | 판정 |", "|---|---|---|---|---|---|"]
        for x in rows:
            why = []
            if x in task_rows and not asks(x):
                why.append("요청 없음")
            if x in none_rows and asks(x):
                why.append("요청 더 냄")
            if x in due_rows and x not in due_ok:
                why.append("기한 다름" if (x["summary"] or {}).get("due_text") else "기한 없음")
            if x in failed:
                why.append(f"요약 실패({(x['fallback'] or '')[:30]})")
            j = x.get("judge") or {}
            if j.get("verdict") in ("부족", "틀림", "판정 실패"):
                why.append(f"판정 {j['verdict']}")
            if why:
                s = x["summary"] or {}
                cell = lambda v: str(v).replace("|", "/").replace("\n", " ")[:120]  # noqa: E731
                md.append(f"| {x['id']} | {' · '.join(why)} | {cell(s.get('gist', '—'))} | {cell(' / '.join(s.get('asks') or []) or '—')} "
                          f"| {cell(s.get('due_text') or '—')} | {cell((j.get('verdict', '') + ' ' + j.get('reason', '')).strip() or '—')} |")
    rep = out.with_suffix(".md")
    rep.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"{len(rows)}통 · 요청 찾음 {len(found)}/{len(task_rows)} · 요청 더 냄 {len(extra)}/{len(none_rows)} · 기한 맞음 {len(due_ok)}/{len(due_rows)}"
          f" · 요약 실패 {len(failed)}" + (f" · 판정 {dict(jc)}" if a.judge else "") + f" → {rep}")
    if getattr(llm, "day_limit", None) and a.llm:
        print(f"하루 한도: {llm.day_limit}")
    return rows


if __name__ == "__main__":
    main()
