"""분류 작업자 (1프로세스, BE-D10). `CLASSIFY_WORKER=1`이면 서버가 뜰 때 작업자 스레드 WORKERS개가 돌고, 작업자마다 한 번에
PARALLEL통을 꺼내 ai에 동시에 보낸다(동시 호출 = WORKERS × PARALLEL).

- 이유(11-19 실제 메일 10통 시험): 엑사원 API 한 통이 30초~3분이라 하나씩이면 10통에 10분이 넘고, 느린 메일 하나가 뒤를 다 막는다.
  작업 꺼내기(classify._claim)는 조건부 UPDATE라 여러 스레드가 같은 작업을 두 번 꺼내지 않는다. 하루 호출 수(엑사원 100회)는 그대로다.
- 섞은 이유: 작업자 하나가 한 번에 여러 통을 보내면(PARALLEL) 묶음이 끝날 때까지 그 작업자는 쉬므로, 느린 한 통이 묶음을 붙잡는다.
  작업자를 둘 이상 두면 한 작업자가 붙잡혀도 다른 작업자가 다음 묶음을 꺼낸다.
- 개수: 기본 2 × 2 = 동시 4통. ai 서버의 엑사원 동시 호출 상한이 8(ai/app/llm/client.py _API_POOL)이고 대화형 호출(캐치봇 · 다듬기)도
  그 안에서 돌아야 하므로 절반으로 둔다. `CLASSIFY_WORKERS` · `CLASSIFY_PARALLEL`로 바꾸고, 곱이 8을 넘으면 PARALLEL을 줄인다.
  엑사원 API의 분당 · 동시 호출 제한은 문서에서 찾지 못해 [불확실] — 429가 보이면 줄인다.

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
from concurrent.futures import ThreadPoolExecutor

from app.ai_client.client import AIClient
from app.core.db import SessionLocal
from app.jobs import classify

INTERVAL = float(os.environ.get("CLASSIFY_WORKER_INTERVAL", "5"))
QUOTA_WAIT = float(os.environ.get("CLASSIFY_QUOTA_WAIT", "600"))  # 엑사원 하루 한도를 다 쓰면 이만큼 쉬고 다시 본다(한도가 풀릴 때까지 반복)
log = logging.getLogger("app.jobs.classify")
MAX_WORKERS = 8  # ai 서버 엑사원 동시 호출 상한(_API_POOL)과 같다
_stop = threading.Event()
_threads: list[threading.Thread] = []


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def workers() -> int:
    """CLASSIFY_WORKERS(기본 2), 1~MAX_WORKERS로 자른다. 숫자가 아니면 기본값."""
    return max(1, min(_env_int("CLASSIFY_WORKERS", 2), MAX_WORKERS))


def parallel() -> int:
    """작업자 하나가 한 번에 보내는 수 CLASSIFY_PARALLEL(기본 2). 작업자 수와 곱해 MAX_WORKERS를 넘지 않게 줄인다."""
    return max(1, min(_env_int("CLASSIFY_PARALLEL", 2), MAX_WORKERS // workers()))


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
    if out.get("error") in ("quota", "auth"):  # 한도 소진 · 키 없음(설정 문제)은 금방 풀리지 않는다. 매 5초 헛호출하지 않는다
        return QUOTA_WAIT
    return out["status"] == "done"


def _loop() -> None:
    ai = AIClient()  # 작업자마다 따로. 한 작업자 안의 동시 호출은 이 클라이언트를 나눠 쓴다(httpx Client는 스레드 안전)
    n = parallel()
    with ThreadPoolExecutor(max_workers=n, thread_name_prefix=threading.current_thread().name) as pool:
        while not _stop.is_set():
            got = list(pool.map(lambda _: _tick(ai), range(n)))  # 한 번에 n통을 꺼내 동시에 보낸다(각자 세션)
            if True in got:
                continue
            _stop.wait(max((g for g in got if g is not False), default=INTERVAL) or INTERVAL)  # 한도 소진이면 QUOTA_WAIT
    ai.close()


def start() -> None:
    if _threads or not enabled():
        return
    _stop.clear()
    with SessionLocal() as db:  # 지난번에 끊긴 running을 먼저 되돌린다(한 번만 — 스레드가 서로의 작업을 되돌리지 않게)
        if n := classify.requeue_running(db):
            log.info("running으로 남은 분류 작업 %d건을 대기열로 되돌림", n)
    for i in range(workers()):
        t = threading.Thread(target=_loop, name=f"classify-worker-{i + 1}", daemon=True)
        t.start()
        _threads.append(t)


def stop() -> None:
    _stop.set()
    for t in _threads:
        t.join(timeout=5)
    _threads.clear()
