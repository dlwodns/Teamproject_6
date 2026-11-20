"""리마인더 신호 받기 (BE-12 · AI-24, 명세 reminders.md 8절) — ai `/signals`를 부르고 commitments · reminder_signals에 넣는다.

- 켜는 값: `REMINDER_SIGNALS=1`(기본 꺼짐). 엑사원을 한 번 더 부르는 일이라 문맥 기억(MEMORY_EXTRACT)처럼 ai를 연결한 뒤 켠다.
- 언제 부르나: 분류가 끝난 받은 메일(jobs/classify.py 한 줄)과 저장된 보낸 메일(services/ingest.py 한 줄).
  받은 메일은 그 대화에 미처리 업무가 있거나 내가 보낸 메일이 있을 때만 부른다. 명세는 '미처리 업무가 있을 때'인데, 상대 약속
  ("보내 드릴게요")은 대개 내 요청에 대한 답장이라 업무가 없는 대화에서 나오므로 '내가 보낸 메일이 있는 대화'를 더했다(BE-D32).
- 실패 규칙(AI-D19와 같음): quota는 시도로 세지 않고 다음에 · model_failed · bad_output은 시도로 세어 3번까지 · empty_body는 다시
  부르지 않음 · 연결 실패 · 제한 시간은 queued로 남김(ai 꺼짐) · ai에 /signals가 없음(404)은 skipped(조용히 건너뜀).
  다시 부르기는 스케줄러 틱이 run_pending으로 한다. 신호가 없어도 리마인더의 규칙 유형은 그대로 돈다.
- 코드는 형식만 다시 본다: 근거의 줄 하나라도 본문에 없으면 버리고(비교는 ai와 같게 NFKC · 보이지 않는 글자 · 공백을 무시한다.
  ai는 인용을 뗀 본문에서 찾으므로 인용까지 든 본문 전체와 비교하는 여기가 더 엄격하지 않다), task_id는 보낸 open_tasks 안의 것만, 약속의 who는 메일 방향으로 정한다.
- 개인정보(BE-6 · D53): 분류 · 기억 추출과 같이 보내기 전에 가리고(privacy.masker_for) 응답은 되돌린 뒤 근거를 원문과 비교한다.
  설정 '메일 본문 읽기'(read_body)가 꺼져 있으면 이 메일 · 앞 메일 본문을 모두 비워 보낸다(제목 · 주소만, 구조도 10절).
"""
import logging
import os
import re
import threading
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import privacy
from app.ai_client.client import AIClient, AIError
from app.core.clock import now
from app.mail.body import fetch_body
from app.models import Account, Commitment, Mail, ReminderSignal, SignalCheck, Task, User
from app.services.learn import reads_body

log = logging.getLogger("app.jobs.signals")
MAX_ATTEMPTS = 3
THREAD_MAX = 5
THREAD_CHARS = 400
PENDING_PER_TICK = 5  # 틱마다 다시 부르는 수(엑사원 1통 약 30초)
COUNTED = ("model_failed", "bad_output")
_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"))  # ai pipeline/signals.py와 같다
_inflight: set[int] = set()  # 지금 ai를 부르고 있는 메일. 분류 작업자와 스케줄러 틱이 같은 메일을 함께 부르지 않게(단일 프로세스, BE-D10)
_inflight_lock = threading.Lock()


def enabled() -> bool:
    return os.environ.get("REMINDER_SIGNALS", "").strip().lower() in ("1", "on", "true")


