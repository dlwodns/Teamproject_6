"""docs/*/plan.md 작업 표 → GitHub 이슈 · 마일스톤 맞추기.

    python scripts/plan_sync.py          # 바뀔 것만 출력 (dry run)
    python scripts/plan_sync.py --apply  # 실제 반영 (gh 로그인 필요)

- 작업 번호(FE-3 등)가 제목에 든 이슈가 있으면 그 이슈를 쓴다. 없으면 만든다.
- 이 스크립트가 만든 이슈(본문에 plan-sync 표시)는 본문 · 담당 · 상태를 plan.md대로 고친다.
  담당이 [미정]이면 담당자는 건드리지 않는다(plan.md를 [미정]으로 바꿔도 해제되지 않음, 손으로 뺀다).
  사람이 만든 이슈는 레이블 · 마일스톤만 붙이고, plan.md가 완료인데 열려 있으면 닫는다.
- 마일스톤은 목표일로 고른다. P1 · P2처럼 날짜가 없으면 넣지 않는다.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = "dlwodns/Teamproject_6"
ROOT = Path(__file__).resolve().parent.parent
PLANS = {"PL": "10_planning", "FE": "20_frontend", "BE": "30_backend", "AI": "40_ai", "DE": "50_data_eval"}
# 이름 → GitHub 계정. 사람이 바뀌면 여기만 고친다.
LOGINS = {"문규남": "mungn0603-code", "이재운": "dlwodns", "임동하": "Limdongha-7751",
          "홍태겸": "Taegyeom03", "최수호": "sooho2638", "강예은": "kangdms6603-hub"}
# (마감 월, 일, 제목, due_on)
MILESTONES = [(11, 18, "11/18 첫 배포", "2026-11-18T14:59:59Z"),
              (11, 20, "11/20 발표자료 초안", "2026-11-20T14:59:59Z"),
              (11, 27, "11/27 코드 마감", "2026-11-27T14:59:59Z"),
              (11, 28, "11/28 IR Day", "2026-11-28T14:59:59Z")]
PART_COLORS = {"PL": "5319e7", "FE": "1d76db", "BE": "0e8a16", "AI": "d93f0b", "DE": "fbca04"}
ID_RE = re.compile(r"^[A-Z]{2,3}-\d+[a-z]?$")
APPLY = "--apply" in sys.argv


def gh(*args, input=None):
    out = subprocess.run(["gh", *args], input=input, capture_output=True, text=True, encoding="utf-8")
    if out.returncode:
        raise SystemExit(f"gh {' '.join(args[:3])} 실패: {out.stderr.strip()}")
    return out.stdout


def api(method, path, body=None):
    if not APPLY and method != "GET":
        print(f"  [dry] {method} {path} {json.dumps(body, ensure_ascii=False)[:160] if body else ''}")
        return {}
    args = ["api", "-X", method, f"repos/{REPO}/{path}"]
    if body is not None:
        args += ["--input", "-"]
    out = gh(*args, input=json.dumps(body) if body is not None else None)
    return json.loads(out) if out.strip() else {}


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse(part, folder):
    """plan.md 4절 작업 표의 행 → dict 목록."""
    rows, header = [], None
    for line in (ROOT / "docs" / folder / "plan.md").read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            header = None if not line.strip() else header
            continue
        c = cells(line)
        if "번호" in c and "작업" in c:
            header = c
        elif header and len(c) == len(header) and ID_RE.match(c[header.index("번호")]):
            row = dict(zip(header, c))
            row["part"], row["folder"] = part, folder
            rows.append(row)
    return rows


def done(status):
    # '구현'은 main에 들어간 것으로 본다. 브랜치에만 있으면 '구현(브랜치 …)'로 적혀 있다.
    s = status.strip("* ")
    return s.startswith(("완료", "병합")) or (s.startswith("구현") and "브랜치" not in s)


def milestone_for(due):
    if "반복" in due:
        return MILESTONES[2][2]
    m = re.search(r"(\d{1,2})/(\d{1,2})", due)
    if not m:
        return None
    md = (int(m[1]), int(m[2]))
    for mo, d, title, _ in MILESTONES:
        if md <= (mo, d):
            return title
    return MILESTONES[-1][2]


def logins(*fields):
    names = re.findall(r"[가-힣]{3}", " ".join(fields))
    return sorted({LOGINS[n] for n in names if n in LOGINS})


def title_of(row):
    text = re.sub(r"[*`]", "", row["작업"])
    short = re.split(r"[:(]|—", text)[0].strip()
    short = short if 4 <= len(short) <= 70 else text[:70].rstrip() + "…"
    return f"{row['번호']} {short}"


def body_of(row):
    keys = ["작업", "단계", "담당", "공동", "리뷰", "목표일", "상태", "끝났다고 보는 기준", "근거"]
    lines = [f"<!-- plan-sync:{row['번호']} -->",
             f"`docs/{row['folder']}/plan.md` 4절에서 옮겼다. 내용 · 상태는 plan.md가 기준이다.", ""]
    lines += [f"- **{k}**: {row[k]}" for k in keys if row.get(k) and row[k] not in ("—", "")]
    return "\n".join(lines) + "\n"


def main():
    rows = [r for p, f in PLANS.items() for r in parse(p, f)]
    print(f"plan.md 작업 {len(rows)}개")

    labels = {l["name"] for l in json.loads(gh("label", "list", "-R", REPO, "--limit", "200", "--json", "name"))}
    for part, color in PART_COLORS.items():
        if f"part:{part}" not in labels:
            api("POST", "labels", {"name": f"part:{part}", "color": color, "description": f"{part} 파트 작업"})

    ms = {m["title"]: m["number"] for m in api("GET", "milestones?state=all&per_page=100")}
    for _, _, title, due in MILESTONES:
        if title not in ms:
            ms[title] = api("POST", "milestones", {"title": title, "due_on": due}).get("number", f"<{title}>")

    issues = json.loads(gh("issue", "list", "-R", REPO, "--state", "all", "--limit", "500",
                           "--json", "number,title,body,state,labels,milestone,assignees"))

    for row in rows:
        tid = row["번호"]
        found = next((i for i in sorted(issues, key=lambda i: i["number"])
                      if re.search(rf"(?<![\w-]){re.escape(tid)}(?![\w-])", i["title"])), None)
        ms_title = milestone_for(row["목표일"])
        want = {"labels": [f"part:{row['part']}", "documentation" if row["part"] == "PL" else "enhancement"],
                "milestone": ms.get(ms_title) if ms_title else None}
        is_done = done(row["상태"])
        if found is None:
            print(f"+ {tid}: 새 이슈 ({ms_title}, {'닫음' if is_done else '열림'})")
            new = api("POST", "issues", {"title": title_of(row), "body": body_of(row),
                                         "assignees": logins(row["담당"], row.get("공동", "")), **want})
            if is_done and new.get("number"):
                api("PATCH", f"issues/{new['number']}", {"state": "closed", "state_reason": "completed"})
            continue
        n, patch = found["number"], {}
        have = {l["name"] for l in found["labels"]}
        if not set(want["labels"]) <= have:
            patch["labels"] = sorted(have | set(want["labels"]))
        # 한 이슈가 작업 여럿을 덮으면(#81 = FE-10 · FE-16) 늦은 마일스톤을 남긴다.
        order = [m[2] for m in MILESTONES]
        cur = (found["milestone"] or {}).get("title")
        if want["milestone"] and (cur not in order or order.index(ms_title) > order.index(cur)):
            patch["milestone"] = want["milestone"]
        if f"plan-sync:{tid}" in (found["body"] or ""):
            if found["body"] != body_of(row):
                patch["body"] = body_of(row)
            who = logins(row["담당"], row.get("공동", ""))
            # 담당이 [미정]이면 손으로 붙인 담당자를 지우지 않는다.
            if who and who != sorted(a["login"] for a in found["assignees"]):
                patch["assignees"] = who
        # 닫기만 한다. 코드로 확인하고 닫은 이슈를 plan.md 상태가 늦다고 다시 열지 않는다.
        if is_done and found["state"] == "OPEN":
            patch["state"] = "closed"
        if patch:
            print(f"~ {tid} → #{n}: {', '.join(patch)}")
            api("PATCH", f"issues/{n}", patch)


if __name__ == "__main__":
    main()
