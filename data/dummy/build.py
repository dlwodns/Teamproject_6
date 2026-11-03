# -*- coding: utf-8 -*-
"""더미 메일 생성기
people.py(가상 조직도) + mails.py(메일 정의) -> dummy_mails.json, mail_list.md
`python build.py test` 이면 mails_test.py(테스트셋) -> test_mails.json, test_mail_list.md
`python build.py dev2` 이면 mails_dev2.py(보조 개발셋) -> dev2_mails.json, dev2_mail_list.md
수정은 people.py / mails.py / mails_test.py에서 하고 다시 생성한다. 실행 시 검증 결과를 출력한다."""
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from people import P, DL, OWNER, SUPERIORS, FAVORITES, ADDR
from mails import MAILS

TEST = sys.argv[1:] == ["test"]
DEV2 = sys.argv[1:] == ["dev2"]
DEV3 = sys.argv[1:] == ["dev3"]
TEST3 = sys.argv[1:] == ["test3"]
if TEST:  # 테스트셋은 추가 인물만 덧붙인다(개발 세트 people은 그대로)
    from mails_test import MAILS, EXTRA, TARGET as TEST_TARGET
    P = {**P, **EXTRA}
if DEV2:  # 보조 개발셋도 같은 방식(추가 인물만 덧붙임)
    from mails_dev2 import MAILS, EXTRA, TARGET as DEV2_TARGET
    P = {**P, **EXTRA}
if DEV3:  # 독립 작성 세트 dev3(규칙 · 프롬프트를 보지 않은 별도 작성자). 같은 방식
    from mails_dev3 import MAILS, EXTRA, TARGET as DEV3_TARGET
    P = {**P, **EXTRA}
if TEST3:  # 봉인 시험 세트 test3(독립 작성자). 수정 작업 중에는 열지 않고 마지막에 1회만 채점한다
    from mails_test3 import MAILS, EXTRA, TARGET as TEST3_TARGET
    P = {**P, **EXTRA}

TYPE = {"자제": "자료제출요청", "수정": "수정재전송요청", "회요": "회신요청", "검승": "검토승인요청",
        "일정": "일정참석", "회신": "회신", "공지": "공지", "참조": "참조", "기타": "기타"}
TASK_TYPES = {"자료제출요청", "수정재전송요청", "회신요청", "검토승인요청", "일정참석"}
TARGET = {"자료제출요청": 16, "수정재전송요청": 10, "회신요청": 14, "검토승인요청": 8, "일정참석": 8,
          "회신": 8, "공지": 16, "참조": 14, "기타": 6}
TARGET = TEST_TARGET if TEST else DEV2_TARGET if DEV2 else DEV3_TARGET if DEV3 else TEST3_TARGET if TEST3 else TARGET
Y, OUT = "2026", Path(__file__).parent
VERSION, JSON_NAME, LIST_NAME = ("test-v1", "test_mails.json", "test_mail_list.md") if TEST else \
                                ("dev2-v1", "dev2_mails.json", "dev2_mail_list.md") if DEV2 else \
                                ("dev3-v1", "dev3_mails.json", "dev3_mail_list.md") if DEV3 else \
                                ("test3-v1", "test3_mails.json", "test3_mail_list.md") if TEST3 else \
                                ("v1", "dummy_mails.json", "mail_list.md")


def addr(k):
    return DL[k[1:]] if k.startswith("@") else P[k]["email"]


def ts(s):  # "10-21 18:00" -> "2026-10-21T18:00"
    return f"{Y}-{s[:5]}T{s[6:]}" if s else None


def greet(p):
    if p["external"]:
        return f"안녕하세요, {p['company']} {p['team']} {p['name']} {p['position']}입니다."
    if p["position"] in ("담당", "사업단장"):
        return f"안녕하세요, {p['name']}입니다."
    return f"안녕하세요 {p['team']} {p['name']} {p['position']}입니다."


def sign(p):
    bar = "*" * 46
    if p["external"]:
        rows = [f"{p['name']} {p['position']}".strip(), f"{p['company']} / {p['team']}"]
    else:
        rows = [f"{p['name']} {p['position']} / {p['name_en']}", " / ".join(p["org"])]
    rows += [f"E-Mail : {p['email']}", f"Phone : {p['phone']}"]
    if not p["external"]:
        rows.append(f"Address : {ADDR}")
    return "\n".join([bar, *rows, bar])


def priority(m, recv):  # 4-4 중요도 규칙. 상급자 또는 즐겨찾기 +30(중복 가산 없음)
    s = 30 if (m["frm"] in SUPERIORS or m["frm"] in FAVORITES) else 0
    dues = [datetime.fromisoformat(ts(t[3])) for t in m["tasks"] if t[3]]
    if dues:
        h = (min(dues) - recv).total_seconds() / 3600
        s += 30 if h <= 24 else 15 if h <= 72 else 0
    s += 15 if m["urgent"] else 0
    s += 20 if m["fu"] else 0
    s += 10 if OWNER in m["to"] else -10 if OWNER in m["cc"] else 0
    return "P1" if s >= 70 else "P2" if s >= 40 else "P3"


