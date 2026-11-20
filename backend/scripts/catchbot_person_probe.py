"""캐치봇 '누가 뭐라고 했지' 시나리오 점검(AI-44) — 실제 서버(POST /api/agent/command)에 질문을 보내 기대와 비교한다.

    python scripts/catchbot_person_probe.py --dry          # 시나리오만 출력(호출 없음)
    python scripts/catchbot_person_probe.py                # 전부 실행(엑사원 API 1회씩)
    python scripts/catchbot_person_probe.py --only P1,P7   # 일부만

- 기대값은 11-20 시험 메일함(문규남 계정, 메일 36~47)을 기준으로 적었다. 메일함이 바뀌면 SCENARIOS를 고친다.
- 엑사원 API는 하루 100회 한도라 시작 전에 ai `/health`의 남은 횟수를 보고, 시나리오 수 + --reserve보다 적으면 멈춘다.
  남은 횟수는 ai가 엑사원을 한 번 부른 뒤에야 알 수 있다(서버를 막 띄웠으면 None — 그대로 진행).
- 답 모양(executor._person): 사람을 찾으면 kind=person — person.mails = 쓴 메일, mails = 이름이 나온 메일.
  쓴 메일이 없는 이름 · 본인은 kind=query — mails = 이름이 나온 메일. 그 밖의 행동(T19 메일 찾기)은 mails = 찾은 메일.
- 결과는 표준 출력과 --out JSON에 남는다.
"""
import argparse
import json
import sys
import time

import httpx

BACKEND = "http://localhost:8000"
AI = "http://localhost:8001"

# id, 질문, 고른 메일, 기대: kind(하나 또는 여럿) · wrote(쓴 메일) · mentioned(이름이 나온 메일) · task_mails(업무가 나온 메일) · has(답에 들어갈 글자)
SCENARIOS = [
    ("P1", "임소희 책임이 나한테 뭐라고 했었지", [], {"kind": "person", "wrote": {41, 42, 43}, "mentioned": set()}),
    ("P2", "모정훈 과장이 보낸 메일 보여줘", [], {"kind": ("person", "query"), "wrote": {39}}),
    ("P3", "정태성 담당님이 누구였지", [], {"kind": "person", "wrote": {45}, "mentioned": {37, 42}}),
    ("P4", "문가영 책임 얘기 나온 메일 있어?", [], {"kind": "query", "wrote": set(), "mentioned": {42}}),  # 43은 인용된 앞 메일에만 나온다
    ("P5", "김민석 팀장이 나한테 뭐라고 했었지", [], {"kind": "query", "wrote": set(), "mentioned": {39, 40, 42}}),
    ("P6", "임 책임이 뭐라고 했지", [], {"kind": "person", "wrote": {41, 42, 43}}),  # 성 + 직급
    ("P7", "소희 책임이 뭐라고 했어", [], {"kind": "person", "wrote": {41, 42, 43}}),  # 이름만
    ("P8", "임소희가 뭐라고 했었지", [], {"kind": "person", "wrote": {41, 42, 43}}),  # 직급 없음
    ("P9", "Ethan Marlow가 뭐라고 했어?", [], {"kind": "person", "wrote": {47}}),  # 영문 이름(아직 안 함)
    ("P11", "황인성 책임이 요청한 업무 뭐야", [], {"task_mails": {40}}),
    ("P12", "이 메일 보낸 사람 누구야", [41], {"kind": "person", "has": "임소희"}),  # 고른 메일을 쓴 사람(공용 주소)
    ("P13", "보완본 재제출 누가 요청했었지", [], {"has": "임소희"}),  # 내용 → 사람
    ("P14", "BP사 인력 연장 건 누가 뭐라고 했었지", [], {"has": "임소희"}),
    ("P15", "어떤 업무 누가 뭐라고 했었지", [], {"kind": "ask"}),  # 대상 없음 → 되묻기
    ("P16", "홍길동 부장이 뭐라고 했었지", [], {"kind": "empty"}),  # 없는 사람
    ("P17", "문규남 팀장이 뭐라고 했지", [], {"has": "본인"}),  # 나 자신
]


def remaining() -> int | None:
    try:
        v = httpx.get(f"{AI}/health", timeout=10).json()["llm"]["day_limit"]["remaining"]
        return None if v is None else int(v)
    except (httpx.HTTPError, KeyError, ValueError):
        return None