def _plain(text: str) -> str:
    """비교용(ai와 같게): 보이지 않는 글자를 지우고 NFKC로 맞춘 뒤 공백을 모두 뺀다."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", (text or "").translate(_INVISIBLE)))


def grounded(evidence: str | None, body: str) -> bool:
    """근거의 줄마다 본문에 있는가. ai는 떨어진 문장들을 줄바꿈으로 이어 근거로 준다(AI-D14 · AI-D20)."""
    plain = _plain(body)
    lines = [_plain(x) for x in (evidence or "").split("\n")]
    lines = [x for x in lines if x]
    return bool(lines) and all(x in plain for x in lines)


def _account(db: Session, mail: Mail) -> Account:
    return db.get(Account, mail.account_id)


def _thread(db: Session, mail: Mail) -> list[Mail]:
    if not mail.conversation_id:
        return []
    return list(db.scalars(select(Mail).where(Mail.account_id == mail.account_id, Mail.conversation_id == mail.conversation_id,
                                              Mail.id != mail.id, Mail.sent_at <= mail.sent_at)
                          .order_by(Mail.sent_at, Mail.id)))


def _open_tasks(db: Session, mail: Mail, thread: list[Mail]) -> list[Task]:
    ids = [m.id for m in thread if m.direction == "received"]
    if not ids:
        return []
    return list(db.scalars(select(Task).where(Task.mail_id.in_(ids), Task.status.in_(("pending", "snoozed")))
                          .order_by(Task.id)))


def should_call(db: Session, mail: Mail) -> bool:
    """보낸 메일은 늘, 받은 메일은 대화에 미처리 업무나 내가 보낸 메일이 있을 때만(모델 호출 줄이기)."""
    if mail.direction == "sent":
        return True
    thread = _thread(db, mail)
    return bool(_open_tasks(db, mail, thread)) or any(m.direction == "sent" for m in thread)


def build_request(db: Session, mail: Mail, body: str) -> tuple[dict, list[Task]]:
    account = _account(db, mail)
    user = db.get(User, account.user_id)
    thread = _thread(db, mail)
    tasks = _open_tasks(db, mail, thread)
    allow = reads_body(db, account.user_id)
    prev = []
    for m in thread[-THREAD_MAX:]:
        text = ""
        if allow:  # 본문 읽기 꺼짐이면 앞 메일 본문도 가져오지 않는다
            try:
                text = fetch_body(db, m) or ""
            except Exception:  # noqa: BLE001 - 앞 메일 본문은 없어도 된다
                text = ""
        prev.append({"sender": m.sender, "sent_at": m.sent_at, "subject": m.subject or "", "body": text[:THREAD_CHARS]})
    return {
        "mail_id": mail.id,
        "mail": {"direction": mail.direction, "sender": mail.sender, "recipients": list(mail.recipients or []),
                 "cc": list(mail.cc or []), "subject": mail.subject or "", "body": body, "sent_at": mail.sent_at},
        "me": {"email": account.email, "name": user.name if user else None},
        "thread": prev,
        "open_tasks": [{"task_id": t.id, "text": t.text, "due_at": t.due_at} for t in tasks],
    }, tasks


def save(db: Session, mail: Mail, body: str, result, task_ids: set[int]) -> dict:
    """응답을 저장한다. 형식이 맞지 않는 신호는 버리고 센다. 커밋은 부르는 쪽이 한다."""
    ok = lambda ev: grounded(ev, body)  # noqa: E731 - 근거는 본문에 글자 그대로(줄마다, 공백 · 보이지 않는 글자 · 전각은 느슨하게)
    at, kept, dropped = now(), {"commitments": 0, "due_changes": 0, "resolved": 0, "question": 0}, 0
    who = "me" if mail.direction == "sent" else "them"
    for c in result.commitments:
        if not ok(c.evidence):
            dropped += 1
            continue
        db.add(Commitment(mail_id=mail.id, who=who, text=c.text, due_raw=c.due_raw, due_at=c.due_at,
                          evidence_text=c.evidence, status="open", source="exaone", created_at=at))
        kept["commitments"] += 1
    for d in result.due_changes:
        if d.task_id not in task_ids or not ok(d.evidence):
            dropped += 1
            continue
        db.add(ReminderSignal(mail_id=mail.id, task_id=d.task_id, kind="due_change", new_due_raw=d.new_due_raw,
                              new_due_at=d.new_due_at, evidence_text=d.evidence, status="open", created_at=at))
        kept["due_changes"] += 1
    for r in result.resolved:
        if r.task_id not in task_ids or not ok(r.evidence):
            dropped += 1
            continue
        db.add(ReminderSignal(mail_id=mail.id, task_id=r.task_id, kind="resolved", reason=r.reason,
                              evidence_text=r.evidence, status="open", created_at=at))
        kept["resolved"] += 1
    if result.asks_me_question and mail.direction == "received":
        db.add(ReminderSignal(mail_id=mail.id, kind="question", status="open", created_at=at))
        kept["question"] += 1
    db.flush()
    return {**kept, "dropped": dropped}


def _check(db: Session, mail: Mail) -> SignalCheck:
    row = db.scalar(select(SignalCheck).where(SignalCheck.mail_id == mail.id))
    if row is None:
        row = SignalCheck(mail_id=mail.id, status="queued", attempts=0, created_at=now())
        db.add(row)
        db.flush()
    return row


def enqueue(db: Session, mail: Mail) -> SignalCheck | None:
    """부를 대상이면 대기열에 넣는다(이미 있으면 그대로). 꺼져 있거나 대상이 아니면 None."""
    if not enabled() or not should_call(db, mail):
        return None
    return _check(db, mail)


def run(db: Session, ai: AIClient, mail: Mail, body: str | None = None) -> dict:
    """메일 한 통. 결과: {status, error?, saved?}. 커밋한다. 다른 쪽이 그 메일을 부르는 중이면 {status: running}."""
    with _inflight_lock:
        if mail.id in _inflight:
            return {"status": "running"}
        _inflight.add(mail.id)
    try:
        return _run(db, ai, mail, body)
    finally:
        with _inflight_lock:
            _inflight.discard(mail.id)


def _run(db: Session, ai: AIClient, mail: Mail, body: str | None) -> dict:
    check = _check(db, mail)
    db.refresh(check)  # 다른 세션이 방금 끝냈을 수 있다(done이면 다시 부르지 않는다)
    if check.status != "queued":
        return {"status": check.status}
    account = _account(db, mail)
    if not reads_body(db, account.user_id):
        body = ""  # 본문 읽기 꺼짐: 가져오지 않는다(ai는 빈 본문이면 empty_body → skipped)
    elif body is None:
        try:
            body = fetch_body(db, mail)
        except Exception:  # noqa: BLE001
            body = None
    if body is None:
        check.attempts += 1
        check.error, check.status = "body_unavailable", "failed" if check.attempts >= MAX_ATTEMPTS else "queued"
        db.commit()
        return {"status": check.status, "error": "body_unavailable"}
    payload, tasks = build_request(db, mail, body)
    masker = privacy.masker_for(db, account.user_id)  # 개인정보 가리기(BE-6): 보내기 전에 가리고 응답은 되돌린다
    payload = masker.mask_obj(payload)
    db.commit()  # ai를 부르는 동안 DB를 잡지 않는다
    try:
        result = ai.signals(payload)
    except AIError as e:
        check.error = f"{e.kind}: {e}"[:200]
        if e.kind == "bad_response":
            check.attempts += 1
            check.status = "failed" if check.attempts >= MAX_ATTEMPTS else "queued"
        db.commit()  # timeout · unavailable은 ai 꺼짐: 세지 않고 queued로 남는다
        return {"status": check.status, "error": e.kind}
    check.checked_at = now()
    if result is None:  # ai에 /signals가 없다(AI-24 전): 조용히 건너뛴다
        check.status, check.error = "skipped", "ai_signals_missing"
        db.commit()
        return {"status": "skipped", "error": "ai_signals_missing"}
    result = masker.unmask_model(result)  # 근거 · 약속 문장을 원래 이름 · 번호로(그다음 원문 본문과 비교한다)
    if result.fallback:
        check.error = result.fallback
        if result.fallback == "empty_body":
            check.status = "skipped"
        elif result.fallback in COUNTED:
            check.attempts += 1
            check.status = "failed" if check.attempts >= MAX_ATTEMPTS else "queued"
        else:  # quota 등: 시도로 세지 않고 다음에
            check.status = "queued"
        db.commit()
        return {"status": check.status, "error": result.fallback}
    saved = save(db, mail, body, result, {t.id for t in tasks})
    check.status, check.error = "done", None
    db.commit()
    return {"status": "done", "saved": saved}


def after_classify(db: Session, ai: AIClient, mail: Mail, body: str | None) -> dict | None:
    """분류가 끝난 받은 메일(jobs/classify.py). 실패해도 분류 결과는 그대로다."""
    try:
        if enqueue(db, mail) is None:
            return None
        return run(db, ai, mail, body)
    except Exception:  # noqa: BLE001
        db.rollback()
        log.exception("리마인더 신호 실패(분류는 완료)")
        return None


def run_pending(db: Session, ai: AIClient, limit: int = PENDING_PER_TICK) -> list[dict]:
    """대기 중인 메일을 다시 부른다(보낸 메일 · 다시 시도). 스케줄러 틱이 부른다."""
    if not enabled():
        return []
    out = []
    ids = db.scalars(select(SignalCheck.mail_id).where(SignalCheck.status == "queued")
                     .order_by(SignalCheck.checked_at.is_not(None), SignalCheck.checked_at, SignalCheck.id).limit(limit)).all()
    for mail_id in ids:
        mail = db.get(Mail, mail_id)
        if mail is None:
            continue
        r = run(db, ai, mail)
        out.append({"mail_id": mail_id, **r})
        if r.get("error") in ("unavailable", "timeout", "quota"):
            break  # ai가 꺼졌거나 한도가 찼으면 이번 틱은 그만
    return out
