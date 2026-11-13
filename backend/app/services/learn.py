"""메일 기억하기 — 설정을 켜면 사내 메일에서 업무 사실을 알아내 '에이전트가 아는 것'에 넣는다 (PL-16, 11-11 결정).

결정(문규남 11-11): 대상이 사내 메일이므로 항목마다 묻지 않는다. 설정 '메일 기억하기'를 켜면 바로 넣고, 끄면 아무것도
하지 않는다. 기본은 켜짐이다(11-11 결정 — D50 결정 8 ①'기본 꺼짐'의 예외: 앱 안의 기억만 바꾸고, 밖으로 아무것도
보내지 않으며, 모두 보이고 되돌릴 수 있다). 넣은 것은 모두 기록 탭에 '자동 · 메일에서 알게 됨'으로 남고,
'에이전트가 아는 것'에서 "메일에서 알게 됐어요"로 보이며, 지우거나 되돌릴 수 있다.

지금 알아내는 것 — 규칙(모델 호출 없음, on_mail_saved):
1. 보낸 사람의 직급 — 서명 블록(E-Mail 줄이 보낸 사람 주소와 같은 블록)의 "이름 직급" 줄에서.
   그 직급이 내 직급보다 높으면 상급자로 표시한다(직급 순서는 RANK).
2. 내가 속한 배포 목록 — 받은 메일의 받는 사람 · 참조에 내 주소가 없고 주소가 하나뿐이면, 그 주소로 받은 것이다.
   숨은참조로 받은 1:1 메일도 같은 모양이라 동료 개인 주소가 목록으로 들어갈 수 있다(#44 리뷰). 그래서
   ① 사람 주소(연락처에 있거나, 그 주소에서 나에게 메일을 보낸 적이 있음)는 넣지 않고
   ② 서로 다른 보낸 사람 LIST_MIN_SENDERS명 이상에게서 같은 모양으로 받았을 때만 넣는다.

지키는 것:
- 사내 메일만 본다(보낸 사람 도메인이 내 계정 도메인과 같을 때).
- 사용자가 직접 바꾼 항목은 덮어쓰지 않는다(그 연락처 · 내 정보를 화면 · 말로 바꾸거나, 메일에서 알게 된 것을
  되돌린 기록이 있으면 그 항목은 더 배우지 않는다).
- 상급자 표시를 끄지 않는다(켜기만). 직급은 비어 있을 때만 채운다.
문맥 기억 — 모델(learn_context, BE-D21): 메일 문장을 ai `/memory/extract`로 읽혀 보낸 사람의 맡은 일 · 소속.
  엑사원을 연결하고 `MEMORY_EXTRACT=1`이면 분류 작업자가 분류를 마친 뒤 부른다.

- 설정 '본문 읽기'(settings.read_body)가 꺼져 있으면 본문을 보는 서명 학습을 하지 않는다(받는 사람만 본다).
- 메일 본문은 저장하지 않는다(구조도 10절). 메일을 저장하는 그때 한 번 본다 — `on_mail_saved()`를 메일 저장 경로
  (시드 · Outlook 동기화 BE-7 · 더미 적재)에서 부른다.
"""
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, ActionLog, AgentSettings, Contact, Mail, User, UserSettings
from app.services import memory

# 기록의 source. '말로 시킨 행동'(agent_rule · agent_model) 수와 섞이지 않게 따로 둔다(#44 리뷰).
# 규칙으로 알았는지 · 모델로 알았는지는 params_json.learned_by(rule · model)에 남긴다
SOURCE = "mail_learn"
VIA = memory.MAIL_LEARN
LIST_MIN_SENDERS = 2

# 높을수록 윗사람. LG CNS 직급(사원 ~ 수석) · 직책(팀장 ~ 사업부장) · 임원. 순서가 애매한 값은 넣지 않는다
RANK = {"사원": 1, "주임": 1, "선임": 2, "대리": 2, "과장": 3, "책임": 3, "차장": 4, "부장": 5, "수석": 5,
        "파트장": 5, "팀장": 6, "그룹장": 6, "실장": 7, "사업단장": 7, "담당": 8, "본부장": 8, "사업부장": 9,
        "상무": 9, "전무": 10, "부사장": 11, "사장": 12, "대표": 12, "CEO": 12}
NAME_POS = re.compile(r"^\s*([가-힣]{2,4})\s+(" + "|".join(sorted(RANK, key=len, reverse=True)) + r")(?:님)?\s*(?:/.*)?$")
EMAIL_LINE = re.compile(r"^\s*E-?mail\s*[:：]\s*(\S+@\S+)\s*$", re.IGNORECASE)


def enabled(db: Session, user_id: int) -> bool:
    s = db.get(AgentSettings, user_id)
    return True if s is None else bool(s.learn_from_mail)  # 행이 없으면 기본값(켜짐)


