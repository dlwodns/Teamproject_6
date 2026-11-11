"""메일 분류 작업 (구조도 4 · 12절, BE-9 ai_client 사용).

흐름: 메일 저장 → enqueue()로 classify_jobs에 queued → run_next()가 하나씩 꺼내
  본문 가져오기 → 요청 만들기(기억 포함, ai_client/payload.py) → ai /classify → mails.category · tasks 저장 → done.

- 엑사원 한 통이 수십 초라 요청 안에서 기다리지 않는다. 작업을 꺼낸 표시(running)를 먼저 커밋하고, ai를 부르는 동안은
  DB를 잡고 있지 않는다.
- 실패(ai 꺼짐 · 제한 시간 · 형식 다름 · 모델 실패로 규칙만 낸 결과 · 본문을 못 가져옴)는 queued로 되돌려 다시 시도한다.
  3번 실패하면 failed. 메일은 지우지 않고 '분류 대기 · 실패 N건'으로 보여 준다(누락 0, 12절 #17).
- 이 PR에서 저장하는 칸은 main의 테이블에 있는 것뿐이다: 분류 · 업무(할 일 · 기한 · 근거 문장 · 우선순위 · 지목).
  확인 칸(checks) · 칸 배정(lane) · 업무 유형(type)은 테이블 칸이 생기면(#30 · AI-19 계약) 같은 자리에서 저장한다.
"""
import time
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.ai_client.client import AIClient, AIError
from app.ai_client.payload import build_classify_request
import logging

from app.core.clock import now
from app.core.config import get_settings
from app.mail.body import fetch_body
from app.models import Account, ClassifyJob, Mail, Task, UserSettings
from app.services import learn

MAX_ATTEMPTS = 3
NO_CLASSIFY_SENDERS = ("noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon")


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
    """서버가 죽어 running으로 남은 작업을 대기열로 되돌린다. 작업자(1프로세스, BE-D10)가 시작할 때 한 번 부른다."""
    n = db.execute(update(ClassifyJob).where(ClassifyJob.status == "running").values(status="queued")
                   .execution_options(synchronize_session=False)).rowcount
    db.commit()
    return n


def _claim(db: Session) -> ClassifyJob | None:
    for job_id in db.scalars(select(ClassifyJob.id).where(ClassifyJob.status == "queued").order_by(ClassifyJob.id)):
        got = db.execute(update(ClassifyJob).where(ClassifyJob.id == job_id, ClassifyJob.status == "queued")
                         .values(status="running").execution_options(synchronize_session=False)).rowcount
        if got == 1:
            db.commit()
            return db.get(ClassifyJob, job_id)
    db.commit()
    return None


def _fail(db: Session, job: ClassifyJob, error: str) -> str:
    job.attempts += 1
    job.error = error[:500]
    job.status = "failed" if job.attempts >= MAX_ATTEMPTS else "queued"
    db.commit()
    return job.status


def _body(db: Session, mail: Mail) -> str | None:
    account = db.get(Account, mail.account_id)
    s = db.get(UserSettings, account.user_id)
    if s is not None and not s.read_body:
        return ""  # 본문 읽기 꺼짐: 제목 · 발신자로만 분류(구조도 10절)
    return fetch_body(db, mail)


def _save(db: Session, mail: Mail, result) -> int:
    mail.category, mail.category_source = result.category, result.source
    if db.scalar(select(Task.id).where(Task.mail_id == mail.id)) is not None:
        return 0  # 이미 업무가 있으면(사용자가 바꾼 상태 포함) 덮어쓰지 않는다
    for t in result.tasks:
        due_source = "none" if t.due_at is None else ("model" if result.source == "exaone" else "rule")
        db.add(Task(mail_id=mail.id, text=t.text, due_raw=t.due_raw, due_at=t.due_at, due_source=due_source,
                    mentioned_me=result.mentioned_me, priority=result.priority, source=result.source,
                    confidence=result.confidence, evidence_text=t.evidence, status="pending"))
    return len(result.tasks)


def run_next(db: Session, ai: AIClient) -> dict | None:
    """대기 작업 하나를 처리한다. 없으면 None. 결과: {job_id, mail_id, status, tasks?, error?}"""
    job = _claim(db)
    if job is None:
        return None
    mail = db.get(Mail, job.mail_id)
    body = _body(db, mail)
    if body is None:
        return {"job_id": job.id, "mail_id": mail.id, "status": _fail(db, job, "본문을 가져오지 못함"),
                "error": "body_unavailable"}
    payload = build_classify_request(db, mail, body)
    db.commit()  # ai를 부르는 동안 DB를 잡지 않는다
    started = time.monotonic()
    try:
        result = ai.classify(payload)
    except AIError as e:
        return {"job_id": job.id, "mail_id": mail.id, "status": _fail(db, job, f"{e.kind}: {e}"), "error": e.kind}
    if result.mail_id != mail.id:
        return {"job_id": job.id, "mail_id": mail.id, "status": _fail(db, job, "응답 mail_id가 다름"),
                "error": "bad_response"}
    if result.fallback:  # 모델 실패로 규칙만 낸 결과: 할 일이 비어 있으므로 저장하지 않고 다시 시도한다
        return {"job_id": job.id, "mail_id": mail.id, "status": _fail(db, job, f"fallback: {result.fallback}"),
                "error": "fallback"}
    n = _save(db, mail, result)
    job.status, job.error = "done", None
    job.model, job.prompt_version = result.model, result.prompt_version
    job.elapsed_ms = int((time.monotonic() - started) * 1000)
    db.commit()
    out = {"job_id": job.id, "mail_id": mail.id, "status": "done", "tasks": n}
    if get_settings().memory_extract:  # 문맥 기억(모델, BE-D21). 실패해도 분류 결과는 그대로다
        try:
            account = db.get(Account, mail.account_id)
            out["learned"] = len(learn.learn_context(db, account.user_id, mail, body, ai))
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
            logging.getLogger("app.jobs.classify").exception("문맥 기억 실패(분류는 완료)")
    return out


def counts(db: Session, user_id: int) -> dict:
    """화면의 '분류 대기 N건 · 실패 N건'(누락 0: 숨기지 않는다)."""
    rows = db.execute(select(ClassifyJob.status).join(Mail, ClassifyJob.mail_id == Mail.id)
                      .join(Account, Mail.account_id == Account.id).where(Account.user_id == user_id)).scalars().all()
    return {k: rows.count(k) for k in ("queued", "running", "done", "failed")}
