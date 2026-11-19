"""연결한 Outlook 계정 → 내 정보 · 내 주소 (BE-7).

- 내 정보: Graph `/me`의 이름 · 부서 · 직함으로 users 행을 채운다. 개인 계정(Outlook.com)은 이름만 오고, 회사 계정은 부서 · 직함도 온다.
  한국 이름은 Graph가 '규남 문'(이름 성)으로 주므로 성 · 이름이 둘 다 한글이면 '문규남'으로 붙인다.
  설정 화면의 내 정보는 읽기만이라 연결 · [지금 받기] 때마다 Graph 값으로 덮는다.
- 내 주소: 분류가 '나에게 온 메일'을 알려면 로그인 주소 말고도 받는 주소(별칭)를 모두 알아야 한다.
  회사 계정은 `/me`의 mail · proxyAddresses(smtp:) · otherMails로 안다. 개인 계정 별칭(예: @outlook.kr)은 Graph가 알려 주지 않아
  받은 메일에서 배운다(learn): 받는 사람 · 참조에 내 주소가 하나도 없는데 Microsoft 개인 메일 도메인 주소가 딱 하나 있으면 그 주소다.
  ponytail: 그 주소를 받는 사람으로, 나를 숨은 참조로 보낸 메일이면 남의 주소를 배울 수 있다 — 설정 화면에 보이니 틀리면 연결을 다시 하면 지워진다.
  막으려면 사용자가 별칭을 직접 고르는 칸을 둔다.
"""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Mail, User

CONSUMER = re.compile(r"^(?:outlook|hotmail|live)\.[a-z.]+$|^msn\.com$")  # Microsoft 개인 메일 도메인(별칭이 생기는 곳)
HANGUL = re.compile(r"^[가-힣]+$")
LEARN_RECENT = 200  # [지금 받기] 때 다시 훑는 최근 받은 메일 수


def person_name(me: dict) -> str | None:
    given, sur = (me.get("givenName") or "").strip(), (me.get("surname") or "").strip()
    if HANGUL.match(given) and HANGUL.match(sur):
        return sur + given
    return (me.get("displayName") or "").strip() or None


def graph_addresses(me: dict) -> set[str]:
    """`/me`가 알려 주는 내 주소 전부(소문자)."""
    out = {me.get("mail"), me.get("userPrincipalName"), *(me.get("otherMails") or [])}
    out |= {p.split(":", 1)[1] for p in me.get("proxyAddresses") or [] if p.lower().startswith("smtp:")}
    return {a.strip().lower() for a in out if a and "@" in a}


def apply_me(db: Session, account: Account, me: dict) -> None:
    """Graph `/me`로 내 정보 · 계정 별칭을 맞춘다. 이름이 비어 오면 이름은 그대로 둔다."""
    user = db.get(User, account.user_id)
    if name := person_name(me):
        user.name = name[:100]
    user.department = (me.get("department") or "").strip()[:100] or None
    user.position = (me.get("jobTitle") or "").strip()[:50] or None
    _add_aliases(account, graph_addresses(me))


def _add_aliases(account: Account, found: set[str]) -> None:
    new = sorted((set(account.aliases or []) | found) - {account.email.lower()})
    if new != (account.aliases or []):
        account.aliases = new  # 새 목록으로 바꿔야 JSON 칸 변경이 저장된다


def my_addresses(db: Session, user_id: int) -> list[str]:
    """내 모든 계정의 주소 · 별칭(소문자)."""
    out: set[str] = set()
    for a in db.scalars(select(Account).where(Account.user_id == user_id)):
        out |= {a.email.lower(), *(a.aliases or [])}
    return sorted(out)


def learn(account: Account, recipients: list[str], cc: list[str]) -> None:
    """받은 메일 한 통의 받는 사람 · 참조에서 개인 계정 별칭을 배운다(모듈 설명)."""
    rcpts = {a.strip().lower() for a in [*recipients, *cc] if a and "@" in a}
    if rcpts & {account.email.lower(), *(account.aliases or [])}:
        return
    cand = [a for a in rcpts if CONSUMER.match(a.rsplit("@", 1)[1])]
    if len(cand) == 1:
        _add_aliases(account, {cand[0]})


def learn_recent(db: Session, account: Account) -> None:
    """이미 받아 둔 메일에서 다시 배운다([지금 받기] · 연결 직후 — 별칭을 나중에 만든 경우)."""
    rows = db.execute(select(Mail.recipients, Mail.cc).where(Mail.account_id == account.id, Mail.direction == "received")
                      .order_by(Mail.sent_at.desc()).limit(LEARN_RECENT)).all()
    for to, cc in rows:
        learn(account, list(to or []), list(cc or []))
