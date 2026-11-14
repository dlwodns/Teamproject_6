"""명령 테스트 세트(eval/datasets/agent_commands_v1.jsonl)로 명령 해석을 채점한다 (AI detail 7절, AI-14).

사용 (레포 루트에서):
  ai/.venv/bin/python eval/runners/run_agent_commands.py          # 규칙만
  ai/.venv/bin/python eval/runners/run_agent_commands.py --llm    # 규칙 + 엑사원 (ollama 필요)

채점: 행동 ID 일치 + expected에 적힌 reason(지원 외 unsupported · 되묻기 ambiguous) · target · params 칸 일치.
confirm(확인창 여부)은 backend 규칙이 정하므로 여기서 채점하지 않는다.
위험한 오탐: 정답이 '실행 안 함'(null) · 조회 행동인데 상태를 바꾸는 행동(MUTATING)을 낸 건수. 0이어야 한다(BFCL '관련 없음' 지표를 본뜸).

type(정상 · 범위 밖)과 sub(정상은 행동 ID, 범위 밖은 지원 외 · 무관 · 지시 아님) 칸이 모든 줄에 있는 세트(v4~)는
보고서에 정상 행동별 표 · 범위 밖 거르기 표 · 위험한 오탐 목록 · 경로별 건수를 더 붙인다. 없는 세트는 기존 표만 낸다.
"""
import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai"))

from app.agent.plan import plan  # noqa: E402
from app.agent.rules_v1 import MUTATING, RULES_VERSION  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.llm.client import LLMError, build_client  # noqa: E402
from app.prompts.agent_v1 import PROMPT_VERSION, load_examples  # noqa: E402
from app.schemas.agent import ActionSpec, PlanContext, PlanRequest, PlanResponse  # noqa: E402

DATASET = ROOT / "eval/datasets/agent_commands_v1.jsonl"
# backend 행동 레지스트리와 같은 목록 (AI detail 2절)
ACTIONS = [ActionSpec(id=i, name=n) for i, n in [
    ("T01", "오늘_요약"), ("T02", "미처리_조회"), ("T03", "일괄_완료"), ("T04", "되돌리기"), ("T05", "나중에_처리"),
    ("T06", "무응답_확인"), ("T07", "회신_초안"), ("T08", "근거_설명"), ("T09", "리마인드_설정"), ("T10", "제외_처리"),
    ("T11", "중요_발신자_지정"), ("T12", "초안_작성"), ("T13", "기한_보기"), ("T14", "템플릿_전송")]]


def check(expected: dict, got: dict) -> list[str]:
    wrong = []
    if expected.get("action") != got["action"]:
        wrong.append(f"action {expected.get('action')}→{got['action']}")
    elif "reason" in expected and expected["reason"] != got.get("reason"):
        wrong.append(f"reason {expected['reason']}→{got.get('reason')}")
    for part in ("target", "params"):
        for k, v in (expected.get(part) or {}).items():
            if got[part].get(k) != v:
                wrong.append(f"{part}.{k} {v}→{got[part].get(k)}")
    return wrong


def pct(n: int, d: int) -> str:
    return f"{n}/{d} ({n / d * 100:.1f}%)" if d else "0/0"


def route(x: dict) -> str:
    """경로 이름. 규칙만 모드에서 모델로 갈 문장은 source=rule + fallback으로 돌아온다."""
    return x["source"] + (f" (fallback: {x['fallback']})" if x["fallback"] else "")


