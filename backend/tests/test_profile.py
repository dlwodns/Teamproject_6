"""BE-7 내 정보 · 내 주소(app/mail/profile.py): Outlook 연결로 이름 · 부서 · 직함을 채우고, 별칭으로 받은 메일도 '나'로 본다."""
from app.mail import profile
from app.models import Account, Mail, User
from app.services.memory import classify_context
from datetime import datetime


def _account(db, email="me@example.com"):
    db.add(User(id=1, name="Outlook 테스트"))
    db.flush()
    a = Account(id=1, user_id=1, provider="outlook_graph", email=email)
    db.add(a)
    db.commit()
    return a


def test_personal_account_gives_korean_name_only(db):
    a = _account(db)
    profile.apply_me(db, a, {"displayName": "규남 문", "givenName": "규남", "surname": "문", "mail": "me@example.com",
                             "userPrincipalName": "me@example.com", "jobTitle": None})
    u = db.get(User, 1)
    assert (u.name, u.department, u.position) == ("문규남", None, None)
    assert a.aliases in (None, [])  # 로그인 주소는 별칭에 넣지 않는다


def test_work_account_gives_department_title_and_proxy_addresses(db):
    a = _account(db, "junho.lee@corp.example")
    profile.apply_me(db, a, {"displayName": "Junho Lee", "givenName": "Junho", "surname": "Lee", "mail": "Junho.Lee@corp.example",
                             "department": "클라우드전환1팀", "jobTitle": "팀장",
                             "proxyAddresses": ["SMTP:junho.lee@corp.example", "smtp:jh@corp.example", "X500:/o=x"]})
    u = db.get(User, 1)
    assert (u.name, u.department, u.position) == ("Junho Lee", "클라우드전환1팀", "팀장")
    assert a.aliases == ["jh@corp.example"]


def test_alias_is_learned_from_received_mail_and_sent_to_ai_as_me(db):
    a = _account(db)
    profile.learn(a, ["friend@example.org", "kim@corp.example"], [])  # 내 주소도, MS 개인 도메인도 아님 → 배우지 않음
    profile.learn(a, ["me@outlook.kr"], [])
    profile.learn(a, ["me@example.com", "other@hotmail.example"], [])  # 내 주소가 이미 있으면 남의 주소를 배우지 않는다
    assert a.aliases == ["me@outlook.kr"]
    m = Mail(account_id=1, source_id="x", direction="received", sender="kim@corp.example", recipients=["me@outlook.kr"],
             subject="s", sent_at=datetime(2026, 11, 19, 9))
    db.add(m)
    db.commit()
    assert classify_context(db, m)["owner"]["aliases"] == ["me@outlook.kr"]


def test_learn_recent_backfills_from_stored_mail(db):
    a = _account(db)
    db.add(Mail(account_id=1, source_id="x", direction="received", sender="k@corp.example", recipients=["me@outlook.kr"],
                subject="s", sent_at=datetime(2026, 11, 19, 9)))
    db.commit()
    profile.learn_recent(db, a)
    assert a.aliases == ["me@outlook.kr"]
