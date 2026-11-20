"""리마인더 스케줄러 (BE-12, BE-D10 · 명세 reminders.md 7.3절). APScheduler 단일 프로세스, 1분마다 한 번.

`REMINDER_SCHEDULER=1`이면 서버가 뜰 때 함께 돈다(분류 작업자 CLASSIFY_WORKER와 같은 방식). 틱마다:
1. 리마인더 엔진(app/reminders/engine.run_all): 항목 계산 → 보낼 알림 → 직전 재확인 → 알림 쓰기
2. 리마인더 신호 다시 부르기(jobs/signals.run_pending, REMINDER_SIGNALS=1일 때만). ai를 오래 기다릴 수 있어 별도 작업(signals_tick)으로 돈다
3. 요약 · 회고 머리 문장 미리 만들기(app/reminders/headlines.run, AI-29, BRIEFING_HEADLINE=0이면 끔). 모델 1회가 수 분이라 별도 작업(headlines_tick)
- 예약을 메모리에 들고 있지 않는다. 항목과 보낼 때는 매 틱 DB에서 다시 계산하므로, 서버를 다시 켜면 첫 틱(시작 즉시)이 DB에서
  다시 만든다. 중복은 reminders 유일 제약이 막는다.
- worker가 여럿이면 각자 돌지만 유일 제약 때문에 같은 알림은 한 번만 쓰인다. 그래도 운영은 단일 프로세스로 한다(BE-D10).
- 시각은 app.core.clock.now()(시연 시각 BE-D17)다. APScheduler의 1분 간격은 실제 시간이다.
- Outlook 동기화(BE-7): MAIL_SOURCE=outlook_graph면 REMINDER_SCHEDULER와 상관없이 SYNC_MINUTES마다 연결된 계정을 받는다
  (app/mail/graph_sync.sync_all). Graph 호출이 느려도 다른 틱을 막지 않게 따로 돈다.
"""
import logging
import os
from apscheduler.schedulers.background import BackgroundScheduler

from app.core.clock import real_now
from app.core.db import SessionLocal

log = logging.getLogger("app.reminders")
JOB_ID = "reminders"
SIGNALS_JOB_ID = "reminder_signals"
HEADLINES_JOB_ID = "briefing_headlines"
SYNC_JOB_ID = "outlook_sync"
SYNC_MINUTES = 2  # ponytail: 폴링 간격 고정. 새 메일 즉시 반영이 필요하면 Graph 변경 알림(구독, 최대 7일 갱신)으로
_scheduler: BackgroundScheduler | None = None


def enabled() -> bool:
    return os.environ.get("REMINDER_SCHEDULER", "").strip().lower() in ("1", "on", "true")


def tick() -> None:
    from app.reminders import engine

    try:
        with SessionLocal() as db:
            results = engine.run_all(db)
            sent = sum(len(r["sent"]) for r in results)
            if sent:
                log.info("리마인더 알림 %d건", sent)
    except Exception:  # noqa: BLE001 - 스케줄러는 죽지 않는다. 다음 틱에 다시 본다
        log.exception("리마인더 틱 실패")


def signals_tick() -> None:
    """리마인더 신호 다시 부르기. ai를 AI_BACKGROUND_TIMEOUT_S × 최대 PENDING_PER_TICK통 기다릴 수 있어(AI-28)
    알림 틱과 따로 돈다. 같은 틱에 두면 그동안 알림이 밀린다."""
    from app.ai_client.client import AIClient
    from app.jobs import signals

    if not signals.enabled():
        return
    try:
        with SessionLocal() as db:
            ai = AIClient()
            try:
                signals.run_pending(db, ai)
            finally:
                ai.close()
    except Exception:  # noqa: BLE001 - 스케줄러는 죽지 않는다. 다음 틱에 다시 본다
        log.exception("리마인더 신호 틱 실패")


def headlines_tick() -> None:
    """정한 시각의 요약 · 회고 머리 문장(AI-29). ai를 최대 10분 기다려 알림 틱 · 신호 틱과 따로 돈다."""
    from app.ai_client.client import AIClient
    from app.reminders import headlines

    if not headlines.enabled():
        return
    try:
        with SessionLocal() as db:
            ai = AIClient()
            try:
                if n := headlines.run(db, ai):
                    log.info("머리 문장 %d건", n)
            finally:
                ai.close()
    except Exception:  # noqa: BLE001 - 스케줄러는 죽지 않는다. 다음 틱에 다시 본다
        log.exception("머리 문장 틱 실패")


def sync_tick() -> None:
    """Outlook 동기화(BE-7). 계정마다 실패를 따로 잡는다(graph_sync.sync_all)."""
    from app.mail import graph_sync
    from app.services import calendar

    try:
        with SessionLocal() as db:
            graph_sync.sync_all(db)
            calendar.retry_outlook(db)
    except Exception:  # noqa: BLE001 - 스케줄러는 죽지 않는다. 다음 틱에 다시 본다
        log.exception("Outlook 동기화 틱 실패")


def sync_enabled() -> bool:
    from app.core.config import get_settings

    return get_settings().mail_source == "outlook_graph"


def start() -> None:
    global _scheduler
    jobs = []
    if enabled():  # 서로 막지 않게 따로 돈다(AI-28)
        jobs += [(tick, JOB_ID, 1), (signals_tick, SIGNALS_JOB_ID, 1), (headlines_tick, HEADLINES_JOB_ID, 1)]
    if sync_enabled():
        jobs.append((sync_tick, SYNC_JOB_ID, SYNC_MINUTES))
    if _scheduler is not None or not jobs:
        return
    _scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    # 시작하자마자 한 번(DB에서 다시 만들기), 그다음 간격마다. 늦은 틱은 하나로 합치고 겹쳐 돌지 않는다.
    # 첫 시각은 실제 KST 지금이다(OS 시간대가 KST가 아니어도 스케줄러 시간대 Asia/Seoul과 맞게)
    for fn, job_id, minutes in jobs:
        _scheduler.add_job(fn, "interval", minutes=minutes, id=job_id, next_run_time=real_now(),
                           coalesce=True, max_instances=1, misfire_grace_time=30)
    _scheduler.start()


def stop() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