def extra_sections(results: list[dict], danger: list[str]) -> list[str]:
    """type(정상 · 범위 밖) · sub 칸이 있는 세트에만 붙이는 표 (a) 정상 (b) 범위 밖 (c) 위험한 오탐 (d) 경로."""
    normal = [x for x in results if x["row"]["type"] == "정상"]
    outside = [x for x in results if x["row"]["type"] == "범위 밖"]
    act_ok = [x for x in normal if x["got"]["action"] == x["row"]["expected"].get("action")]
    rejected = [x for x in normal if x["got"]["action"] is None]
    md = ["", f"## 정상 명령 ({len(normal)}문장)", "",
          f"- 행동 일치: {pct(len(act_ok), len(normal))}",
          f"- **행동 · 대상 · 인자 완전 일치: {pct(sum(not x['wrong'] for x in normal), len(normal))}**",
          f"- 정상 명령인데 실행 안 함(action null): {len(rejected)}건"
          + (f" ({' · '.join(f'{k} {v}' for k, v in Counter(route(x) + ' ' + str(x['got'].get('reason')) for x in rejected).items())})"
             if rejected else ""),
          "", "| 행동 | 문장 | 행동 일치 | 완전 일치 | 틀린 ID (나온 행동) |", "|---|---|---|---|---|"]
    for sub in sorted({x["row"]["sub"] for x in normal}):
        g = [x for x in normal if x["row"]["sub"] == sub]
        a_ok = sum(x["got"]["action"] == x["row"]["expected"].get("action") for x in g)
        bad = " ".join(f"{x['row']['id']}({x['got']['action'] or 'null'})" for x in g if x["wrong"])
        md.append(f"| {sub} | {len(g)} | {a_ok}/{len(g)} | {sum(not x['wrong'] for x in g)}/{len(g)} | {bad or '—'} |")

    blocked = [x for x in outside if x["got"]["action"] is None]
    md += ["", f"## 범위 밖 요청 ({len(outside)}문장)", "",
           f"- **거르기 성공(action null): {pct(len(blocked), len(outside))}**",
           f"- 그중 규칙이 직접 거름 {sum(not x['fallback'] for x in blocked)}건 · fallback으로 null {sum(bool(x['fallback']) for x in blocked)}건"
           " (규칙만 모드의 fallback null은 엑사원 판단이 아니라 모델을 부르지 않은 결과다)",
           f"- reason까지 일치: {pct(sum(not x['wrong'] for x in outside), len(outside))}",
           "", "| 구분 | 문장 | 거르기 성공 | reason 일치 | 실행해 버린 ID (행동) | 걸렀으나 reason 다른 ID |", "|---|---|---|---|---|---|"]
    for sub in dict.fromkeys(x["row"]["sub"] for x in outside):
        g = [x for x in outside if x["row"]["sub"] == sub]
        ran = " ".join(f"{x['row']['id']}({x['got']['action']})" for x in g if x["got"]["action"] is not None)
        diff = " ".join(x["row"]["id"] for x in g if x["got"]["action"] is None and x["wrong"])
        md.append(f"| {sub} | {len(g)} | {sum(x['got']['action'] is None for x in g)}/{len(g)} "
                  f"| {sum(not x['wrong'] for x in g)}/{len(g)} | {ran or '—'} | {diff or '—'} |")

    md += ["", f"## 위험한 오탐 ({len(danger)}건)", "",
           "정답이 실행 안 함 · 조회인데 상태 변경 · 설정 · 발송 행동을 낸 문장.", "",
           "| ID | 지시 | 구분 | 정답 | 결과 | 경로 |", "|---|---|---|---|---|---|"]
    for x in results:
        if x["row"]["id"] in danger:
            r = x["row"]
            md.append(f"| {r['id']} | {r['text']} | {r['type']} · {r['sub']} | {r['expected'].get('action') or 'null'} "
                      f"| {x['got']['action']} | {route(x)} |")

    md += ["", "## 경로별 건수", "", "| 경로 | 전체 | 정상 | 범위 밖 | 일치 |", "|---|---|---|---|---|"]
    for k in dict.fromkeys(route(x) for x in results):
        g = [x for x in results if route(x) == k]
        md.append(f"| {k} | {len(g)} | {sum(x['row']['type'] == '정상' for x in g)} "
                  f"| {sum(x['row']['type'] == '범위 밖' for x in g)} | {sum(not x['wrong'] for x in g)}/{len(g)} |")
    fb = [x for x in results if x["fallback"]]
    if fb:
        md.append(f"- fallback이 붙은 {len(fb)}건은 규칙이 행동 1개로 정하지 못해 모델 경로로 넘어갔거나(규칙 0개 · 2개 이상) 모델 호출이 실패한 문장이다.")
    return md


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--dataset", type=Path, default=DATASET, help="채점할 명령 세트(jsonl)")
    ap.add_argument("--out", type=Path, default=None, help="보고서 경로(기본: eval/reports/<세트>_<rule|llm>.md)")
    a = ap.parse_args()
    dataset = a.dataset if a.dataset.is_absolute() else ROOT / a.dataset
    llm = build_client(replace(get_settings(), llm_enabled=a.llm))

    rows = [json.loads(ln) for ln in dataset.read_text(encoding="utf-8").splitlines() if ln.strip()]
    overlap = {r["text"] for r in rows} & {e["text"] for e in load_examples()}
    has_sub = all(r.get("type") in ("정상", "범위 밖") and r.get("sub") for r in rows)
    lines, ok, by_type, times, stats, danger, results = [], 0, {}, {"rule": [], "model": []}, [], [], []
    for r in rows:
        ctx = PlanContext(now=r["now"], selected_mail_ids=r.get("selected_mail_ids", []), last_result_ids=r.get("last_result_ids", []))
        t0 = time.perf_counter()
        try:
            res = plan(PlanRequest(text=r["text"], actions=ACTIONS, context=ctx), llm)
        except LLMError as e:  # AI-D19: 모델이 못 고르면 규칙으로 메우지 않는다 → 행동 없음 · 실패 이유로 채점(오답)
            res = PlanResponse(action=None, source="model", reason=None, fallback=str(e), rules_version=RULES_VERSION)  # 이유 없음 = 어느 정답과도 맞지 않음
        times[res.source].append(time.perf_counter() - t0)
        if res.source == "model" and getattr(llm, "last_stats", None):
            stats.append(llm.last_stats)  # 입력 읽기 · 출력 생성 시간 내역(ollama)
        got = json.loads(res.model_dump_json())
        wrong = check(r["expected"], got)
        if got["action"] in MUTATING and r["expected"].get("action") not in MUTATING:
            danger.append(r["id"])
        x = {"row": r, "got": got, "wrong": wrong, "source": res.source, "fallback": res.fallback}
        results.append(x)
        ok += not wrong
        s = by_type.setdefault(r["type"], [0, 0])
        s[0] += not wrong
        s[1] += 1
        if wrong:
            lines.append(f"| {r['id']} | {r['text']} | {r['type']} | {route(x) if has_sub else res.source} | {' · '.join(wrong)} |")

    avg = {k: (sum(v) / len(v) * 1000 if v else 0) for k, v in times.items()}
    md = [f"# 명령 해석 채점 · {dataset.name}", "",
          f"- 버전: 규칙 {RULES_VERSION} · 프롬프트 {PROMPT_VERSION if a.llm else '미사용'} · 모델 {llm.model if a.llm else '미사용(규칙만)'}",
          f"- 예시 세트와 겹치는 문장: {len(overlap)}건 (0이어야 한다)",
          f"- **행동 · 대상 · 인자 모두 일치: {ok}/{len(rows)}**",
          f"- 위험한 오탐(실행 안 함 · 조회가 정답인데 상태 변경 행동): {len(danger)}건 {' '.join(danger)}",
          f"- 평균 응답 시간: 규칙 경로 {avg['rule']:.1f}ms ({len(times['rule'])}건) · 모델 경로 {avg['model']:.1f}ms ({len(times['model'])}건)",
          *([f"- 모델 경로 시간 내역(평균): 입력 {sum(x['prompt_tokens'] for x in stats) / len(stats):.0f}토큰 · "
              f"{sum(x['prompt_s'] for x in stats) / len(stats):.1f}초 / 출력 {sum(x['gen_tokens'] for x in stats) / len(stats):.0f}토큰 · "
              f"{sum(x['gen_s'] for x in stats) / len(stats):.1f}초 / 로딩 {sum(x['load_s'] for x in stats) / len(stats):.1f}초"] if stats else []),
          "", "| 유형 | 일치 |", "|---|---|", *[f"| {k} | {v[0]}/{v[1]} |" for k, v in by_type.items()]]
    if has_sub:
        md += extra_sections(results, danger)
    md += ["", "## 틀린 항목", "", "| ID | 지시 | 유형 | 경로 | 틀린 칸 (기대→결과) |", "|---|---|---|---|---|", *lines]
    out = a.out or ROOT / "eval/reports" / f"{'agent_commands' if dataset == DATASET else dataset.stem}_{'llm' if a.llm else 'rule'}.md"
    out = out if out.is_absolute() else ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"{ok}/{len(rows)} 일치 · 위험한 오탐 {len(danger)}건 · 예시와 겹침 {len(overlap)}건 → "
          f"{out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")


if __name__ == "__main__":
    main()
