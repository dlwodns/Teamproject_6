"""메일 기억하기 — 설정을 켜면 사내 메일에서 업무 사실을 알아내 '에이전트가 아는 것'에 넣는다 (PL-16, 11-11 결정).

결정(문규남 11-11): 대상이 사내 메일이므로 항목마다 묻지 않는다. 설정 '메일 기억하기'를 켜면 바로 넣고, 끄면 아무것도
하지 않는다. 기본은 켜짐이다(11-11 결정 — D50 결정 8 ①'기본 꺼짐'의 예외: 앱 안의 기억만 바꾸고, 밖으로 아무것도
보내지 않으며, 모두 보이고 되돌릴 수 있다). 넣은 것은 모두 기록 탭에 '자동 · 메일에서 알게 됨'으로 남고,
'에이전트가 아는 것'에서 "메일에서 알게 됐어요"로 보이며, 지우거나 되돌릴 수 있다.

지금 알아내는 것 — 규칙(모델 호출 없음, on_mail_saved):
1. 보낸 사람의 직급 — 서명 블록(E-Mail 줄이 보낸 사람 주소와 같은 블록)의 "이름 직급" 줄에서.
   그 직급이 내 직급보다 높으면 상급자로 표시한다(직급 순서는 RANK).
   서명이 없으면 첫인사("사업단PMO 임소희 책임입니다" · "저는 임소희입니다")에서 — 보통 자기 주소로 보내므로
   보낸 사람 주소 = 그 이름으로 연락처에 둔다(11-20, AI-44). 한 주소를 여러 사람이 쓰면 먼저 소개한 사람이 남는다.
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

from app import privacy
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
RANK_ALT = "|".join(sorted(RANK, key=len, reverse=True))
# 첫인사의 자기소개: '이름 직급입니다' · '저는 이름입니다' · '보안팀 이름입니다' · '이 팀장님, 이름입니다'.
# 앞에 아무것도 없는 '…입니다'는 '회의 안내입니다'도 이름이 되어 받지 않는다.
# ponytail: 낱말 규칙이라 '사업부 공지입니다'는 이름으로 잘못 읽는다. 잦으면 성씨 목록이나 모델로
INTRO = re.compile(rf"(?<![가-힣])([가-힣]{{2,3}})\s?({RANK_ALT})님?\s?입니다"
                   rf"|(?:저는|[가-힣][팀실부단]|PMO|,)\s?([가-힣]{{2,3}})\s?입니다")
# 첫인사 · 맺음말 규칙이 이름 자리에서 잡는 업무 · 부서 · 안내 낱말('인사 담당입니다' · '인사팀 공지입니다') — 사람 이름이 아니다(#281 리뷰)
NOT_NAME = frozenset("""인사 보안 고객 행사 요청 공지 안내 회의 기획 영업 총무 재무 회계 법무 개발 운영 품질 구매 교육 홍보 문의 확인
전달 공유 보고 업무 담당 결재 일정 자료 견적 계약 채용 감사 전략 기술 설계 시험 점검 관리 경영 사업 본부 센터 고객사 협력사
마케팅 서비스 시스템 인프라 정보 대외 대내 생산 물류 연구 디자인 사무국 사무실 비서 비서실 담당자 관리자 운영자 책임자""".split())
INTRO_LINES = 5  # 첫인사는 본문 앞 몇 줄 안에 있다(인용된 앞 메일의 소개는 보지 않는다)
# 맺음말 '문규남 드림' · '임소희 책임 올림'(본문 끝 SIGNOFF_LINES줄 안)
SIGNOFF = re.compile(rf"^\s*([가-힣]{{2,3}})\s?(?:({RANK_ALT})\s?)?(?:드림|올림)\s*$")
SIGNOFF_LINES = 4
# 이 줄부터 아래는 내가 쓴 글이 아니다: 서명 구분선 · 인용 구분선 · 인용된 앞 메일 머리(보낸 사람: · From:)
QUOTE = re.compile(r"^\s*(?:\*{5,}|-{5,}|_{5,}|-+\s*Original Message|(?:From|보낸 사람)\s*:)", re.M)
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


def intro(body: str) -> tuple[str, str | None] | None:
    """첫인사의 자기소개에서 (이름, 직급 또는 None). 빈 줄을 뺀 앞 INTRO_LINES줄만 본다."""
    head = "\n".join([x for x in body.splitlines() if x.strip()][:INTRO_LINES])
    for m in INTRO.finditer(head):
        hit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), None)
        if hit[0] not in NOT_NAME:
            return hit
    return None


def own_part(body: str) -> str:
    """보낸 사람이 이 메일에 직접 쓴 부분 — 서명 · 인용된 앞 메일(QUOTE 첫 줄)부터 아래를 뗀다."""
    return QUOTE.split(body, maxsplit=1)[0]


def author(body: str, sender: str) -> tuple[str, str | None] | None:
    """이 메일을 쓴 사람 (이름, 직급 또는 None) — 첫인사의 자기소개 → 서명(보낸 사람 주소 줄) → 맺음말 순(AI-44).
    한 주소를 여러 사람이 쓰거나(공용 · 시험 주소) 연락처에 없는 사람이어도 메일마다 쓴 사람을 안다."""
    own = own_part(body)
    if hit := intro(own) or signature(body, sender):
        return hit
    for line in [x for x in own.splitlines() if x.strip()][-SIGNOFF_LINES:]:
        if (m := SIGNOFF.match(line)) and m.group(1) not in NOT_NAME:
            return m.group(1), m.group(2)
    return None


def fill_author(db: Session, mail: Mail, body: str | None) -> None:
    """메일의 쓴 사람 칸을 채운다(아직 안 봤을 때만). 찾지 못하면 ''(본 것으로 표시). 본문 읽기가 꺼져 있으면 보지 않는다.
    메일을 받을 때(ingest)와 본문을 가져올 때마다(app/mail/body.py) 부른다 — 예전에 받은 메일도 본문을 한 번 보면 채워진다.
    커밋은 부르는 쪽이 한다."""
    if mail.author_name is not None or mail.direction != "received" or body is None:
        return
    account = db.get(Account, mail.account_id)
    if account is None or not reads_body(db, account.user_id):
        return
    hit = author(body, mail.sender)
    mail.author_name, mail.author_position = (hit[0], hit[1]) if hit else ("", None)


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
    said = "메일 서명에서"
    if sig is None and (sig := author(body, mail.sender)) is not None:
        said = "메일 첫인사에서"  # 첫인사 · 맺음말은 낱말 규칙이라 서명(보낸 주소 줄)보다 덜 확실 — 상급자 표시는 하지 않는다
    if sig is None:
        return None
    name, position = sig
    contact = db.scalar(select(Contact).where(Contact.user_id == user_id,
                                              func.lower(Contact.email) == mail.sender.strip().lower()))
    if contact is None:  # 처음 보는 사람은 연락처만 만든다(기억 항목이 아니라 기록하지 않는다)
        contact = Contact(user_id=user_id, email=mail.sender.lower(), name=name)
        db.add(contact)
        db.flush()
    elif not contact.name:  # 문맥 기억이 이름 없이 만든 연락처
        contact.name = name
    target = f"contact:{contact.id}"
    if position is None or _touched_by_user(db, user_id, target):
        return None
    changes = {}
    if not contact.position:
        changes["position"] = position
    my_rank, their_rank = RANK.get(me.position or ""), RANK[position]
    superior = said == "메일 서명에서" and my_rank is not None and their_rank > my_rank and not contact.is_superior
    if superior:
        changes["is_superior"] = True
    if not changes:
        return None
    what = f"{name} {position}님" + ("을 상급자로" if superior else "의 직급을")
    return memory.update_person(db, user_id, contact.id, source=SOURCE, via=VIA, **changes,
                                extra={"text": f"{said} {what} 알게 됐어요", "mail_id": mail.id,
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
    masker = privacy.masker_for(db, user_id)  # 개인정보 가리기(BE-6). 근거 문장 · 값은 되돌려 저장한다
    try:
        result = masker.unmask_model(ai.extract_memory(masker.mask_obj(payload)))
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