def set_enabled(db: Session, user_id: int, on: bool) -> AgentSettings:
    from app.core.clock import now

    s = db.get(AgentSettings, user_id)
    if s is None:
        s = AgentSettings(user_id=user_id, learn_from_mail=on, updated_at=now())
        db.add(s)
    else:
        s.learn_from_mail, s.updated_at = on, now()
    db.flush()
    return s


def _domain(address: str) -> str:
    return address.rsplit("@", 1)[-1].strip().lower()


def reads_body(db: Session, user_id: int) -> bool:
    s = db.get(UserSettings, user_id)
    return s is None or bool(s.read_body)


def signature(body: str, sender: str) -> tuple[str, str] | None:
    """서명에서 (이름, 직급). E-Mail 줄이 보낸 사람 주소와 같은 블록의 바로 위 4줄 안에서 찾는다.
    인용된 앞 메일의 서명(다른 사람 주소)은 쓰지 않는다."""
    lines = body.splitlines()
    for i, line in enumerate(lines):
        m = EMAIL_LINE.match(line)
        if not m or m.group(1).strip().lower() != sender.lower():
            continue
        for j in range(i - 1, max(-1, i - 5), -1):
            if hit := NAME_POS.match(lines[j]):
                return hit.group(1), hit.group(2)
    return None


def _touched_by_user(db: Session, user_id: int, target: str) -> bool:
    """그 항목을 사용자가 직접 바꾼 기록(메일에서 알게 된 것 말고)이 있는가.
    사용자가 메일에서 알게 된 것을 되돌린 것도 직접 바꾼 것이다(거절한 것을 다음 메일에서 다시 넣지 않는다)."""
    for x in db.scalars(select(ActionLog).where(ActionLog.user_id == user_id)):
        p = x.params_json or {}
        if p.get("target") == target and p.get("via") != VIA:
            return True
    return False


def _learn_sender(db: Session, user_id: int, me: User, mail: Mail, body: str) -> ActionLog | None:
    sig = signature(body, mail.sender)
    if sig is None:
        return None
    name, position = sig
    contact = db.scalar(select(Contact).where(Contact.user_id == user_id,
                                              func.lower(Contact.email) == mail.sender.strip().lower()))
    if contact is None:  # 처음 보는 사람은 연락처만 만든다(기억 항목이 아니라 기록하지 않는다)
        contact = Contact(user_id=user_id, email=mail.sender.lower(), name=name)
        db.add(contact)
        db.flush()
    target = f"contact:{contact.id}"
    if _touched_by_user(db, user_id, target):
        return None
    changes = {}
    if not contact.position:
        changes["position"] = position
    my_rank, their_rank = RANK.get(me.position or ""), RANK[position]
    superior = my_rank is not None and their_rank > my_rank and not contact.is_superior
    if superior:
        changes["is_superior"] = True
    if not changes:
        return None
    what = f"{name} {position}님" + ("을 상급자로" if superior else "의 직급을")
    return memory.update_person(db, user_id, contact.id, source=SOURCE, via=VIA, **changes,
                                extra={"text": f"메일 서명에서 {what} 알게 됐어요", "mail_id": mail.id,
                                       "learned_by": "rule"})


def _only_other(mail: Mail, mine: set[str]) -> str | None:
    """받는 사람 · 참조가 (보낸 사람을 빼고) 주소 하나뿐이고 내 주소가 없으면 그 주소."""
    to = {a.strip().lower() for a in (mail.recipients or []) + (mail.cc or []) if a and a.strip()}
    to.discard(mail.sender.strip().lower())
    if len(to) != 1 or mine & to:
        return None
    return next(iter(to))


def _is_person(db: Session, user_id: int, address: str) -> bool:
    """사람 주소인가: 연락처에 있거나, 그 주소에서 나에게 메일을 보낸 적이 있다(배포 목록은 보내는 쪽이 아니다)."""
    # 주소는 받은 그대로(대문자 섞임) 저장되므로 소문자로 맞춰 비교한다. address는 _only_other가 소문자로 준다
    if db.scalar(select(Contact.id).where(Contact.user_id == user_id, func.lower(Contact.email) == address)) is not None:
        return True
    accounts = select(Account.id).where(Account.user_id == user_id)
    return db.scalar(select(Mail.id).where(Mail.account_id.in_(accounts), func.lower(Mail.sender) == address)
                     .limit(1)) is not None


def _senders_via(db: Session, user_id: int, mine: set[str], address: str) -> set[str]:
    """이 주소 하나로만 받은 사내 메일의 서로 다른 보낸 사람."""
    accounts = select(Account.id).where(Account.user_id == user_id)
    rows = db.scalars(select(Mail).where(Mail.account_id.in_(accounts), Mail.direction == "received"))
    return {m.sender.strip().lower() for m in rows if _only_other(m, mine) == address}


