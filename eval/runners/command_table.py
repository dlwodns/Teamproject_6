"""명령 해석 결과를 모델끼리 · 영역별로 맞대는 표(DE-10 · #172). 모델을 부르지 않는다.

run_agent_commands.py가 남긴 결과(<보고서>.results.json)를 모델마다 하나씩 받아
(1) 전체 표 (2) 영역별 표(사용자 목적 묶음, v5 예시 세트의 goal 이름) (3) 행동별 표 (4) 모든 모델이 틀린 문장을 만든다.

    python eval/runners/command_table.py --dataset eval/datasets/agent_commands_v4.jsonl \\
        "K-EXAONE 2.5=eval/reports/agent_commands_v4_api-k-exaone_v2.5.results.json" \\
        "Claude Haiku 5.5=eval/reports/agent_commands_v4_or-anthropic-claude-haiku-5.5.results.json" \\
        "DeepSeek V4.1 Flash=eval/reports/agent_commands_v4_or-deepseek-deepseek-v4.1-flash.results.json" --md /tmp/table.md

채점은 run_agent_commands.check 그대로다(행동 ID + expected의 reason · target · params). 결과 파일의 wrong을 쓰지 않고
지금 세트의 정답으로 다시 채점한다(정답을 고친 뒤에도 같은 결과로 다시 표를 만들 수 있게).
봉인 세트(agent_commands_v3 또는 --sealed)는 개수만 적는다(문장 번호 · 문장 없음).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_agent_commands import MUTATING, check  # noqa: E402  채점 · 위험한 오탐 기준을 측정기와 같게(ai 규칙 MUTATING)

# 영역 = 사용자 목적 묶음(v5 agent_commands_v5 goal G1 ~ G6 · G8 이름). v5에 없는 쓰기 · 설정 행동은 따로 묶는다
AREAS = [
    ("할 일 파악", {"T01", "T02"}),
    ("메일 찾기 · 내용 확인", {"T08", "T18", "T19", "T20"}),
    ("처리하기", {"T03", "T04", "T05", "T10", "T16"}),
    ("일정", {"T13", "T15"}),
    ("답 기다림 · 재촉", {"T06", "T14"}),
    ("사람", {"T17"}),
    ("쓰기 · 설정", {"T07", "T09", "T11", "T12"}),
]


def area_of(row: dict) -> str:
    if row.get("type") == "범위 밖":
        return "범위 밖 · " + ("되묻기" if row["expected"].get("reason") == "ambiguous" else "지원 외")
    act = row["expected"].get("action")
    return next((name for name, ids in AREAS if act in ids), "기타")


def frac(n: int, d: int) -> str:
    return f"{n}/{d}" if d else "—"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", help="'모델 이름=결과 파일(.results.json)'")
    ap.add_argument("--dataset", type=Path, default=ROOT / "eval/datasets/agent_commands_v4.jsonl")
    ap.add_argument("--sealed", action="store_true", help="문장 번호 · 문장을 적지 않는다(agent_commands_v3는 자동)")
    ap.add_argument("--md", type=Path, default=None, help="표를 이 파일에도 쓴다")
    a = ap.parse_args()
    dataset = a.dataset if a.dataset.is_absolute() else ROOT / a.dataset
    hide = a.sealed or dataset.stem == "agent_commands_v3"
    rows = {r["id"]: r for r in (json.loads(ln) for ln in dataset.read_text(encoding="utf-8").splitlines() if ln.strip())}

    runs = []
    for spec in a.runs:
        name, _, path = spec.partition("=")
        res = {e["id"]: e for e in json.loads(Path(path).read_text(encoding="utf-8"))}
        missing = set(rows) - set(res)
        if missing:  # 반쪽 결과(한도에 걸려 멈춘 실행)로 표를 만들지 않는다
            sys.exit(f"{name}: 세트 {len(rows)}문장 중 {len(missing)}문장 결과가 없다 — run_agent_commands.py --resume으로 끝까지 잰 뒤 다시")
        runs.append((name, {i: (rows[i], res[i]["got"], check(rows[i]["expected"], res[i]["got"]), res[i].get("s"), res[i].get("fallback"))
                            for i in rows}))

    names = [n for n, _ in runs]
    md = [f"# 명령 해석 · 모델 맞대기 · {dataset.name} ({len(rows)}문장)", "",
          "- 채점: 행동 ID + 정답에 적힌 reason · target · params 칸(run_agent_commands.py와 같음). 위험한 오탐 = 정답이 실행 안 함 · 조회인데 상태를 바꾸는 행동",
          "", "## 전체", "",
          "| 모델 | 모두 일치 ↑ | 정상 행동 일치 · 완전 일치 ↑ | 정상인데 실행 안 함 ↓ | 범위 밖 거르기 · 이유까지 ↑ | 위험한 오탐 ↓ | 답 못 함(호출 실패 · 형식) ↓ | 1문장 처리 시간 중앙 · 90% · 최대 |",
          "|---|---|---|---|---|---|---|---|"]
    for name, rs in runs:
        v = list(rs.values())
        normal = [x for x in v if x[0].get("type") == "정상"]
        outside = [x for x in v if x[0].get("type") == "범위 밖"]
        danger = [x for x in v if x[1].get("action") in MUTATING and x[0]["expected"].get("action") not in MUTATING]
        ts = sorted(x[3] for x in v if x[3] is not None)
        q = lambda f: ts[min(len(ts) - 1, int(f * len(ts)))]  # noqa: E731  run_agent_commands와 같은 분위수
        md.append(f"| {name} | **{sum(not x[2] for x in v)}/{len(v)}** "
                  f"| {sum(x[1].get('action') == x[0]['expected'].get('action') for x in normal)} · {sum(not x[2] for x in normal)}/{len(normal)} "
                  f"| {sum(x[1].get('action') is None for x in normal)} "
                  f"| {sum(x[1].get('action') is None for x in outside)} · {sum(not x[2] for x in outside)}/{len(outside)} "
                  f"| {len(danger)} | {sum(bool(x[4]) for x in v)} "
                  f"| {q(0.5):.1f} · {q(0.9):.1f} · {ts[-1]:.1f}초 |" if ts else "| — |")

    order = [n for n, _ in AREAS] + ["기타", "범위 밖 · 지원 외", "범위 밖 · 되묻기"]
    areas = [k for k in order if any(area_of(r) == k for r in rows.values())]
    md += ["", "## 영역별 (완전 일치 · 괄호는 행동만 일치)", "",
           "영역은 사용자 목적 묶음(v5 예시 세트 goal): 할 일 파악 T01 · T02 / 메일 찾기 · 내용 확인 T08 · T18 · T19 · T20 / 처리하기 T03 · T04 · T05 · T10 · T16 / "
           "일정 T13 · T15 / 답 기다림 · 재촉 T06 · T14 / 사람 T17 / 쓰기 · 설정 T07 · T09 · T11 · T12. 범위 밖은 '거르고 이유까지 맞음'(괄호는 거르기만).", "",
           "| 영역 | 문장 | " + " | ".join(names) + " |", "|---|---|" + "---|" * len(names)]
    for k in areas:
        ids = [i for i, r in rows.items() if area_of(r) == k]
        cells = []
        for _, rs in runs:
            full = sum(not rs[i][2] for i in ids)
            act = sum(rs[i][1].get("action") == rows[i]["expected"].get("action") for i in ids)
            cells.append(f"{full}/{len(ids)} ({act})")
        md.append(f"| {k} | {len(ids)} | " + " | ".join(cells) + " |")

    acts = sorted({r["expected"].get("action") for r in rows.values() if r.get("type") == "정상"} - {None})
    md += ["", "## 행동별 (정상 명령, 완전 일치 · 괄호는 행동만 일치)", "",
           "| 행동 | 영역 | 문장 | " + " | ".join(names) + " |", "|---|---|---|" + "---|" * len(names)]
    for act in acts:
        ids = [i for i, r in rows.items() if r.get("type") == "정상" and r["expected"].get("action") == act]
        cells = [f"{sum(not rs[i][2] for i in ids)}/{len(ids)} ({sum(rs[i][1].get('action') == act for i in ids)})" for _, rs in runs]
        md.append(f"| {act} | {area_of(rows[ids[0]])} | {len(ids)} | " + " | ".join(cells) + " |")

    common = [i for i in rows if all(rs[i][2] for _, rs in runs)]
    md += ["", f"## 모든 모델이 틀린 문장 ({len(common)}개)", "",
           "모델보다 프롬프트 · 행동 설명 · 정답 쪽을 먼저 본다(DE-D25)."]
    if not hide and common:
        md += ["", "| ID | 지시 | 정답 | " + " | ".join(names) + " |", "|---|---|---|" + "---|" * len(names)]
        for i in common:
            e = rows[i]["expected"]
            want = e.get("action") or e.get("reason")
            got = [rs[i][1].get("action") or rs[i][1].get("reason") or "null" if rs[i][1].get("action") != e.get("action")
                   else " · ".join(rs[i][2]) for _, rs in runs]
            md.append(f"| {i} | {rows[i]['text'].replace('|', '/')} | {want} | " + " | ".join(got) + " |")
    text = "\n".join(md) + "\n"
    print(text)
    if a.md:
        a.md.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
