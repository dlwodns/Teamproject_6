# -*- coding: utf-8 -*-
"""더미 메일 생성기
people.py(가상 조직도) + mails.py(메일 정의) -> dummy_mails.json, mail_list.md
`python build.py test` 이면 mails_test.py(테스트셋) -> test_mails.json, test_mail_list.md
`python build.py dev2` 이면 mails_dev2.py(보조 개발셋) -> dev2_mails.json, dev2_mail_list.md
`python build.py dev4` 이면 mails_dev4.py(개발셋 v2, DE-1) -> dev4_mails.json, dev4_mail_list.md
`python build.py testA --src <레포 밖 폴더>` 이면 <폴더>/mails_testA.py(봉인 테스트, DE-D15) -> 같은 폴더에 JSON · 목록
`python build.py demo` 이면 mails.py 받은 메일 + mails_sent.py 보낸 메일(DE-2) -> demo_mails.json, demo_mail_list.md (시연용, 채점에 쓰지 않음)
수정은 people.py / mails*.py에서 하고 다시 생성한다. 실행 시 검증 결과와 JSON의 SHA-256을 출력한다.
라벨 규약: docs/50_data_eval/label_guide.md"""
import hashlib
import importlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from people import P, DL, OWNER, SUPERIORS, FAVORITES, ADDR
from mails import MAILS

# 세트 이름 -> (메일 정의 모듈, 버전, JSON, 목록, 설명). v1은 위 mails.py와 아래 TARGET을 쓴다
SETS = {
    "v1": ("mails", "v1", "dummy_mails.json", "mail_list.md",
           "LG CNS 팀장 메일함 하루치 더미 메일(2026-10-19). 스레드 시작 메일 2건은 10-16 수신"),
    "test": ("mails_test", "test-v1", "test_mails.json", "test_mail_list.md",
             "테스트셋: LG CNS 팀장 메일함 더미 메일(2026-10-26). 스레드 시작 메일 2건은 10-23 수신. 규칙 수정에 쓰지 않는다"),
    "dev2": ("mails_dev2", "dev2-v1", "dev2_mails.json", "dev2_mail_list.md",
             "보조 개발셋 dev2: LG CNS 팀장 메일함 더미 메일(2026-10-19 위주, 10-20 2건). 스레드 시작 메일 3건은 10-15 · 10-16 수신. 개발셋 과적합 확인용"),
    "dev3": ("mails_dev3", "dev3-v1", "dev3_mails.json", "dev3_mail_list.md",
             "독립 작성 세트 dev3: 규칙 · 프롬프트를 보지 않은 별도 작성자가 쓴 메일과 정답"),
    "test3": ("mails_test3", "test3-v1", "test3_mails.json", "test3_mail_list.md",
              "봉인 시험 세트 test3: 독립 작성자. 수정 중에는 열지 않고 마지막에 1회 채점"),
    "dev4": ("mails_dev4", "dev4-v1", "dev4_mails.json", "dev4_mail_list.md",
             "개발셋 v2(dev4): 헷갈리는 할 일 없는 메일을 늘린 개발 세트(DE-D18). 규칙 수정에 써도 된다"),
    "testA": ("mails_testA", "testA-v1", "testA_mails.json", "testA_mail_list.md",
              "봉인 테스트 A(DE-D15 · DE-D16): 레포 밖 보관. 버전마다 1회 채점"),
    "testB": ("mails_testB", "testB-v1", "testB_mails.json", "testB_mail_list.md",
              "봉인 테스트 B(DE-D15 · DE-D16): 레포 밖 보관. 마일스톤에서만 채점"),
    "demo": ("mails_sent", "demo-v1", "demo_mails.json", "demo_mail_list.md",
             "시연용: 개발셋 v1 받은 메일 100통 + 보낸 메일(DE-2, 응답 대기 시연 ⑥). 받은 메일 M · T 번호는 v1과 같다. "
             "#10 시드가 --source로 읽는다. 채점에는 쓰지 않는다"),
}
NEW_SETS = {"dev4", "testA", "testB"}  # 라벨 가이드 태그 목록 검사 · 보낸 메일 허용
SENT_OK = NEW_SETS | {"demo"}  # 보낸 메일을 넣어도 되는 세트(DE-D10). 기존 세트(v1 · test · dev2 · dev3 · test3)는 안 된다
SEALED = {"testA", "testB"}  # 레포 밖(--src)에서만 만든다
ARGS = sys.argv[1:]
SRC = Path(ARGS[ARGS.index("--src") + 1]).resolve() if "--src" in ARGS else None
NAME = next((a for a in ARGS if a in SETS), "v1")
if SRC is not None:
    ARGS = [a for i, a in enumerate(ARGS) if a != "--src" and (i == 0 or ARGS[i - 1] != "--src")]
