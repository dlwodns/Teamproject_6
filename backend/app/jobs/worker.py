"""분류 작업자 (1프로세스, BE-D10). `CLASSIFY_WORKER=1`이면 서버가 뜰 때 백그라운드 스레드로 돈다.

리마인더 스케줄러(APScheduler, BE-10)가 붙으면 그 작업 하나로 `classify.run_next`를 부르게 옮긴다. 그때까지 쓰는 작은 반복이다.
대기 작업이 없으면 INTERVAL초 쉬고 다시 본다. 서버가 멈출 때 stop()으로 끝낸다.
"""
import logging
import os
import threading

from app.ai_client.client import AIClient
from app.core.db import SessionLocal
from app.jobs import classify

INTERVAL = float(os.environ.get("CLASSIFY_WORKER_INTERVAL", "5"))
log = logging.getLogger("app.jobs.classify")
_stop = threading.Event()
_thread: threading.Thread | None = None


def enabled() -> bool:
    return os.environ.get("CLASSIFY_WORKER", "").strip().lower() in ("1", "on", "true")


def _loop() -> None:
    ai = AIClient()
    with SessionLocal() as db:
        if n := classify.requeue_running(db):
            log.info("running으로 남은 분류 작업 %d건을 대기열로 되돌림", n)
    while not _stop.is_set():
        try:
            with SessionLocal() as db:
                out = classify.run_next(db, ai)
            if out:
                log.info("분류 작업 %s 메일 %s → %s", out["job_id"], out["mail_id"], out["status"])
                continue
        except Exception:  # noqa: BLE001 - 작업자는 죽지 않는다. 다음 차례에 다시 본다
            log.exception("분류 작업 중 오류")
        _stop.wait(INTERVAL)
    ai.close()


def start() -> None:
    global _thread
    if _thread is None and enabled():
        _stop.clear()
        _thread = threading.Thread(target=_loop, name="classify-worker", daemon=True)
        _thread.start()


def stop() -> None:
    global _thread
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=5)
        _thread = None
