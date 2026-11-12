"""메일 분류 작업 (구조도 4 · 12절, BE-9 ai_client 사용).

흐름: 메일 저장 → enqueue()로 classify_jobs에 queued → run_next()가 하나씩 꺼내
  본문 가져오기 → 요청 만들기(기억 포함, ai_client/payload.py) → ai /classify → 메일 분류 · 업무 · 확인 칸 저장 → done.

- 엑사원 한 통이 수십 초라 요청 안에서 기다리지 않는다. 작업을 꺼낸 표시(running · started_at)를 먼저 커밋하고, ai를
  부르는 동안은 DB를 잡고 있지 않는다.
- ai가 꺼져 있거나(unavailable) 제한 시간을 넘으면(timeout) 실패로 세지 않고 queued로 남긴다. 화면에는 '분류 대기 N건'으로
  보인다(구조도 12절 #17). 작업자는 실패 뒤 INTERVAL만큼 쉰다(jobs/worker.py).
- 형식이 다른 응답 · 본문을 못 가져옴 · 그 밖의 예외는 실패로 센다. 3번이면 failed. failed는 retry()로 다시 queued가 된다.
  메일은 지우지 않고 '실패 N건'으로 보여 준다(누락 0).
- ai가 모델 실패로 규칙 결과만 낸 응답(fallback)도 버리지 않는다. 규칙이 찾은 할 일 · 확인 칸이 들어 있으므로
  source=rule로 저장하고 done으로 끝내되, 작업에 fallback 이유를 남겨 '엑사원 재분류 대상'으로 표시한다.
  retry(rule_only=True)로 다시 돌리면, 사용자가 손대지 않은 규칙 업무만 엑사원 결과로 바꾼다.
- running으로 오래 남은 작업(서버가 죽었거나 작업이 멈춤)은 started_at 기준으로 queued로 되살린다.
- started_at은 마지막으로 꺼낸 시각이다. 대기열로 돌아간 작업에도 남겨, 다음에는 오래 기다린 작업부터 꺼낸다.
"""
import logging
import time
from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.ai_client.client import TIMEOUT_S, AIClient, AIError
from app.ai_client.payload import build_classify_request
from app.core.clock import now
from app.core.config import get_settings
from app.mail.body import fetch_body
from app.models import Account, ClassifyJob, Mail, MailCheck, Task, UserSettings
from app.models.mail import CHECK_REASONS
from app.services import learn

MAX_ATTEMPTS = 3
NOT_COUNTED = ("unavailable", "timeout")  # ai가 꺼져 있거나 느린 것은 메일 탓이 아니다. 시도 횟수에 세지 않는다
STALE_AFTER = timedelta(seconds=TIMEOUT_S * 2 + 60)  # ai 호출 제한 시간을 넉넉히 넘기면 멈춘 것으로 본다
NO_CLASSIFY_SENDERS = ("noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon")
log = logging.getLogger("app.jobs.classify")


def enqueue(db: Session, mail: Mail) -> ClassifyJob | None:
    """받은 메일만 넣는다. 자동 발송 주소(noreply 등)는 넣지 않는다(사전 필터). 이미 작업이 있으면 그대로 둔다."""
    if mail.direction != "received":
        return None
    if mail.sender.split("@", 1)[0].lower() in NO_CLASSIFY_SENDERS:
        return None
    if db.scalar(select(ClassifyJob.id).where(ClassifyJob.mail_id == mail.id)) is not None:
        return None
    job = ClassifyJob(mail_id=mail.id, status="queued", attempts=0, created_at=now())
    db.add(job)
    db.flush()
    return job


def requeue_running(db: Session) -> int:
    """서버가 죽어 running으로 남은 작업을 모두 대기열로 되돌린다. 작업자(1프로세스, BE-D10)가 시작할 때 한 번 부른다."""
    n = db.execute(update(ClassifyJob).where(ClassifyJob.status == "running")
                   .values(status="queued", started_at=None)
                   .execution_options(synchronize_session=False)).rowcount
    db.commit()
    return n


def requeue_stale(db: Session, older_than: timedelta = STALE_AFTER) -> int:
    """started_at이 older_than보다 오래된 running을 queued로 되살린다(started_at이 없는 예전 행 포함). 작업자가 쉴 때마다 부른다."""
    cut = now() - older_than
    n = db.execute(update(ClassifyJob)
                   .where(ClassifyJob.status == "running",
                          ClassifyJob.started_at.is_(None) | (ClassifyJob.started_at < cut))
                   .values(status="queued", started_at=None)
                   .execution_options(synchronize_session=False)).rowcount
    db.commit()
    return n