def sets(r: dict) -> tuple[set[int], set[int]]:
    """(쓴 메일, 이름이 나온 메일) — 맨 위 docstring의 답 모양대로."""
    mails = {m["mail_id"] for m in r.get("mails") or []}
    if r.get("person"):
        return {m["mail_id"] for m in r["person"].get("mails") or []}, mails
    if "이름이 나온" in r.get("title", "") or "본인" in r.get("title", ""):
        return set(), mails
    return mails, set()


def check(r: dict, exp: dict) -> list[str]:
    bad = []
    kinds = exp.get("kind")
    if kinds and r.get("kind") not in ((kinds,) if isinstance(kinds, str) else kinds):
        bad.append(f"kind {r.get('kind')} ≠ {kinds}")
    wrote, mentioned = sets(r)
    if "wrote" in exp and wrote != exp["wrote"]:
        bad.append(f"쓴 메일 {sorted(wrote)} ≠ {sorted(exp['wrote'])}")
    if "mentioned" in exp and mentioned != exp["mentioned"]:
        bad.append(f"이름이 나온 메일 {sorted(mentioned)} ≠ {sorted(exp['mentioned'])}")
    if "task_mails" in exp:
        got = {t["mail_id"] for t in r.get("targets") or []}
        if got != exp["task_mails"]:
            bad.append(f"업무의 메일 {sorted(got)} ≠ {sorted(exp['task_mails'])}")
    text = " ".join([r.get("title", ""), *r.get("notes", []), *(r.get("lines") or []),
                     json.dumps(r.get("person") or {}, ensure_ascii=False), *(m["who"] for m in r.get("mails") or [])])
    if "has" in exp and exp["has"] not in text:
        bad.append(f"'{exp['has']}' 없음")
    return bad


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--user", type=int, default=None, help="X-User-Id(dev 모드는 비우면 기본 사용자)")
    ap.add_argument("--reserve", type=int, default=10, help="분류 작업자 몫으로 남길 엑사원 호출 수")
    ap.add_argument("--out", default="catchbot_probe_result.json")
    a = ap.parse_args()
    picked = [s for s in SCENARIOS if not a.only or s[0] in a.only.split(",")]
    if a.dry:
        for sid, text, sel, exp in picked:
            print(sid, text, f"(고른 메일 {sel})" if sel else "", exp)
        return
    left = remaining()
    print(f"엑사원 API 남은 호출: {left} · 쓸 호출: 최대 {len(picked)}")
    if left is not None and left < len(picked) + a.reserve:
        raise SystemExit(f"남은 호출이 {len(picked) + a.reserve}회보다 적어 멈춥니다(--reserve로 조정)")
    headers = {"X-User-Id": str(a.user)} if a.user else {}
    rows = []
    for sid, text, sel, exp in picked:
        t0 = time.monotonic()
        try:
            res = httpx.post(f"{BACKEND}/api/agent/command", headers=headers, timeout=400,
                             json={"text": text, "selected_mail_ids": sel})
            r = res.json() if res.status_code == 200 else {"kind": f"HTTP {res.status_code}", "title": res.text[:200]}
        except httpx.HTTPError as e:
            r = {"kind": "error", "title": str(e)}
        sec = round(time.monotonic() - t0, 1)
        bad = check(r, exp)
        wrote, mentioned = sets(r)
        rows.append({"id": sid, "text": text, "selected": sel, "sec": sec, "ok": not bad, "problems": bad,
                     "action": r.get("action"), "kind": r.get("kind"), "title": r.get("title"), "notes": r.get("notes"),
                     "wrote": sorted(wrote), "mentioned": sorted(mentioned), "who": [(m["mail_id"], m["who"]) for m in r.get("mails") or []],
                     "task_mails": sorted({t["mail_id"] for t in r.get("targets") or []}), "lines": r.get("lines")})
        print(f"{'OK ' if not bad else 'NG '} {sid} {sec:>5}s {r.get('action')}/{r.get('kind')} | {text}\n"
              f"      → {r.get('title')}" + (f"\n      ✗ {' · '.join(bad)}" if bad else ""), flush=True)
    json.dump(rows, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n{sum(x['ok'] for x in rows)}/{len(rows)} 통과 · 남은 호출 {remaining()} · 결과 {a.out}")


if __name__ == "__main__":
    main()
