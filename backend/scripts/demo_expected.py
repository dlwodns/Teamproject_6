"""시연 시각 후보별 기대값. 원본 JSON만 읽는다(시드 · API 코드 import 없음, DB 조회 없음, 표준 라이브러리만).

    python3 backend/scripts/demo_expected.py                      # 후보 A · B
    python3 backend/scripts/demo_expected.py --as-of 2026-10-19T12:00

- DB와 대조할 값: 메일 수 · 업무 수 · 발신자('김 팀장') 미처리 업무 수와 원본 메일 id · M-0064 도착 여부.
- 시연 시각 참고값(대시보드 API 아님): 기한 없는 업무는 뺀다.
  - due_today_remaining: 기준 시각과 같은 날 마감이고 마감 >= 기준 시각 (마감 시각 정각은 '아직 남음')
  - overdue: 마감 < 기준 시각 (전날 이전 마감 포함)
- 시드 직후에는 모든 업무가 pending이라 '미처리'는 적재된 업무 전체다.
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "data" / "dummy" / "dummy_mails.json"
SENDER_MAILS = ("M-0026", "M-0040", "M-0089")  # 시연 ② '김 팀장님 건' 3건
CANDIDATE_B = "2026-10-20T09:00"


def expected(data: dict, as_of: datetime, sender: str = "김 팀장", probe: str = "M-0064") -> dict:
    surname, position = sender.split()
    sender_emails = {p["email"] for p in data["people"].values()
                     if p["email"] != data["mailbox"]["owner"]
                     and (p.get("name") or "").startswith(surname) and p.get("position") == position}
    arrived = [m for m in data["mails"] if datetime.fromisoformat(m["mail"]["received_at"]) <= as_of]
    tasks = [(m["mail"], t) for m in arrived for t in m["gold"]["tasks"]]
    dues = [datetime.fromisoformat(t["due_at"]) for _, t in tasks if t.get("due_at")]
    sender_tasks = [mail["id"] for mail, _ in tasks if mail["from"] in sender_emails]
    return {
        "as_of": as_of.isoformat(timespec="minutes"),
        "mails": len(arrived),
        "tasks": len(tasks),
        "sender_pending_tasks": len(sender_tasks),
        "sender_mail_ids": sorted(set(sender_tasks)),
        f"{probe}_arrived": any(m["mail"]["id"] == probe for m in arrived),
        "due_today_remaining": sum(1 for d in dues if d.date() == as_of.date() and d >= as_of),
        "overdue": sum(1 for d in dues if d < as_of),
        "no_due": sum(1 for _, t in tasks if not t.get("due_at")),
    }


def candidate_a(data: dict) -> datetime:
    """M-0026 · M-0040 · M-0089가 모두 도착한 첫 시각"""
    return max(datetime.fromisoformat(m["mail"]["received_at"]) for m in data["mails"] if m["mail"]["id"] in SENDER_MAILS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--as-of", help="기준 시각(KST). 없으면 후보 A · B")
    parser.add_argument("--source", type=Path, default=SOURCE)
    args = parser.parse_args()
    data = json.loads(args.source.read_text(encoding="utf-8"))
    if args.as_of:
        out = expected(data, datetime.fromisoformat(args.as_of))
    else:
        out = {"A": expected(data, candidate_a(data)), "B": expected(data, datetime.fromisoformat(CANDIDATE_B))}
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
