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
  (app/mail/graph_sync.sync_all). Graph 호출이 느려도 다른 틱을 막지 않게 따로 돈다. GRAPH_NOTIFY_URL이 있으면 같은 틱에서
  변경 알림 구독을 만들고 갱신한다(app/mail/graph_notify.py) — 알림이 오면 그 계정만 바로 받고, 폴링은 놓친 알림을 메우는 그물로 남긴다.
- 예약 보내기(BE-7 단계 2): 위 둘 중 하나라도 켜져 있으면 1분마다 보낼 시각이 된 예약을 보낸다(app/api/reply.run_due).
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
SCHEDULED_JOB_ID = "scheduled_sends"
SYNC_MINUTES = 1  # 폴링 간격(AI-42: 2 → 1분, 계정당 한 번에 Graph 2~3회라 메일함 한도 10분 1만 회에 한참 못 미친다). 변경 알림(GRAPH_NOTIFY_URL)이 있으면 새 메일은 알림으로 바로 오고 이것은 놓친 것을 메운다
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
    """Outlook 동기화(BE-7). 계정마다 실패를 따로 잡는다(graph_sync.sync_all). 변경 알림 구독 갱신도 여기서."""
    from app.mail import graph_notify, graph_sync

    try:
        with SessionLocal() as db:
            graph_notify.ensure_all(db)
            graph_sync.sync_all(db)
    except Exception:  # noqa: BLE001 - 스케줄러는 죽지 않는다. 다음 틱에 다시 본다
        log.exception("Outlook 동기화 틱 실패")


def scheduled_tick() -> None:
    """예약 보내기(BE-7 단계 2). 보낼 시각이 된 예약을 보낸다."""
    from app.api.reply import run_due

    try:
        with SessionLocal() as db:
            if n := run_due(db):
                log.info("예약 보내기 %d건", n)
    except Exception:  # noqa: BLE001 - 스케줄러는 죽지 않는다. 다음 틱에 다시 본다
        log.exception("예약 보내기 틱 실패")


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
    if jobs:
        jobs.append((scheduled_tick, SCHEDULED_JOB_ID, 1))
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
