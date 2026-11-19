"""요약 · 회고 머리 문장 측정 입력 만들기(AI-29) — 시드 DB로 backend 브리핑을 만들고, 서비스가 ai에 보내는 요청(개인정보 가림)을 저장한다.

backend 코드(app.reminders.headlines.payload)를 그대로 쓰므로 backend 가상환경에서 돈다:
  cd backend && uv run python ../eval/runners/dump_briefing_payloads.py
결과: eval/reports/briefing_payloads.json → run_briefing_effort.py(ai 가상환경)가 읽는다.

시드(data/dummy, 10/16~10/19 메일 100통)에는 완료한 업무가 없다. 회고에 '완료'가 있어야 해서 날마다 그날 기한인 업무 중
id가 짝수인 것을 그날 15:00에 완료로 바꾼다(합성, 측정용). 15:00보다 이른 기한은 '기한 후 완료'가 된다.
"""
import json
import sys
import tempfile
from datetime import date, datetime, time
from pathlib import Path

from fastapi.encoders import jsonable_encoder

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import privacy  # noqa: E402
from app.dev import seed  # noqa: E402
from app.models import Task  # noqa: E402
from app.reminders import briefings, headlines  # noqa: E402

DAYS = (date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22), date(2026, 10, 23))  # 화 ~ 금
MORNING_DAYS, EVENING_DAYS, WEEKLY_DAY = DAYS[:2], DAYS[:2], DAYS[3]
OUT = ROOT / "eval/reports/briefing_payloads.json"


def finish_some(db: Session, day: date) -> None:
    done_at = datetime.combine(day, time(15))
    for t in db.scalars(select(Task).where(Task.status == "pending", Task.due_at >= datetime.combine(day, time()),
                                           Task.due_at < datetime.combine(day, time.max))):
        if t.id % 2 == 0:
            t.status, t.done_at, t.status_changed_at = "done", done_at, done_at
    db.commit()


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        engine = seed.demo_engine(Path(d) / "demo_measure.db")
        seed.reset(engine)
        seed.load(engine, "2026-10-19T23:59")
        out = []
        with Session(engine) as db:
            user_id = 1

            def dump(kind: str, day: date, at: datetime) -> None:
                b = briefings.build(db, user_id, kind, day, at)
                p = privacy.masker_for(db, user_id).mask_obj(headlines.payload(db, user_id, b))
                out.append({"id": f"{kind}_{day:%m%d}", "kind": kind, "counts": {s["id"]: s["count"] for s in b["sections"]},
                            "payload": jsonable_encoder(p)})

            for day in DAYS:
                if day in MORNING_DAYS:
                    dump("morning", day, datetime.combine(day, time(8, 30)))
                finish_some(db, day)
                if day in EVENING_DAYS:
                    dump("evening", day, datetime.combine(day, time(17, 30)))
            dump("weekly", WEEKLY_DAY, datetime.combine(WEEKLY_DAY, time(17, 30)))
        engine.dispose()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for x in out:
        print(x["id"], x["counts"])
    print(f"→ {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
