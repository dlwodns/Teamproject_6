"""메일을 저장한 직후 할 일을 한곳에 모은다 (PL-16). 메일 저장 경로(Outlook 동기화 BE-7 · 더미 적재)는 이것만 부른다.

1. 메일 기억하기(설정을 켰을 때만, learn.py) — 본문은 저장하지 않으므로 이때 한 번 본다.
2. 분류 대기열에 넣기(받은 메일만, jobs/classify.py) — 분류는 작업자가 나중에 한다.
3. 보낸 메일은 리마인더 신호 대기열에 넣기(REMINDER_SIGNALS=1일 때만, jobs/signals.py) — 스케줄러 틱이 ai /signals를 부른다.
시연 시드(app/dev/seed.py)는 정답 라벨로 업무를 바로 채우므로 1만 부른다.
"""
from sqlalchemy.orm import Session

from app.jobs import classify, signals
from app.models import ActionLog, ClassifyJob, Mail
from app.services import learn


def after_mail_saved(db: Session, user_id: int, mail: Mail, body: str | None) -> tuple[list[ActionLog], ClassifyJob | None]:
    learn.fill_author(db, mail, body)  # 이 메일을 쓴 사람(AI-44)
    logs = learn.on_mail_saved(db, user_id, mail, body)
    job = classify.enqueue(db, mail)
    signals.enqueue(db, mail)  # 보낸 메일의 내 약속 → 리마인더 신호 대기열(BE-12, 켜져 있을 때만)
    return logs, job
