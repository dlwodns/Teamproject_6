"""규칙 대조(AI-18, 11/6): 규칙 정규식의 대안을 하나씩 빼고 규칙만으로 다시 채점해 놓침 · 할 일로 잡음이 어떻게 바뀌는지 본다.

  ai/.venv/bin/python eval/runners/ablate_rules.py dev dev2 dev3 dev5 dev6 dev7 dev8

- 빼면 놓침이 늘면 그 대안이 할 일을 찾는 데 쓰인다. 빼면 할 일로 잡음이 늘면 오탐을 막는 대안이다.
- 빼면 할 일로 잡음이 '줄면' 그 대안이 오탐을 만든다 → 좁히거나 뺀다.
- 결과가 같으면 '영향 없음' 목록에 적는다. 다른 대안과 겹쳐서일 수 있으니 바로 지우지 않는다.
- 개발 세트만 쓴다. 봉인 테스트(A · B)는 넣지 않는다(AI-D12).
"""
import json, re, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2] / "ai"))
from app.core.config import Settings
from app.llm.client import LLMError
from app.pipeline import classify as C, signals as SG
from app.pipeline.rules import mail_rules_v1 as R
from app.schemas.classify import ClassifyRequest, OwnerProfile, SenderFlags

FILES = {"dev": "dummy_mails.json", "dev2": "dev2_mails.json", "dev3": "dev3_mails.json", "dev5": "test_mails.json",
         "dev6": "test3_mails.json", "dev7": "dev7_mails.json", "dev8": "dev8_mails.json"}
class NoLLM:
    model = "x"
    def chat_json(self, *a): raise LLMError("rule")
SET = Settings(router_mode="all")

def load(names):
    out = []
    for n in names:
        d = json.load(open(__import__("pathlib").Path(__file__).resolve().parents[2] / "data/dummy" / FILES[n], encoding="utf-8"))
        box, me = d["mailbox"], d["people"]["me"]
        owner = OwnerProfile(email=box["owner"], name=me["name"], position=me["position"], team=me["team"], member_of=box["member_of"])
        for o in d["mails"]:
            if not o.get("gold"): continue
            m = o["mail"]
            if m["from"].lower() == box["owner"].lower(): continue
            req = ClassifyRequest(**{"from": m["from"]}, mail_id=m["id"], to=m["to"], cc=m["cc"], subject=m["subject"], body=m["body"],
                                  attachments=m["attachments"], received_at=m["received_at"], owner=owner,
                                  sender=SenderFlags(is_superior=m["from"] in box["superiors"], is_favorite=m["from"] in box["favorites"]))
            out.append((n, req, bool(o["gold"]["tasks"])))
    return out

def score(data):
    miss, fp, bad = 0, 0, []
    for n, req, gold in data:
        has = bool(C.classify(req, NoLLM(), SET).tasks)
        if gold and not has: miss += 1; bad.append(f"{n}:{req.mail_id}:miss")
        if has and not gold: fp += 1; bad.append(f"{n}:{req.mail_id}:fp")
    return miss, fp, set(bad)

def alts(pat):
    parts, depth, cur, i = [], 0, "", 0
    while i < len(pat):
        ch = pat[i]
        if ch == "\\": cur += pat[i:i+2]; i += 2; continue
        if ch in "([": depth += 1
        if ch in ")]": depth -= 1
        if ch == "|" and depth == 0: parts.append(cur); cur = ""
        else: cur += ch
        i += 1
    return parts + [cur]

names = [a for a in sys.argv[1:] if a in FILES]
data = load(names)
base = score(data)
print("기준 놓침", base[0], "할 일로 잡음", base[1], "메일", len(data))
targets = {k: getattr(R, k) for k in ("REQUEST", "NOT_TASK", "OPTIONAL", "NO_ACTION", "GENERAL_AUDIENCE", "BULK", "NEED", "CONTINGENT", "DONE_OR_CANCEL", "MEETING", "FOLLOW_UP", "URGENT")}
dead = []
for tname, rx in targets.items():
    parts = alts(rx.pattern)
    for i, p in enumerate(parts):
        new = re.compile("|".join(parts[:i] + parts[i+1:]), rx.flags)
        setattr(R, tname, new)
        if hasattr(SG, tname): setattr(SG, tname, new)
        m, f, b = score(data)
        setattr(R, tname, rx)
        if hasattr(SG, tname): setattr(SG, tname, rx)
        if (m, f) == base[:2]: dead.append(f"{tname}[{i}] {p[:40]}")
        if (m, f) != base[:2]:
            print(f"{tname}[{i}] {p[:60]!r}: 빼면 놓침 {base[0]}→{m} · 잡음 {base[1]}→{f}  {sorted(b ^ base[2])[:6]}")

print("영향 없음", len(dead))
for d in dead: print("  -", d)
