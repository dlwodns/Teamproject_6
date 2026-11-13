"""분류 작업자 (1프로세스, BE-D10). `CLASSIFY_WORKER=1`이면 서버가 뜰 때 백그라운드 스레드로 돈다.

리마인더 스케줄러(APScheduler, BE-10)가 붙으면 그 작업 하나로 `classify.run_next`를 부르게 옮긴다. 그때까지 쓰는 작은 반복이다.
- 분류를 마치면(done) 바로 다음 작업을 본다.
- 대기 작업이 없거나, 방금 작업이 끝나지 못했으면(ai 꺼짐 · 제한 시간 · 실패) INTERVAL초 쉬고 다시 본다. ai가 꺼져 있을 때
  몇 ms 안에 같은 작업을 거듭 부르지 않기 위해서다(구조도 12절 #17: ai 중지 → queued로 남고 '분류 대기 N건').
- 쉴 때마다 started_at이 오래된 running을 되살린다(classify.requeue_stale).
서버가 멈출 때 stop()으로 끝낸다.
"""
import logging
import os
import threading

from app.ai_client.client import AIClient
from app.core.db import SessionLocal
from app.jobs import classify

INTERVAL = float(os.environ.get("CLASSIFY_WORKER_INTERVAL", "5"))
QUOTA_WAIT = float(os.environ.get("CLASSIFY_QUOTA_WAIT", "600"))  # 엑사원 하루 한도를 다 쓰면 이만큼 쉬고 다시 본다(한도가 풀릴 때까지 반복)
log = logging.getLogger("app.jobs.classify")
_stop = threading.Event()
_thread: threading.Thread | None = None


def enabled() -> bool:
    return os.environ.get("CLASSIFY_WORKER", "").strip().lower() in ("1", "on", "true")


def _tick(ai: AIClient) -> bool | float:
    """작업 하나를 처리한다. 분류를 마쳤으면 True(쉬지 않고 다음 작업), 한도 소진이면 QUOTA_WAIT, 그 밖에는 False(INTERVAL만큼 쉼)."""
    try:
        with SessionLocal() as db:
            if n := classify.requeue_stale(db):
                log.warning("오래 running으로 남은 분류 작업 %d건을 대기열로 되돌림", n)
            out = classify.run_next(db, ai)
    except Exception:  # noqa: BLE001 - 작업자는 죽지 않는다. 쉬었다가 다시 본다
        log.exception("분류 작업 중 오류")
        return False
    if out is None:
        return False
    log.info("분류 작업 %s 메일 %s → %s%s", out["job_id"], out["mail_id"], out["status"],
             f" ({out['error']})" if out.get("error") else "")
    if out.get("error") == "quota":
        return QUOTA_WAIT
    return out["status"] == "done"


def _loop() -> None:
    ai = AIClient()
    with SessionLocal() as db:
        if n := classify.requeue_running(db):
            log.info("running으로 남은 분류 작업 %d건을 대기열로 되돌림", n)
    while not _stop.is_set():
        got = _tick(ai)
        if got is True:
            continue
        _stop.wait(got or INTERVAL)  # False면 INTERVAL, 한도 소진이면 QUOTA_WAIT
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