if [a for a in ARGS if a not in SETS] or len(ARGS) > 1:
    sys.exit(f"알 수 없는 인자: {sys.argv[1:]} (세트: {', '.join(SETS)} · 봉인 테스트는 --src <폴더>)")
REPO = Path(__file__).resolve().parents[2]
if NAME in SEALED and (SRC is None or SRC == REPO or REPO in SRC.parents):
    sys.exit(f"{NAME}는 봉인 테스트라 레포 밖 폴더에서 만든다: python build.py {NAME} --src <레포 밖 폴더> (DE-D15)")
TEST, DEV2, DEV3, TEST3 = (NAME == n for n in ("test", "dev2", "dev3", "test3"))  # 기존 세트 표시(호환)
SET_TARGET, AWAIT_AT = None, []  # AWAIT_AT: 응답 대기 기대값을 찍을 기준 시각("MM-DD HH:MM", 보낸 메일 정의 파일에 둔다)
if NAME != "v1":  # 세트마다 추가 인물만 덧붙인다(개발 세트 people은 그대로)
    if SRC is not None:
        sys.path.insert(0, str(SRC))
    try:
        _mod = importlib.import_module(SETS[NAME][0])
    except ModuleNotFoundError as e:
        sys.exit(f"{SETS[NAME][0]}.py를 찾지 못했다({e.name}). 라벨 가이드 7절 형식으로 먼저 만든다")
    if NAME == "demo":  # 받은 메일은 v1 그대로, 보낸 메일만 더한다. 분포 목표도 v1
        MAILS = MAILS + _mod.MAILS
    else:
        MAILS, SET_TARGET = _mod.MAILS, _mod.TARGET
    P = {**P, **getattr(_mod, "EXTRA", {})}
    AWAIT_AT = getattr(_mod, "AWAIT_AT", [])

TYPE = {"자제": "자료제출요청", "수정": "수정재전송요청", "회요": "회신요청", "검승": "검토승인요청",
        "일정": "일정참석", "회신": "회신", "공지": "공지", "참조": "참조", "기타": "기타"}
TASK_TYPES = {"자료제출요청", "수정재전송요청", "회신요청", "검토승인요청", "일정참석"}
TARGET = {"자료제출요청": 16, "수정재전송요청": 10, "회신요청": 14, "검토승인요청": 8, "일정참석": 8,
          "회신": 8, "공지": 16, "참조": 14, "기타": 6}
TARGET = SET_TARGET or TARGET
Y, OUT = "2026", SRC or Path(__file__).parent
_, VERSION, JSON_NAME, LIST_NAME, DESCRIPTION = SETS[NAME]
TAGS = {"완곡요청", "암시요청", "CC지목", "공지속개인요청", "공지속역할요청", "요청2개", "재요청", "첨부이미지요청",
        "외부긴급", "지목없는당부", "타인요청", "CC미지목", "TO정보공유", "확인부탁공유", "완료회신", "조건부회신",
        "자동회신", "일정취소", "사내소식", "사외행사", "VIP저중요도", "상대날짜", "마감없음", "마감모호", "마감변경",
        "영문표현", "보낸메일", "애매"}  # 라벨 가이드 5절. 새 세트(NEW_SETS)만 검사한다


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
# 받은 메일은 M-번호 · T-번호를 예전과 똑같이 매긴다(보낸 메일이 앞 날짜에 끼어도 기존 번호가 밀리지 않게).
# 보낸 메일은 S-번호, 보낸 메일로 새로 생긴 스레드는 받은 메일 스레드 번호 뒤에 붙인다(DE-2)
recv_rows = [m for m in rows if m["frm"] != OWNER]
sent_rows = [m for m in rows if m["frm"] == OWNER]
ids, keys, th_map, out = {}, {}, {}, []
for i, m in enumerate(recv_rows, 1):
    ids[id(m)], keys[id(m)] = f"M-{i:04d}", m["th"] or f"_single{i}"
for j, m in enumerate(sent_rows, 1):
    ids[id(m)], keys[id(m)] = f"S-{j:04d}", m["th"] or f"_sent{j}"
for m in recv_rows + sent_rows:
    th_map.setdefault(keys[id(m)], f"T-{len(th_map) + 1:04d}")
