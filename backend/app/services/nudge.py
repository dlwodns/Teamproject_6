"""T14 재촉 메일 (기획 detail 5 · 7절 · AI detail T14, 시연 장면 ⑦). 응답 대기(BE-13) 메일에 재촉 템플릿을 보낸다.

- 발송이라 늘 미리보기 → 확인 → 발송(D37). 미리보기(action_previews, action = T14)에 받는 사람 · 제목 · 본문을 담고,
  확인은 기존 POST /api/actions/execute로 한다(preview_id · mail_ids). 같은 미리보기는 한 번만 실행된다.
- 대상: 고른 메일 · 직전 결과(T06 응답 대기 목록, 메일 id) 또는 "답장 안 온 거 전부"(awaiting_reply). 지금도 응답 대기인
  내 보낸 요청 메일만. 실행 직전에 다시 확인해 그사이 답이 왔거나 대기를 끝낸 메일은 보내지 않는다.
- 내용은 기본 재촉 템플릿(기획 detail 7절)이다 — ai를 부르지 않는다. 템플릿 고르기 · 고치기는 BE-16(P2).
- 보낸 재촉 메일은 '요청'으로 기록한다(제목에 RE: 없음): 마지막 요청이 되어 응답 대기에서 빠지고, 기준일이 지나도 답이
  없으면 다시 뜬다(5절 '회신 뒤 재요청은 마지막 요청부터'). 재촉은 내 업무 처리가 아니라 완료 확인을 묻지 않는다(D48).
"""
import re
import uuid
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.clock import now
from app.models import Account, ActionLog, ActionPreview, Mail, User
from app.reminders import rules
from app.services.sending import SendUnknown, can_send, record_sent, send_graph
from app.services.task_status import PREVIEW_TTL, StatusError

ACTION = "T14"
SUBJECT = "[확인 요청] {원메일제목}"
BODY = "{인사}, 안녕하세요.\n\n{보낸날짜}에 보내드린 '{원메일제목}' 건 확인 부탁드립니다.\n\n감사합니다.{서명}"
PREFIX = re.compile(r"^(?:\s*\[확인 요청\]\s*)+")  # 재촉을 다시 재촉해도 머리말이 겹치지 않게 벗긴다(#205 리뷰)


def _waiting(ctx: rules.Context) -> dict[int, Mail]:
    """지금 응답 대기인 내 보낸 요청 메일(id → 메일). 판정은 BE-13과 같은 rules.awaiting_requests."""
    return {m.id: m for m in rules.awaiting_requests(ctx)}


def _fill(ctx: rules.Context, me: User | None, mail: Mail) -> dict:
    """미리보기 한 통. ctx는 미리보기 전체에서 한 번만 만든다(메일마다 다시 조회하지 않게, #205 리뷰)."""
    label = rules.recipients_label(ctx, mail)  # 카드 '받는 사람' 칸: '박지호 매니저', 여럿이면 '… 외 N명'
    first, others = label.split(" 외 ")[0], max(len(mail.recipients or []) - 1, 0)
    # 인사말은 '박지호 매니저 외 1명님'처럼 어색해지지 않게 첫 사람 + '외 N분'으로 쓴다
    greet = f"{first}님" + (f" 외 {others}분" if others else "")
    # 원메일제목: 재촉의 재촉이면 원메일이 재촉 메일이라 '[확인 요청]'을 벗긴다. 보낸날짜는 지금 재촉하는 그 메일(직전 요청)의 날짜
    values = {"수신자명": label, "인사": greet, "보낸날짜": rules.day_label(mail.sent_at.date()),
              "원메일제목": PREFIX.sub("", mail.subject or "") or "(제목 없음)",
              "서명": f"\n{me.name} 드림" if me and me.name else ""}  # 이름이 없으면 ' 드림'만 남지 않게 줄을 뺀다
    return {"mail_id": mail.id, "to": values["수신자명"], "to_addresses": list(mail.recipients or []),
            "subject": SUBJECT.format(**values), "body": BODY.format(**values).rstrip()}


