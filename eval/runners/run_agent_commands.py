"""명령 테스트 세트(eval/datasets/agent_commands_v1.jsonl)로 명령 해석을 채점한다 (AI detail 7절, AI-14).

사용 (레포 루트에서):
  ai/.venv/bin/python eval/runners/run_agent_commands.py          # 규칙만
  ai/.venv/bin/python eval/runners/run_agent_commands.py --llm    # 규칙 + 엑사원 (ollama 필요)

채점: 행동 ID 일치 + expected에 적힌 target · params 칸 일치. confirm(확인창 여부)은 backend 규칙이 정하므로 여기서 채점하지 않는다.
"""
import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ai"))

from app.agent.plan import plan  # noqa: E402
from app.agent.rules_v1 import RULES_VERSION  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.llm.client import build_client  # noqa: E402
from app.prompts.agent_v1 import PROMPT_VERSION, load_examples  # noqa: E402
from app.schemas.agent import ActionSpec, PlanContext, PlanRequest  # noqa: E402

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
    for part in ("target", "params"):
        for k, v in (expected.get(part) or {}).items():
            if got[part].get(k) != v:
                wrong.append(f"{part}.{k} {v}→{got[part].get(k)}")
    return wrong


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    a = ap.parse_args()
    llm = build_client(replace(get_settings(), llm_enabled=a.llm))

    rows = [json.loads(ln) for ln in DATASET.read_text(encoding="utf-8").splitlines() if ln.strip()]
    overlap = {r["text"] for r in rows} & {e["text"] for e in load_examples()}
    lines, ok, by_type, times, stats = [], 0, {}, {"rule": [], "model": []}, []
    for r in rows:
        ctx = PlanContext(now=r["now"], selected_mail_ids=r.get("selected_mail_ids", []), last_result_ids=r.get("last_result_ids", []))
        t0 = time.perf_counter()
        res = plan(PlanRequest(text=r["text"], actions=ACTIONS, context=ctx), llm)
        times[res.source].append(time.perf_counter() - t0)
        if res.source == "model" and getattr(llm, "last_stats", None):
            stats.append(llm.last_stats)  # 입력 읽기 · 출력 생성 시간 내역(ollama)
        got = json.loads(res.model_dump_json())
        wrong = check(r["expected"], got)
        ok += not wrong
        s = by_type.setdefault(r["type"], [0, 0])
        s[0] += not wrong
        s[1] += 1
        if wrong:
            lines.append(f"| {r['id']} | {r['text']} | {r['type']} | {res.source} | {' · '.join(wrong)} |")

    avg = {k: (sum(v) / len(v) * 1000 if v else 0) for k, v in times.items()}
    md = [f"# 명령 해석 채점 · {DATASET.name}", "",
          f"- 버전: 규칙 {RULES_VERSION} · 프롬프트 {PROMPT_VERSION if a.llm else '미사용'} · 모델 {llm.model if a.llm else '미사용(규칙만)'}",
          f"- 예시 세트와 겹치는 문장: {len(overlap)}건 (0이어야 한다)",
          f"- **행동 · 대상 · 인자 모두 일치: {ok}/{len(rows)}**",
          f"- 평균 응답 시간: 규칙 경로 {avg['rule']:.1f}ms ({len(times['rule'])}건) · 모델 경로 {avg['model']:.1f}ms ({len(times['model'])}건)",
          *([f"- 모델 경로 시간 내역(평균): 입력 {sum(x['prompt_tokens'] for x in stats) / len(stats):.0f}토큰 · "
              f"{sum(x['prompt_s'] for x in stats) / len(stats):.1f}초 / 출력 {sum(x['gen_tokens'] for x in stats) / len(stats):.0f}토큰 · "
              f"{sum(x['gen_s'] for x in stats) / len(stats):.1f}초 / 로딩 {sum(x['load_s'] for x in stats) / len(stats):.1f}초"] if stats else []),
          "", "| 유형 | 일치 |", "|---|---|", *[f"| {k} | {v[0]}/{v[1]} |" for k, v in by_type.items()],
          "", "## 틀린 항목", "", "| ID | 지시 | 유형 | 경로 | 틀린 칸 (기대→결과) |", "|---|---|---|---|---|", *lines]
    out = ROOT / "eval/reports" / f"agent_commands_{'llm' if a.llm else 'rule'}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"{ok}/{len(rows)} 일치 · 예시와 겹침 {len(overlap)}건 → {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