for m in rows:
    p = P[m["frm"]]
    recv = datetime.fromisoformat(f"{Y}-{m['day']}T{m['t'][:2]}:{m['t'][2:]}")
    key = keys[id(m)]
    body = m["body"] if m["raw"] else f"{greet(p)}\n\n{m['body']}\n\n감사합니다.\n\n{sign(p)}"
    team = f"{p['company']} {p['team']}" if p["external"] else p["team"]
    sender = {"name": None, "position": None, "team": team} if m["raw"] else \
             {"name": p["name"], "position": p["position"], "team": team}
    men = m["men"] if m["men"] is not None else (bool(m["tasks"]) and OWNER in m["to"])
    out.append({
        "mail": {"id": ids[id(m)], "thread_id": th_map[key],
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
err, warn = [], []
owner_addr = P[OWNER]["email"]
sent = [o for o in out if o["mail"]["from"] == owner_addr]  # 보낸 메일(DE-D10): 분포 · 할 일 통계에서 뺀다
if sent and NAME not in SENT_OK:
    err.append(f"보낸 메일 {len(sent)}통 — 기존 세트에는 넣지 않는다(새 세트 dev4 · testA · testB · 시연용 demo만)")
prim = Counter(o["gold"]["action_types"][0] for o in out if o not in sent)
for t, n in TARGET.items():
    if prim[t] != n:
        err.append(f"분포 불일치 {t}: {prim[t]}건 (목표 {n})")
for o in out:
    g, ml, pt = o["gold"], o["mail"], o["gold"]["action_types"][0]
    if NAME in NEW_SETS:
        warn += [f"{ml['id']} 라벨 가이드 5절에 없는 태그: {t}" for t in g["tags"] if t not in TAGS]
    if o in sent:
        if g["tasks"]:
            err.append(f"{ml['id']} 보낸 메일인데 tasks 있음(내 요청은 상대의 할 일)")
        if "보낸메일" not in g["tags"]:
            warn.append(f"{ml['id']} 보낸 메일에 '보낸메일' 태그 없음")
        continue
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
             "description": DESCRIPTION,
             "schema": "mail=메일 원문(입력), gold=정답 라벨(추출 대상 + 기대 우선순위)"},
    "mailbox": {"owner": owner["email"], "name": owner["name"], "position": owner["position"],
                "team": owner["team"], "member_of": list(DL.values()),
                "superiors": [P[k]["email"] for k in SUPERIORS],
                "favorites": [P[k]["email"] for k in FAVORITES]},
    "people": P,
    "mails": out}
JSON_TEXT = json.dumps(data, ensure_ascii=False, indent=2)
(OUT / JSON_NAME).write_text(JSON_TEXT, encoding="utf-8")

md = [f"# 더미 메일 목록 {VERSION}", "",
      f"메일함: {owner['team']} {owner['name']} {owner['position']} · 총 {len(out)}건 · "
      f"Task 생성 메일 {task_mails}건", "",
      "| ID | 수신 | 발신 | 제목 | 유형 | VIP | 우선 | 태그 |", "|---|---|---|---|---|---|---|---|"]
for o in out:
    ml, g = o["mail"], o["gold"]
    who = " ".join(x for x in (g["sender"]["name"], g["sender"]["position"]) if x) or g["sender"]["team"]
    who = f"(보냄) {who}" if ml["from"] == owner_addr else who
    md.append(f"| {ml['id']} | {ml['received_at'][5:].replace('T', ' ')} | {who} | {ml['subject']} | "
              f"{', '.join(g['action_types'])} | {'★' if ml['is_vip'] else ''} | {g['priority']} | "
              f"{', '.join(g['tags'])} |")
(OUT / LIST_NAME).write_text("\n".join(md) + "\n", encoding="utf-8")

if sent:
    print("보낸 메일", len(sent), "통 (유형 분포 검증 · 분류 채점에서 뺀다)")
print("총", len(out), "건 / Task 생성", task_mails, "건 (", round(task_mails / len(out) * 100), "% )")
print("유형 분포:", dict(prim))
print("우선순위:", dict(Counter(o["gold"]["priority"] for o in out)))
print("VIP 발신:", sum(o["mail"]["is_vip"] for o in out), "건")
print("엣지케이스 태그:", dict(tags), "합계", sum(tags.values()))
print("2통 이상 스레드:", sum(1 for n in thread_sizes.values() if n > 1), "개")
print("검증 오류:", len(err))
for e in err:
    print("  -", e)
if warn:
    print("경고:", len(warn))
    for w in warn:
        print("  -", w)
for at in AWAIT_AT:  # 응답 대기 기대값: 요청한 보낸 메일(DE-D10) 중 같은 스레드에 상대 회신이 없고 3일 이상 지난 것
    now, wait = datetime.fromisoformat(ts(at)), []
    for o in sent:
        ml, sent_at = o["mail"], datetime.fromisoformat(o["mail"]["received_at"])
        if o["gold"]["action_types"][0] not in TASK_TYPES or sent_at > now:
            continue
        replied = any(x["mail"]["thread_id"] == ml["thread_id"] and x["mail"]["from"] != owner_addr
                      and sent_at < datetime.fromisoformat(x["mail"]["received_at"]) <= now for x in out)
        if not replied and (now - sent_at).total_seconds() >= 3 * 86400:
            wait.append(ml["id"])
    print(f"응답 대기 기대값 @ {at}: {len(wait)}통", ", ".join(wait))
print("SHA-256:", hashlib.sha256((OUT / JSON_NAME).read_bytes()).hexdigest(), JSON_NAME)