rows = sorted(MAILS, key=lambda m: (m["day"], m["t"]))
th_map, out = {}, []
for i, m in enumerate(rows, 1):
    p = P[m["frm"]]
    recv = datetime.fromisoformat(f"{Y}-{m['day']}T{m['t'][:2]}:{m['t'][2:]}")
    key = m["th"] or f"_single{i}"
    th_map.setdefault(key, f"T-{len(th_map) + 1:04d}")
    body = m["body"] if m["raw"] else f"{greet(p)}\n\n{m['body']}\n\n감사합니다.\n\n{sign(p)}"
    team = f"{p['company']} {p['team']}" if p["external"] else p["team"]
    sender = {"name": None, "position": None, "team": team} if m["raw"] else \
             {"name": p["name"], "position": p["position"], "team": team}
    men = m["men"] if m["men"] is not None else (bool(m["tasks"]) and OWNER in m["to"])
    out.append({
        "mail": {"id": f"M-{i:04d}", "thread_id": th_map[key],
                 "received_at": recv.isoformat(timespec="minutes"),
                 "from": p["email"], "is_vip": m["frm"] in FAVORITES,
                 "to": [addr(k) for k in m["to"]], "cc": [addr(k) for k in m["cc"]],
                 "subject": m["subj"], "body": body, "attachments": m["att"]},
        "gold": {"sender": sender,
                 "action_types": [TYPE[c] for c in m["types"].split()],
                 "mentioned_me": men,
                 "tasks": [{"action": a, "format": f, "due_raw": r, "due_at": ts(d)} for a, f, r, d in m["tasks"]],
                 "urgent": m["urgent"], "is_follow_up": m["fu"],
                 "priority": priority(m, recv), "tags": m["tags"]}})

# ---------- 검증 ----------
err = []
prim = Counter(o["gold"]["action_types"][0] for o in out)
for t, n in TARGET.items():
    if prim[t] != n:
        err.append(f"분포 불일치 {t}: {prim[t]}건 (목표 {n})")
for o in out:
    g, ml, pt = o["gold"], o["mail"], o["gold"]["action_types"][0]
    if pt in TASK_TYPES and not g["tasks"]:
        err.append(f"{ml['id']} 요청 유형인데 tasks 없음")
    if pt in {"회신", "참조", "기타"} and g["tasks"]:
        err.append(f"{ml['id']} Task 비생성 유형인데 tasks 있음")
    if pt == "공지" and g["tasks"] and not g["mentioned_me"]:
        err.append(f"{ml['id']} 공지 Task인데 개인 지목 없음")
    for t in g["tasks"]:
        if t["due_at"] and t["due_at"] < ml["received_at"]:
            err.append(f"{ml['id']} 마감이 수신 시각보다 이름")
        if bool(t["due_raw"]) != bool(t["due_at"]):
            err.append(f"{ml['id']} due_raw/due_at 짝 불일치")
    if ml["is_vip"] != (ml["from"] in [P[k]["email"] for k in FAVORITES]):
        err.append(f"{ml['id']} is_vip 불일치")
if len({o["mail"]["id"] for o in out}) != len(out):
    err.append("ID 중복")

task_mails = sum(1 for o in out if o["gold"]["tasks"])
thread_sizes = Counter(o["mail"]["thread_id"] for o in out)
tags = Counter(t for o in out for t in o["gold"]["tags"])

# ---------- 저장 ----------
owner = P[OWNER]
data = {
    "meta": {"version": VERSION, "count": len(out),
             "description": "테스트셋: LG CNS 팀장 메일함 더미 메일(2026-10-26). 스레드 시작 메일 2건은 10-23 수신. 규칙 수정에 쓰지 않는다"
             if TEST else "보조 개발셋 dev2: LG CNS 팀장 메일함 더미 메일(2026-10-19 위주, 10-20 2건). 스레드 시작 메일 3건은 10-15 · 10-16 수신. 개발셋 과적합 확인용"
             if DEV2 else "독립 작성 세트 dev3: 규칙 · 프롬프트를 보지 않은 별도 작성자가 쓴 메일과 정답"
             if DEV3 else "봉인 시험 세트 test3: 독립 작성자. 수정 중에는 열지 않고 마지막에 1회 채점"
             if TEST3 else "LG CNS 팀장 메일함 하루치 더미 메일(2026-10-19). 스레드 시작 메일 2건은 10-16 수신",
             "schema": "mail=메일 원문(입력), gold=정답 라벨(추출 대상 + 기대 우선순위)"},
    "mailbox": {"owner": owner["email"], "name": owner["name"], "position": owner["position"],
                "team": owner["team"], "member_of": list(DL.values()),
                "superiors": [P[k]["email"] for k in SUPERIORS],
                "favorites": [P[k]["email"] for k in FAVORITES]},
    "people": P,
    "mails": out}
(OUT / JSON_NAME).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

md = [f"# 더미 메일 목록 {VERSION}", "",
      f"메일함: {owner['team']} {owner['name']} {owner['position']} · 총 {len(out)}건 · "
      f"Task 생성 메일 {task_mails}건", "",
      "| ID | 수신 | 발신 | 제목 | 유형 | VIP | 우선 | 태그 |", "|---|---|---|---|---|---|---|---|"]
for o in out:
    ml, g = o["mail"], o["gold"]
    who = " ".join(x for x in (g["sender"]["name"], g["sender"]["position"]) if x) or g["sender"]["team"]
    md.append(f"| {ml['id']} | {ml['received_at'][5:].replace('T', ' ')} | {who} | {ml['subject']} | "
              f"{', '.join(g['action_types'])} | {'★' if ml['is_vip'] else ''} | {g['priority']} | "
              f"{', '.join(g['tags'])} |")
(OUT / LIST_NAME).write_text("\n".join(md) + "\n", encoding="utf-8")

print("총", len(out), "건 / Task 생성", task_mails, "건 (", round(task_mails / len(out) * 100), "% )")
print("유형 분포:", dict(prim))
print("우선순위:", dict(Counter(o["gold"]["priority"] for o in out)))
print("VIP 발신:", sum(o["mail"]["is_vip"] for o in out), "건")
print("엣지케이스 태그:", dict(tags), "합계", sum(tags.values()))
print("2통 이상 스레드:", sum(1 for n in thread_sizes.values() if n > 1), "개")
print("검증 오류:", len(err))
for e in err:
    print("  -", e)
