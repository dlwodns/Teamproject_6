"""리마인더 스케줄러 (BE-12, BE-D10 · 명세 reminders.md 7.3절). APScheduler 단일 프로세스, 1분마다 한 번.

`REMINDER_SCHEDULER=1`이면 서버가 뜰 때 함께 돈다(분류 작업자 CLASSIFY_WORKER와 같은 방식). 틱마다:
1. 리마인더 엔진(app/reminders/engine.run_all): 항목 계산 → 보낼 알림 → 직전 재확인 → 알림 쓰기
2. 리마인더 신호 다시 부르기(jobs/signals.run_pending, REMINDER_SIGNALS=1일 때만)
- 예약을 메모리에 들고 있지 않는다. 항목과 보낼 때는 매 틱 DB에서 다시 계산하므로, 서버를 다시 켜면 첫 틱(시작 즉시)이 DB에서
  다시 만든다. 중복은 reminders 유일 제약이 막는다.
- worker가 여럿이면 각자 돌지만 유일 제약 때문에 같은 알림은 한 번만 쓰인다. 그래도 운영은 단일 프로세스로 한다(BE-D10).
- 시각은 app.core.clock.now()(시연 시각 BE-D17)다. APScheduler의 1분 간격은 실제 시간이다.
"""
import logging
import os
from apscheduler.schedulers.background import BackgroundScheduler

from app.core.clock import real_now
from app.core.db import SessionLocal

log = logging.getLogger("app.reminders")
JOB_ID = "reminders"
_scheduler: BackgroundScheduler | None = None


def enabled() -> bool:
    return os.environ.get("REMINDER_SCHEDULER", "").strip().lower() in ("1", "on", "true")


def tick() -> None:
    from app.ai_client.client import AIClient
    from app.jobs import signals
    from app.reminders import engine

    try:
        with SessionLocal() as db:
            results = engine.run_all(db)
            sent = sum(len(r["sent"]) for r in results)
            if sent:
                log.info("리마인더 알림 %d건", sent)
            if signals.enabled():
                ai = AIClient()
                try:
                    signals.run_pending(db, ai)
                finally:
                    ai.close()
    except Exception:  # noqa: BLE001 - 스케줄러는 죽지 않는다. 다음 틱에 다시 본다
        log.exception("리마인더 틱 실패")


def start() -> None:
    global _scheduler
    if _scheduler is not None or not enabled():
        return
    _scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    # 시작하자마자 한 번(DB에서 다시 만들기), 그다음 1분마다. 늦은 틱은 하나로 합치고 겹쳐 돌지 않는다.
    # 첫 시각은 실제 KST 지금이다(OS 시간대가 KST가 아니어도 스케줄러 시간대 Asia/Seoul과 맞게)
    _scheduler.add_job(tick, "interval", minutes=1, id=JOB_ID, next_run_time=real_now(),
                       coalesce=True, max_instances=1, misfire_grace_time=30)
    _scheduler.start()


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
