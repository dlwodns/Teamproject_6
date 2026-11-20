"""사람 찾기(AI-44) — 캐치봇이 말한 사람('임소희 책임' · '소희' · '임 책임')을 연락처와 메일의 쓴 사람에서 찾는다.

사람은 두 곳에 있다.
- 연락처(contacts): 주소 1개 = 이름 1개. 사용자가 고칠 수 있고 맡은 일 · 소속(문맥 기억)이 붙는다.
- 메일의 쓴 사람(mails.author_name): 메일마다 본문의 첫인사 · 서명 · 맺음말에서 읽은 이름(services/learn.author).
  공용 주소(여러 사람이 한 주소로 보냄) · 연락처에 없는 사람도 메일 단위로 가른다.
그 사람이 '쓴 메일' = 쓴 사람이 그 이름인 메일 + (연락처면) 그 주소로 온 메일 중 쓴 사람이 다른 이름이 아닌 것.
'이름만 나온 메일' = 최근 받은 메일 중 보낸 사람이 직접 쓴 부분(인용 · 서명 아래 제외)에 이름이 나오고 그 사람이 쓰지 않은 것.
캐치봇의 사람 조회(T17) · 보낸 사람 조건(T02 · T03 · T05 … resolve, T19 메일 찾기)이 모두 이 파일로 사람을 찾는다.
"""
import re
from dataclasses import dataclass

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import Session

from app.mail.body import fetch_body
from app.models import Account, Contact, Mail, User
from app.models.mail import visible_mail
from app.services.learn import RANK, own_part, reads_body

NAME_SCAN = 30  # ponytail: 최근 받은 메일 30통만 본문을 본다(Graph 1통씩, 5~6초). 더 넓게 보려면 Graph $search로
RANKS = sorted(RANK, key=len, reverse=True)
# 말 속의 '이름 직급'(모정훈 과장 · 임 책임). 이름은 1~4글자 — 성 + 직급도 받는다
PERSON_IN_TEXT = re.compile(r"[가-힣]{1,4}\s?(?:" + "|".join(RANKS) + r")(?:님)?")


@dataclass
class Person:
    name: str | None
    position: str | None
    contact: Contact | None
    email: str  # 그 사람이 보낸 주소(연락처 주소, 없으면 가장 최근 쓴 메일의 보낸 주소)


def split(phrase: str) -> tuple[str, str | None]:
    """'임소희 책임님' → ('임소희', '책임'). 공백 · '님'을 떼고 끝의 직급을 나눈다."""
    p = re.sub(r"\s+|님$", "", phrase.strip())
    for r in RANKS:
        if p.endswith(r) and len(p) > len(r):
            return p[: -len(r)], r
    return p, None


def name_matches(phrase: str, name: str | None, position: str | None) -> bool:
    """말한 사람이 이 이름 · 직급인가. 성명('임소희') · 이름('소희', 두 글자 이상) · 성 + 직급('임 책임', 직급이 같을 때)."""
    if not name:
        return False
    core, rank = split(phrase)
    n = re.sub(r"\s+", "", name).lower()
    core = core.lower()
    if len(core) < 2:
        return len(core) == 1 and rank is not None and rank == position and n.startswith(core)
    return core == n or (len(n) == len(core) + 1 and n.endswith(core)) or n in core


def is_me(db: Session, user_id: int, phrase: str) -> bool:
    me = db.get(User, user_id)
    return me is not None and name_matches(phrase, me.name, me.position)


def _received(user_id: int):
    return (select(Mail).join(Account, Mail.account_id == Account.id)
            .where(Account.user_id == user_id, Mail.direction == "received", visible_mail()))


def recent(db: Session, user_id: int) -> list[tuple[Mail, str]]:
    """최근 받은 메일 NAME_SCAN통과 그 직접 쓴 부분. 본문을 가져오며 쓴 사람 칸도 채운다(fetch_body).
    본문 읽기가 꺼져 있으면 []."""
    if not reads_body(db, user_id):
        return []
    rows = db.scalars(_received(user_id).order_by(Mail.sent_at.desc(), Mail.id.desc()).limit(NAME_SCAN)).all()
    return [(m, own_part(fetch_body(db, m) or "")) for m in rows]


def backfill(db: Session, user_id: int) -> None:
    """쓴 사람 칸을 아직 안 본 최근 메일만 본문을 가져와 채운다(예전에 받은 메일). 한 번 채우면 다시 가져오지 않는다."""
    if not reads_body(db, user_id):
        return
    for m in db.scalars(_received(user_id).where(Mail.author_name.is_(None))
                        .order_by(Mail.sent_at.desc(), Mail.id.desc()).limit(NAME_SCAN)):
        fetch_body(db, m)
    db.flush()


def find(db: Session, user_id: int, phrase: str) -> list[Person]:
    """말한 사람 후보. 연락처와 쓴 사람을 이름으로 합친다(같은 이름은 한 사람). 여럿이면 부르는 쪽이 되묻는다."""
    from app.agent.resolve import match_contacts  # resolve가 이 파일을 쓴다(순환 import 피함)

    backfill(db, user_id)
    out: dict[str, Person] = {}
    for c in match_contacts(db, user_id, phrase):
        out[c.name or c.email] = Person(c.name, c.position, c, c.email)
    authors = db.execute(select(Mail.author_name, Mail.author_position, Mail.sender).join(Account, Mail.account_id == Account.id)
                         .where(Account.user_id == user_id, Mail.direction == "received", Mail.author_name != "")
                         .order_by(Mail.sent_at.desc())).all()
    for name, position, sender in authors:
        if name in out:
            out[name].position = out[name].position or position
        elif name_matches(phrase, name, position):
            out[name] = Person(name, position, None, sender)
    return list(out.values())


def wrote(p: Person) -> ColumnElement[bool]:
    """그 사람이 쓴 메일 조건(받은 메일 쿼리에 붙인다)."""
    conds = [Mail.author_name == p.name] if p.name else []
    if p.contact is not None:  # 그 주소로 온 메일 중 다른 사람이 쓴 것(공용 주소)은 뺀다. 아직 안 본 메일(NULL)은 넣는다
        conds.append(and_(func.lower(Mail.sender) == p.contact.email.lower(),
                          or_(Mail.author_name.is_(None), Mail.author_name == "", Mail.author_name == (p.name or ""))))
    return or_(*conds)


def mentioning(scanned: list[tuple[Mail, str]], name: str, skip: set[int]) -> list[Mail]:
    """이름이 직접 쓴 부분에 나오는 메일(skip = 그 사람이 쓴 메일). 최근 순."""
    return [m for m, own in scanned if m.id not in skip and name in own]
