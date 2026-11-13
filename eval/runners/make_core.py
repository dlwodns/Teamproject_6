"""핵심 회귀 세트 50통을 만든다 (AI-21, 11/11 사용자 결정): 프롬프트 · 모델이 바뀔 때마다 이 세트만 새로 부른다.

왜 50통인가: LG K-EXAONE 무료 API가 하루 100회라 하루에 두 번(예: 고치기 전 · 뒤) 돌릴 수 있다.
코드(조건 · 후처리 · 채점기 · 정답)만 바뀌면 모델을 부르지 않고 남긴 출력으로 다시 채점한다(run_dummy.py --replay).

구성(개발 세트 7개, 봉인 세트 제외 · 메일함이 같아 한 파일로 합친다, ID는 '세트:M-번호'):
1. 위험 메일 14통 고정 — AI-D17 사각지대(바뀐 회의 참석 · 전 직원 희망자 · 해당자 · 발표 · 비밀번호 만료 · 나에게 직접 온 알림)
2. 나머지 36통 — 주 유형마다 최소 2통 · 정답 태그마다 최소 1통이 들어가게 고른다(가장 많은 빈칸을 채우는 메일부터).
   드문 태그일수록 먼저(1/통 수). 같으면 11/11 K-EXAONE 40통에서 틀린 메일(반복 오답)을 먼저, 그다음 시드 고정 무작위
3. 할 일 있음 25 · 없음 25
사용: ai/.venv/bin/python eval/runners/make_core.py  →  data/dummy/core50_mails.json (+ 목록 core50_list.md)
"""
import json
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DUMMY = ROOT / "data/dummy"
FILES = {"dev": "dummy_mails.json", "dev2": "dev2_mails.json", "dev3": "dev3_mails.json", "dev5": "test_mails.json",
         "dev6": "test3_mails.json", "dev7": "dev7_mails.json", "dev8": "dev8_mails.json"}
RISK = ["dev:M-0070", "dev:M-0089", "dev:M-0092", "dev2:M-0029", "dev2:M-0014", "dev2:M-0005", "dev3:M-0044", "dev3:M-0018",
        "dev3:M-0058", "dev5:M-0025", "dev5:M-0009", "dev6:M-0039", "dev8:M-0005", "dev8:M-0024"]
# 11/11 K-EXAONE(v6) 40통 오답 · 7.8B 반복 오답(공지 ↔ 공유 · 사내 소식 · 자동 발송 · 사용 안내 · 조건부 제출 · 발표)
HARD = {"dev7:M-0004", "dev7:M-0016", "dev7:M-0020", "dev7:M-0025", "dev7:M-0034", "dev7:M-0044", "dev7:M-0050", "dev8:M-0043",
        "dev7:M-0005", "dev7:M-0047", "dev8:M-0006", "dev8:M-0055", "dev7:M-0037", "dev8:M-0038", "dev8:M-0008"}
N, HALF, MIN_TYPE, SEED = 50, 25, 2, 21