def _learn_list(db: Session, user_id: int, mine: set[str], my_domain: str, mail: Mail) -> ActionLog | None:
    address = _only_other(mail, mine)
    if address is None or _domain(address) != my_domain:
        return None
    target = f"me:{user_id}"
    current = memory.snapshot(db, user_id, target)["mailing_lists"]
    if address in [x["address"] for x in current] or _touched_by_user(db, user_id, target):
        return None
    if _is_person(db, user_id, address) or len(_senders_via(db, user_id, mine, address)) < LIST_MIN_SENDERS:
        return None  # 숨은참조로 받은 1:1 메일일 수 있다. 사람 주소는 넣지 않고, 여러 사람에게서 확인된 뒤에만 넣는다
    kind = memory.list_kind(address)
    word = {"role": "직책", "team": "팀", "all": "전사"}[kind]
    return memory.update_me(db, user_id, mailing_lists=current + [{"address": address, "kind": kind}], source=SOURCE,
                            via=VIA, extra={"text": f"메일에서 내가 {address}({word} 목록)에 속한 것을 알게 됐어요",
                                            "mail_id": mail.id, "learned_by": "rule"})


def on_mail_saved(db: Session, user_id: int, mail: Mail, body: str | None) -> list[ActionLog]:
    """메일을 저장한 직후 부른다(같은 트랜잭션). 설정이 꺼져 있거나 사외 메일 · 보낸 메일이면 아무것도 하지 않는다.
    커밋은 부르는 쪽이 한다."""
    if mail.direction != "received" or not enabled(db, user_id):
        return []
    me = db.get(User, user_id)
    accounts = db.scalars(select(Account.email).where(Account.user_id == user_id)).all()
    mine = {a.lower() for a in accounts}
    my_domains = {_domain(a) for a in accounts}
    if _domain(mail.sender) not in my_domains:
        return []  # 사내 메일만
    logs = []
    if body and reads_body(db, user_id) and (log := _learn_sender(db, user_id, me, mail, body)):
        logs.append(log)
    account_domain = _domain(next(a for a in accounts if _domain(a) == _domain(mail.sender)))
    if log := _learn_list(db, user_id, mine, account_domain, mail):
        logs.append(log)
    return logs


# ---------- 문맥 기억(모델) — BE-D21 ----------

def learn_context(db: Session, user_id: int, mail: Mail, body: str, ai) -> list[ActionLog]:
    """메일 문장을 ai `/memory/extract`로 읽혀 보낸 사람의 맡은 일 · 소속을 기억한다(모델을 연결하고 MEMORY_EXTRACT=1일 때
    분류 작업자가 부른다). 규칙 학습과 같은 선을 지킨다: 설정이 켜져 있을 때 · 사내 메일만 · 사용자가 직접 바꾸거나 되돌린
    연락처는 건드리지 않음 · 근거 문장이 본문에 있는 사실만(ai가 거름). ai가 실패하면 아무것도 바꾸지 않는다."""
    from app.ai_client.client import AIError

    if mail.direction != "received" or not body.strip() or not enabled(db, user_id) or not reads_body(db, user_id):
        return []
    me = db.get(User, user_id)
    accounts = db.scalars(select(Account.email).where(Account.user_id == user_id)).all()
    if _domain(mail.sender) not in {_domain(a) for a in accounts}:
        return []
    email = mail.sender.strip().lower()
    contact = db.scalar(select(Contact).where(Contact.user_id == user_id, func.lower(Contact.email) == email))
    if contact is not None and _touched_by_user(db, user_id, f"contact:{contact.id}"):
        return []
    account = db.get(Account, mail.account_id)
    payload = {"mail_id": mail.id, "from": mail.sender, "sender_name": contact.name if contact else None,
               "subject": mail.subject or "", "body": body,
               "owner": {"email": account.email, "name": me.name, "position": me.position, "team": me.department}}
    try:
        result = ai.extract_memory(payload)
    except AIError:
        return []
    if result.mail_id != mail.id or not result.facts:
        return []
    if contact is None:
        contact = Contact(user_id=user_id, email=email)
        db.add(contact)
        db.flush()
    current = memory.snapshot(db, user_id, f"contact:{contact.id}")["facts"]
    changes = {f.kind: {"value": f.value, "evidence": f.evidence, "mail_id": mail.id}
               for f in result.facts if current.get(f.kind, {}).get("value") != f.value}
    if not changes:
        return []
    name = contact.name or email.split("@")[0]
    said = " · ".join(f"{memory.FACT_LABEL[k]}({v['value']})" for k, v in changes.items())
    log = memory.update_person(db, user_id, contact.id, facts=changes, source=SOURCE, via=VIA,
                               extra={"text": f"메일에서 {name}님의 {said}을 알게 됐어요", "mail_id": mail.id,
                                      "learned_by": "model", "prompt_version": result.prompt_version})
    return [log] if log else []
