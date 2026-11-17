"""T14 재촉 메일 (기획 detail 5 · 7절 · AI detail T14, 시연 장면 ⑦). 응답 대기(BE-13) 메일에 재촉 템플릿을 보낸다.

- 발송이라 늘 미리보기 → 확인 → 발송(D37). 미리보기(action_previews, action = T14)에 받는 사람 · 제목 · 본문을 담고,
  확인은 기존 POST /api/actions/execute로 한다(preview_id · mail_ids). 같은 미리보기는 한 번만 실행된다.
- 대상: 고른 메일 · 직전 결과(T06 응답 대기 목록, 메일 id) 또는 "답장 안 온 거 전부"(awaiting_reply). 지금도 응답 대기인
  내 보낸 요청 메일만. 실행 직전에 다시 확인해 그사이 답이 왔거나 대기를 끝낸 메일은 보내지 않는다.
- 내용은 기본 재촉 템플릿(기획 detail 7절)이다 — ai를 부르지 않는다. 템플릿 고르기 · 고치기는 BE-16(P2).
- 보낸 재촉 메일은 '요청'으로 기록한다(제목에 RE: 없음): 마지막 요청이 되어 응답 대기에서 빠지고, 기준일이 지나도 답이
  없으면 다시 뜬다(5절 '회신 뒤 재요청은 마지막 요청부터'). 재촉은 내 업무 처리가 아니라 완료 확인을 묻지 않는다(D48).
"""
import uuid
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.clock import now
from app.models import Account, ActionPreview, Mail, User
from app.reminders import rules
from app.services.sending import can_send, record_sent
from app.services.task_status import PREVIEW_TTL, StatusError

ACTION = "T14"
SUBJECT = "[확인 요청] {원메일제목}"
BODY = "{수신자명}님, 안녕하세요.\n\n{보낸날짜}에 보내드린 '{원메일제목}' 건 확인 부탁드립니다.\n\n감사합니다.\n{내이름} 드림"


def _waiting(db: Session, user_id: int, at: datetime) -> dict[int, Mail]:
    """지금 응답 대기인 내 보낸 요청 메일(id → 메일). 판정은 BE-13과 같은 rules.awaiting_requests."""
    return {m.id: m for m in rules.awaiting_requests(rules.Context(db, user_id, at))}


def _fill(db: Session, user_id: int, mail: Mail, at: datetime) -> dict:
    ctx = rules.Context(db, user_id, at)
    me = db.get(User, user_id)
    values = {"수신자명": rules.recipients_label(ctx, mail), "보낸날짜": rules.day_label(mail.sent_at.date()),
              "원메일제목": mail.subject or "(제목 없음)", "내이름": (me.name if me and me.name else "")}
    return {"mail_id": mail.id, "to": values["수신자명"], "to_addresses": list(mail.recipients or []),
            "subject": SUBJECT.format(**values), "body": BODY.format(**values).rstrip()}


def preview(db: Session, user_id: int, *, mail_ids: list[int] | None, all_waiting: bool, source: str,
            at: datetime | None = None) -> tuple[ActionPreview | None, list[dict], list[str]]:
    """(미리보기, 보낼 메일 목록, 노트). 보낼 것이 없으면 미리보기 None. 보낼 수 없는 계정(Outlook)은 StatusError(unavailable)."""
    at = at or now()
    waiting = _waiting(db, user_id, at)
    if mail_ids:
        picked = [waiting[i] for i in dict.fromkeys(mail_ids) if i in waiting]
        notes = [f"고른 메일 {len(set(mail_ids))}통 중 응답 대기 {len(picked)}통"]
    elif all_waiting:
        picked, notes = list(waiting.values()), [f"응답 대기 {len(waiting)}통 전부"]
    else:
        return None, [], []
    for m in picked:
        if not can_send(db.get(Account, m.account_id)):
            raise StatusError("unavailable", "이 계정은 아직 서비스 안에서 보낼 수 없습니다(Outlook 연결 뒤)")
    sends = [_fill(db, user_id, m, at) for m in picked]
    if not sends:
        return None, [], notes
    p = ActionPreview(preview_id=str(uuid.uuid4()), user_id=user_id, action=ACTION, target_ids=[s["mail_id"] for s in sends],
                      params_json={"kind": "nudge", "source": source, "sends": sends}, created_at=at,
                      expires_at=at + PREVIEW_TTL)
    db.add(p)
    db.flush()
    return p, sends, notes


def execute(db: Session, preview_id: str, *, owner: int, mail_ids: list[int] | None = None) -> dict:
    """확인한 재촉 메일을 보낸다. mail_ids: 확인 카드에서 남긴 메일(미리보기 대상 안에서 줄이기만). 없으면 전부.
    결과 {sent_mail_ids: 새로 보낸 메일, skipped: [{mail_id, reason}]}. 커밋은 부르는 쪽이 한다."""
    p = db.get(ActionPreview, preview_id)
    if p is None or p.user_id != owner or p.action != ACTION:
        raise StatusError("not_found", "없는 미리보기입니다")
    if p.used_at is not None:
        raise StatusError("conflict", "이미 실행한 미리보기입니다")
    at = now()
    if p.expires_at < at:
        raise StatusError("conflict", "만료된 미리보기입니다. 다시 미리보기를 받아 주세요")
    if mail_ids is not None:
        picked = list(dict.fromkeys(mail_ids))
        if not picked or not set(picked) <= set(p.target_ids):
            raise StatusError("invalid", "미리보기 대상 안에서 1통 이상 골라 주세요")
    else:
        picked = list(p.target_ids)
    claimed = db.execute(update(ActionPreview).where(ActionPreview.preview_id == preview_id, ActionPreview.used_at.is_(None))
                         .values(used_at=at).execution_options(synchronize_session=False)).rowcount
    if claimed != 1:  # 같은 미리보기가 거의 동시에 두 번 와도 한 번만 보낸다(BE-4와 같은 방식)
        raise StatusError("conflict", "이미 실행한 미리보기입니다")
    waiting = _waiting(db, owner, at)  # 발송 직전 재확인: 그사이 답이 왔거나 대기를 끝냈으면 보내지 않는다
    by_id = {s["mail_id"]: s for s in p.params_json["sends"]}
    out = {"sent_mail_ids": [], "skipped": []}
    for mid in picked:
        orig = waiting.get(mid)
        if orig is None:
            out["skipped"].append({"mail_id": mid, "reason": "no_longer_waiting"})
            continue
        s = by_id[mid]
        sent = record_sent(db, db.get(Account, orig.account_id), recipients=s["to_addresses"], subject=s["subject"],
                           conversation_id=orig.conversation_id, category="요청", at=at)
        out["sent_mail_ids"].append(sent.id)
    return out