def main():
    pool, box, people, metas = {}, None, None, []
    for s, f in FILES.items():
        d = json.loads((DUMMY / f).read_text(encoding="utf-8"))
        box, people = box or d["mailbox"], people or d["people"]
        assert d["mailbox"] == box, f"{s} 메일함이 다르다 — 한 파일로 합칠 수 없다"
        metas.append(d["meta"]["version"])
        for o in d["mails"]:
            if o["mail"]["from"] != box["owner"]:
                pool[f"{s}:{o['mail']['id']}"] = o
    freq = Counter(t for o in pool.values() for t in o["gold"]["tags"])

    def has_task(i):
        return bool(pool[i]["gold"]["tasks"])

    def select(seed):
        """욕심 선택 한 번. 드문 태그일수록 점수가 크다(최대 1점). 같으면 반복 오답, 그다음 시드로 섞은 순서."""
        pick = list(RISK)
        need_type = Counter({t: MIN_TYPE for t in {o["gold"]["action_types"][0] for o in pool.values()}})
        need_tag = Counter({t: 1 for o in pool.values() for t in o["gold"]["tags"]})

        def take(i):
            g = pool[i]["gold"]
            need_type[g["action_types"][0]] -= 1
            for t in g["tags"]:
                need_tag[t] -= 1

        def gain(i):
            g = pool[i]["gold"]
            return (need_type[g["action_types"][0]] > 0) + sum(min(1.0, 3 / freq[t]) for t in g["tags"] if need_tag[t] > 0)

        for i in pick:
            take(i)
        order = sorted(pool)
        random.Random(seed).shuffle(order)
        while len(pick) < N:
            cand = [i for i in order if i not in pick and sum(has_task(x) == has_task(i) for x in pick) < HALF]
            best = max(cand, key=lambda i: (gain(i), i in HARD))
            pick.append(best)
            take(best)
        miss = [t for t, n in need_type.items() if n > 0] + [t for t, n in need_tag.items() if n > 0]
        return pick, miss

    # 할 일 있음 25칸 중 10칸을 위험 메일이 차지해 욕심 선택만으로는 태그 하나가 빠질 수 있다 —
    # 시드를 바꿔 고른 뒤 한 통씩 바꿔 빈칸을 메우고, 빠진 것이 가장 적고 반복 오답이 가장 많은 구성을 쓴다
    def missing(pick):
        nt = Counter({t: MIN_TYPE for t in {o["gold"]["action_types"][0] for o in pool.values()}})
        ng = Counter({t: 1 for o in pool.values() for t in o["gold"]["tags"]})
        for i in pick:
            nt[pool[i]["gold"]["action_types"][0]] -= 1
            for t in pool[i]["gold"]["tags"]:
                ng[t] -= 1
        return [t for t, n in nt.items() if n > 0] + [t for t, n in ng.items() if n > 0]

    def repair(pick):
        """빠진 태그 · 유형이 있으면 같은 쪽(할 일 있음 · 없음) 메일 하나를 바꿔 빈칸을 줄인다(위험 메일은 바꾸지 않는다)."""
        pick = list(pick)
        for _ in range(20):
            left = missing(pick)
            if not left:
                break
            best = None
            for c in sorted(pool):
                if c in pick or not (set(pool[c]["gold"]["tags"]) | {pool[c]["gold"]["action_types"][0]}) & set(left):
                    continue
                for x in pick:
                    if x in RISK or has_task(x) != has_task(c):
                        continue
                    trial = [c if y == x else y for y in pick]
                    score = (len(missing(trial)), -sum(i in HARD for i in trial))
                    if best is None or score < best[0]:
                        best = (score, trial)
            if best is None or best[0][0] >= len(left):
                break
            pick = best[1]
        return pick, missing(pick)

    pick, left = min((repair(select(SEED + k)[0]) for k in range(30)), key=lambda r: (len(r[1]), -sum(i in HARD for i in r[0])))
    pick.sort(key=lambda i: (list(FILES).index(i.split(":")[0]), i))
    mails = []
    for i in pick:
        o = json.loads(json.dumps(pool[i]))
        o["mail"]["id"] = i
        mails.append(o)
    yes = sum(bool(o["gold"]["tasks"]) for o in mails)
    meta = {"version": "core50-v1", "count": len(mails), "sources": metas,
            "description": "핵심 회귀 세트(AI-21, 11/11): 위험 메일 14통 + 유형 · 태그 덮기 36통, 할 일 있음 25 · 없음 25. make_core.py로 만든다",
            "schema": "mail=메일 원문(입력), gold=정답 라벨"}
    (DUMMY / "core50_mails.json").write_text(json.dumps({"meta": meta, "mailbox": box, "people": people, "mails": mails},
                                                        ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["# 핵심 회귀 세트 core50", "", meta["description"], "", "| ID | 제목 | 주 유형 | 할 일 | 태그 | 고른 이유 |", "|---|---|---|---|---|---|"]
    for o in mails:
        i, g = o["mail"]["id"], o["gold"]
        why = "위험 메일" if i in RISK else "반복 오답" if i in HARD else "유형 · 태그 덮기"
        lines.append(f"| {i} | {o['mail']['subject']} | {g['action_types'][0]} | {'있음' if g['tasks'] else '없음'} | {', '.join(g['tags'])} | {why} |")
    (DUMMY / "core50_list.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(mails)}통 · 할 일 있음 {yes} · 없음 {len(mails) - yes} · 반복 오답 {sum(o['mail']['id'] in HARD for o in mails)}통")
    print("주 유형:", dict(Counter(o["gold"]["action_types"][0] for o in mails)))
    print("못 채운 유형 · 태그:", left or "없음")


if __name__ == "__main__":
    main()