def _user_jobs(user_id: int):
    mine = select(Mail.id).join(Account, Mail.account_id == Account.id).where(Account.user_id == user_id)
    return ClassifyJob.mail_id.in_(mine)


def retry(db: Session, user_id: int, *, rule_only: bool = False) -> int:
    """화면의 [다시 시도]. failed를 queued로(시도 횟수 0부터). rule_only=True면 규칙 결과만 저장된 작업도 다시 돌려
    엑사원으로 재분류한다. 커밋은 부르는 쪽이 한다."""
    cond = (ClassifyJob.status == "failed")
    if rule_only:
        cond = cond | ((ClassifyJob.status == "done") & ClassifyJob.fallback.is_not(None))
    return db.execute(update(ClassifyJob).where(_user_jobs(user_id), cond)
                      .values(status="queued", attempts=0, error=None, started_at=None)
                      .execution_options(synchronize_session=False)).rowcount


def _claim(db: Session) -> ClassifyJob | None:
    """대기 작업 하나를 꺼낸다. 한 번도 꺼내지 않은 작업부터, 그다음은 마지막으로 꺼낸 지 오래된 작업부터 본다.
    제한 시간 초과는 세지 않아 계속 queued로 남으므로, 늘 느린 메일 하나가 맨 앞을 차지하면 뒤 메일이 막힌다."""
    order = (ClassifyJob.started_at.is_not(None), ClassifyJob.started_at, ClassifyJob.id)
    for job_id in db.scalars(select(ClassifyJob.id).where(ClassifyJob.status == "queued").order_by(*order)):
        got = db.execute(update(ClassifyJob).where(ClassifyJob.id == job_id, ClassifyJob.status == "queued")
                         .values(status="running", started_at=now())
                         .execution_options(synchronize_session=False)).rowcount
        if got == 1:
            db.commit()
            return db.get(ClassifyJob, job_id, populate_existing=True)  # 세션에 남은 예전 객체(queued)가 아니라 지금 값
    db.commit()
    return None


def _fail(db: Session, job: ClassifyJob, error: str) -> str:
    job.attempts += 1
    job.error = error[:500]
    job.status = "failed" if job.attempts >= MAX_ATTEMPTS else "queued"  # started_at은 마지막으로 꺼낸 시각으로 둔다(_claim 순서)
    db.commit()
    return job.status


def _defer(db: Session, job: ClassifyJob, error: str) -> str:
    """ai가 꺼져 있음 · 제한 시간 초과: 시도 횟수를 세지 않고 대기열에 남긴다(구조도 12절 #17)."""
    job.error = error[:500]
    job.status = "queued"  # started_at은 마지막으로 꺼낸 시각으로 둔다. 다음에는 다른 대기 작업이 먼저 꺼내진다(_claim)
    db.commit()
    return job.status


def _body(db: Session, mail: Mail) -> str | None:
    account = db.get(Account, mail.account_id)
    s = db.get(UserSettings, account.user_id)
    if s is not None and not s.read_body:
        return ""  # 본문 읽기 꺼짐: 제목 · 발신자로만 분류(구조도 10절)
    return fetch_body(db, mail)


def _untouched_rule_output(db: Session, mail_id: int) -> bool:
    """이 메일에 저장된 업무 · 확인 칸이 모두 규칙 결과이고 사용자가 손대지 않았는가(엑사원 재분류로 바꿔도 되는가)."""
    # 객체가 아니라 칸을 읽는다: 세션에 남은 예전 객체가 아니라 화면에서 바꾼 지금 값을 본다
    tasks = db.execute(select(Task.source, Task.status, Task.status_changed_at).where(Task.mail_id == mail_id)).all()
    if any(src != "rule" or st != "pending" or changed is not None for src, st, changed in tasks):
        return False
    check = db.execute(select(MailCheck.source, MailCheck.seen_at).where(MailCheck.mail_id == mail_id)).first()
    return check is None or (check.source == "rule" and check.seen_at is None)