def preview(db: Session, user_id: int, *, mail_ids: list[int] | None, all_waiting: bool, source: str,
            at: datetime | None = None) -> tuple[ActionPreview | None, list[dict], list[str]]:
    """(미리보기, 보낼 메일 목록, 노트). 보낼 것이 없으면 미리보기 None. 보낼 수 없는 계정(Outlook)은 StatusError(unavailable)."""
    at = at or now()
    ctx = rules.Context(db, user_id, at)
    waiting = _waiting(ctx)
    if mail_ids:
        picked = [waiting[i] for i in dict.fromkeys(mail_ids) if i in waiting]
        notes = [f"고른 메일 {len(set(mail_ids))}통 중 응답 대기 {len(picked)}통"]
    elif all_waiting:
        picked, notes = list(waiting.values()), [f"응답 대기 {len(waiting)}통 전부"]
    else:
        return None, [], []
    # 보낼 수 없는 계정(연결을 끊은 Outlook)의 메일만 빼고 나머지는 보낸다. 모두 못 보내면 unavailable(#205 리뷰)
    sendable = [m for m in picked if can_send(db.get(Account, m.account_id))]
    if picked and not sendable:
        raise StatusError("unavailable", "이 계정은 서비스 안에서 보낼 수 없습니다(Outlook 다시 연결)")
    if len(sendable) < len(picked):
        notes.append(f"연결이 끊긴 Outlook 계정 메일 {len(picked) - len(sendable)}통은 보낼 수 없어 뺐습니다")
    me = db.get(User, user_id)
    sends = [_fill(ctx, me, m) for m in sendable]
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
    db.commit()  # 선점을 확정하고 쓰기 잠금을 놓는다 — 아래 Outlook 발송(메일당 수 초)을 기다리는 동안 다른 쓰기가 막히지 않게
    waiting = _waiting(rules.Context(db, owner, at))  # 발송 직전 재확인: 그사이 답이 왔거나 대기를 끝냈으면 보내지 않는다
    by_id = {s["mail_id"]: s for s in p.params_json["sends"]}
    out = {"sent_mail_ids": [], "skipped": []}
    for mid in picked:
        orig = waiting.get(mid)
        if orig is None:
            out["skipped"].append({"mail_id": mid, "reason": "no_longer_waiting"})
            continue
        s = by_id[mid]
        account = db.get(Account, orig.account_id)
        if account.provider == "outlook_graph":
            from app.mail import graph

            # ponytail: 새 메일로 보낸다(Outlook에선 새 대화). 기록은 원 대화로 남겨 응답 대기 계산을 잇는다. 이 재촉에 온 답은
            # Outlook 대화 id가 달라 응답으로 세지 못한다 — 내 보낸 메일에 전체 답장으로 잇는 동작을 Graph 문서로 확인한 뒤 바꾼다
            with graph.account_lock(account.id):  # 보내기 ~ 기록 커밋 사이에 보낸 편지함 동기화가 끼지 않게
                try:
                    draft = send_graph(db, account, "new", content=s["body"], to=s["to_addresses"], subject=s["subject"])
                except SendUnknown:
                    out["skipped"].append({"mail_id": mid, "reason": "send_unknown"})  # 나갔을 수 있다 — 보낸 편지함 확인
                    continue
                except graph.GraphError:  # 거절 · 연결 끊김. 이 메일만 건너뛰고 나머지는 보낸다
                    out["skipped"].append({"mail_id": mid, "reason": "send_failed"})
                    continue
                sent = record_sent(db, account, recipients=s["to_addresses"], subject=s["subject"],
                                   conversation_id=orig.conversation_id, category="요청", at=at, source_id=draft.get("id"))
                db.commit()
            out["sent_mail_ids"].append(sent.id)
            continue
        sent = record_sent(db, account, recipients=s["to_addresses"], subject=s["subject"],
                           conversation_id=orig.conversation_id, category="요청", at=at)
        out["sent_mail_ids"].append(sent.id)
    if out["sent_mail_ids"]:  # 외부 발송은 되돌릴 수 없어도 기록은 남긴다(기록 탭 · 감사, #205 리뷰). before_json 없음 = 되돌리기 불가
        db.add(ActionLog(user_id=owner, action=ACTION, source=p.params_json.get("source") or "ui", preview_id=p.preview_id,
                         confirmed=True, affected_ids=[], before_json=None, created_at=at,
                         params_json={"kind": "nudge", "mail_ids": [m for m in picked if m in waiting],
                                      "sent_mail_ids": out["sent_mail_ids"]}))
        db.flush()
    return out