def _save(db: Session, mail: Mail, result, *, replace_rule: bool) -> int:
    """분류 응답을 저장한다(#30 칸: mails.kind · lane, tasks.urgent · is_follow_up은 업무마다 복사, mail_checks).
    이미 업무 · 확인 칸이 있으면 덮어쓰지 않는다(사용자가 바꾼 상태 포함). 단, 규칙 결과만 저장됐던 메일을 엑사원으로
    다시 분류한 경우(replace_rule)에는 사용자가 손대지 않은 규칙 결과일 때만 바꾼다."""
    has_output = (db.scalar(select(Task.id).where(Task.mail_id == mail.id)) is not None
                  or db.scalar(select(MailCheck.id).where(MailCheck.mail_id == mail.id)) is not None)
    if has_output:
        if not (replace_rule and result.source == "exaone" and _untouched_rule_output(db, mail.id)):
            return 0
        db.execute(delete(Task).where(Task.mail_id == mail.id))
        db.execute(delete(MailCheck).where(MailCheck.mail_id == mail.id))
    mail.category, mail.category_source = result.category, result.source
    mail.kind, mail.lane = result.kind, result.lane
    for t in result.tasks:
        due_source = "none" if t.due_at is None else ("model" if result.source == "exaone" else "rule")
        db.add(Task(mail_id=mail.id, text=t.text, due_raw=t.due_raw, due_at=t.due_at, due_source=due_source,
                    mentioned_me=result.mentioned_me, urgent=result.urgent, is_follow_up=result.is_follow_up,
                    priority=result.priority, source=result.source, confidence=result.confidence,
                    evidence_text=t.evidence, status="pending"))
    check = next((c for c in result.checks if c.reason in CHECK_REASONS), None)  # 메일 1통에 최대 1개
    if check is not None and not result.tasks:  # 확인 칸은 할 일이 없는 메일에만(#30)
        db.add(MailCheck(mail_id=mail.id, text=check.text, reason=check.reason,
                         source="exaone" if check.source == "exaone" else "rule", evidence_text=check.evidence))
    return len(result.tasks)


def _process(db: Session, ai: AIClient, job: ClassifyJob) -> dict:
    mail = db.get(Mail, job.mail_id)
    out = {"job_id": job.id, "mail_id": mail.id}
    body = _body(db, mail)
    if body is None:
        return {**out, "status": _fail(db, job, "본문을 가져오지 못함"), "error": "body_unavailable"}
    payload = build_classify_request(db, mail, body)
    db.commit()  # ai를 부르는 동안 DB를 잡지 않는다
    started = time.monotonic()
    try:
        result = ai.classify(payload)
    except AIError as e:
        handle = _defer if e.kind in NOT_COUNTED else _fail
        return {**out, "status": handle(db, job, f"{e.kind}: {e}"), "error": e.kind}
    if result.mail_id != mail.id:
        return {**out, "status": _fail(db, job, "응답 mail_id가 다름"), "error": "bad_response"}
    n = _save(db, mail, result, replace_rule=job.fallback is not None)
    job.status, job.error, job.started_at = "done", None, None
    # 모델 실패로 규칙 결과만 저장한 것은 표시해 둔다(엑사원 재분류 대상). 엑사원 결과가 저장되면 표시를 지운다
    if result.fallback:
        job.fallback = result.fallback[:500]
    elif result.source == "exaone":
        job.fallback = None
    job.model, job.prompt_version = result.model, result.prompt_version
    job.elapsed_ms = int((time.monotonic() - started) * 1000)
    db.commit()
    out |= {"status": "done", "tasks": n}
    if job.fallback:
        out["rule_only"] = True
    if get_settings().memory_extract and result.source == "exaone":  # 문맥 기억(모델, BE-D21). 실패해도 분류 결과는 그대로다
        try:
            account = db.get(Account, mail.account_id)
            out["learned"] = len(learn.learn_context(db, account.user_id, mail, body, ai))
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
            log.exception("문맥 기억 실패(분류는 완료)")
    return out


def run_next(db: Session, ai: AIClient) -> dict | None:
    """대기 작업 하나를 처리한다. 없으면 None. 결과: {job_id, mail_id, status, tasks?, rule_only?, error?}
    처리 중 어떤 예외가 나도 running으로 남기지 않는다(실패로 세고 queued 또는 failed)."""
    job = _claim(db)
    if job is None:
        return None
    job_id, mail_id = job.id, job.mail_id
    try:
        return _process(db, ai, job)
    except Exception as e:  # noqa: BLE001 - 본문 파일 오류 · 저장 실패 등. 작업을 잃지 않는다
        db.rollback()
        log.exception("분류 작업 %s 처리 중 오류", job_id)
        job = db.get(ClassifyJob, job_id)
        return {"job_id": job_id, "mail_id": mail_id, "status": _fail(db, job, f"error: {type(e).__name__}: {e}"),
                "error": "error"}


def counts(db: Session, user_id: int) -> dict:
    """화면의 '분류 대기 N건 · 실패 N건'(누락 0: 숨기지 않는다). rule_only는 done 중 규칙 결과만 저장된 것(엑사원 재분류 대상)."""
    rows = db.execute(select(ClassifyJob.status, ClassifyJob.fallback).where(_user_jobs(user_id))).all()
    out = {k: sum(1 for s, _ in rows if s == k) for k in ("queued", "running", "done", "failed")}
    out["rule_only"] = sum(1 for s, f in rows if s == "done" and f)
    return out
