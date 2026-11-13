"""'에이전트가 아는 것' — 기억 보기 · 고치기 · 되돌리기, 그리고 그 기억을 쓰는 곳에 넘기기 (PL-16 5.2절).

원칙: **쓰는 곳이 정해진 구조화된 값만 기억이다.** 화면에 보이는 모든 항목은 그 값을 실제로 읽는 곳(used_by)이 있다.
아무도 읽지 않는 자유 문장 규칙은 두지 않는다(11-11 확인: '늘 지키는 규칙' 자유 문장은 읽는 곳이 없어 뺐다.
"박 책임님 메일은 항상 중요로"(T11 중요_발신자_지정)는 그 연락처의 상급자 · 즐겨찾기 표시로 저장된다).

| 기억 | 저장 | 읽는 곳 |
|---|---|---|
| 내 직책 · 팀 · 배포 목록(종류: 직책 · 팀 · 전사) | users · user_mailing_lists | 메일 분류(owner.position · team · member_of · role_lists · team_lists, AI-D15) |
| 상급자 | contacts.is_superior | 제안 카드 ④ · 메일 분류 우선순위(sender.is_superior) |
| 즐겨찾기 | contacts.is_favorite | 메일 분류 우선순위(sender.is_favorite) |
| 맡은 일 · 소속(문맥 기억, 모델) | contact_facts | 제안 카드의 사람 표시("장민호님(한빛은행 IT기획부)") |

쓰는 길은 셋이다: 화면(PATCH) · 에이전트 T11(apply_t11) · 메일 기억하기(learn.py). 모두 이 모듈 함수를 거쳐
action_log 한 줄을 남기고, 되돌리기는 업무와 같은 `POST /api/actions/{id}/undo`다.
메일 분류 요청에 넣을 값은 classify_context() 한 곳에서 만든다(backend ai_client가 이것만 쓴다).

기록 형식 (업무 기록과 구분된다):
- params_json.target = "me:<user_id>" | "contact:<contact_id>"
- before_json = {"state": <바꾸기 전 스냅숏>}, params_json.after = <바꾼 뒤 스냅숏>
  (되돌릴 때 지금 값이 after와 다르면 기록 밖에서 바뀐 것이므로 덮어쓰지 않고 409)
- affected_ids = [] (업무를 건드리지 않는다)
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import now
from app.models import Account, ActionLog, Contact, ContactFact, Mail, MailingList, User
from app.services.task_status import UNDO, StatusError

ACTIONS = {"memory_me": "내 정보", "memory_people": "중요한 사람"}
# 읽는 곳. 화면의 '어디에 쓰이나'는 이 표에서 만든다. 읽는 곳이 바뀌면 여기와 계약 문서 3.3절을 함께 고친다
USED_BY = {
    "me": ["메일 분류"],
    "superior": ["제안 카드", "메일 분류"],
    "favorite": ["메일 분류"],
    "facts": ["제안 카드"],
}
FACT_KINDS = ("works_on", "org")
FACT_LABEL = {"works_on": "맡은 일", "org": "소속"}
USES = {
    "me": "직책 · 팀 배포 목록으로 온 지시는 나에게 온 것으로 보고 할 일로 잡아요.",
    "superior": "상급자 메일은 우선순위를 높이고, 받은 지 2시간이 넘도록 처리하지 않으면 제안 카드로 알려 드려요.",
    "favorite": "즐겨찾기한 분의 메일은 우선순위를 높여요.",
    "facts": "제안 카드에 이름과 함께 맡은 일이나 소속을 보여 드려요.",
}
T11_LEVELS = ("superior", "favorite")
_UNSET = object()
MAIL_LEARN = "mail_learn"  # 메일 기억하기(설정을 켰을 때 메일에서 알게 된 것, services/learn.py)


# ---------- 스냅숏 · 복원 ----------

def _parse(target: str) -> tuple[str, int]:
    kind, _, raw = target.partition(":")
    return kind, int(raw)


def _owned_contact(db: Session, user_id: int, contact_id: int) -> Contact:
    c = db.get(Contact, contact_id)
    if c is None or c.user_id != user_id:
        raise StatusError("not_found", f"없는 연락처: {contact_id}")
    return c


LIST_KINDS = ("role", "team", "all")
_ROLE_WORDS = ("leader", "lead", "head", "manager", "chief", "팀장", "리더")
_ALL_WORDS = ("all", "everyone", "staff", "notice", "company", "전사", "전체")


def list_kind(address: str) -> str:
    """배포 목록 종류를 주소로 짐작한다(사용자가 화면에서 바꿀 수 있다). 직책 목록 · 전사 목록이 아니면 팀 목록으로 본다
    — 내가 받은 소규모 목록은 대개 우리 팀 · 파트다. 예: cloud-leaders@ → role, all@ → all, cloud1@ → team."""
    local = address.split("@", 1)[0].lower()
    words = [w for w in local.replace("_", "-").replace(".", "-").split("-") if w]
    if any(w.startswith(r) for w in words for r in _ROLE_WORDS):
        return "role"
    if any(w in _ALL_WORDS or w.startswith("all") for w in words):
        return "all"
    return "team"


def _norm_lists(items) -> list[dict]:
    """[{"address", "kind"}] 주소 순. 문자열만 오면(예전 기록 · 짐작) 종류를 짐작한다. 같은 주소는 뒤의 것이 이긴다."""
    out: dict[str, str] = {}
    for x in items or []:
        if isinstance(x, str):
            out[x.strip().lower()] = list_kind(x)
        else:
            a = x["address"].strip().lower()
            out[a] = x.get("kind") or list_kind(a)
    return [{"address": a, "kind": out[a]} for a in sorted(out)]


def _lists(db: Session, user_id: int) -> list[dict]:
    rows = db.scalars(select(MailingList).where(MailingList.user_id == user_id).order_by(MailingList.address))
    return [{"address": r.address, "kind": r.kind} for r in rows]


def snapshot(db: Session, user_id: int, target: str) -> dict:
    kind, tid = _parse(target)
    if kind == "me":
        u = db.get(User, tid)
        return {"department": u.department, "position": u.position, "mailing_lists": _lists(db, tid)}
    if kind == "contact":
        c = _owned_contact(db, user_id, tid)
        # 근거 문장은 기록(action_log) 스냅숏에 넣지 않는다. 화면에서 지우면 어디에도 남지 않게(contact_facts에만 있다)
        return {"is_superior": c.is_superior, "is_favorite": c.is_favorite, "position": c.position,
                "facts": _facts(db, c.id)}
    raise StatusError("invalid", f"알 수 없는 기억 항목: {target}")


def _facts(db: Session, contact_id: int, *, evidence: bool = False) -> dict:
    """{종류: {"value", "mail_id"}}. evidence=True면 근거 문장도 — 화면 · 저장에서만 쓰고 기록 스냅숏에는 넣지 않는다."""
    rows = db.scalars(select(ContactFact).where(ContactFact.contact_id == contact_id).order_by(ContactFact.kind))
    return {r.kind: {"value": r.value, "mail_id": r.mail_id, **({"evidence": r.evidence} if evidence else {})}
            for r in rows}


def facts_by_contact(db: Session, user_id: int) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for r in db.scalars(select(ContactFact).where(ContactFact.user_id == user_id)):
        out.setdefault(r.contact_id, {})[r.kind] = r.value
    return out


def _set_facts(db: Session, user_id: int, contact_id: int, facts: dict) -> None:
    rows = {r.kind: r for r in db.scalars(select(ContactFact).where(ContactFact.contact_id == contact_id))}
    for kind, row in rows.items():
        if kind not in facts:
            db.delete(row)
    for kind, f in facts.items():
        row = rows.get(kind)
        if row is None:
            db.add(ContactFact(user_id=user_id, contact_id=contact_id, kind=kind, value=f["value"],
                               evidence=f.get("evidence"), mail_id=f.get("mail_id"), created_at=now()))
        else:
            # 되돌리기(스냅숏)에는 근거 문장이 없다. 값이 그대로면 지금 근거를 두고, 값이 바뀌면 근거도 비운다
            keep = row.evidence if row.value == f["value"] else None
            row.value, row.evidence, row.mail_id = f["value"], f.get("evidence", keep), f.get("mail_id")


def _set_lists(db: Session, user_id: int, items) -> None:
    for row in db.scalars(select(MailingList).where(MailingList.user_id == user_id)):
        db.delete(row)
    db.flush()
    db.add_all(MailingList(user_id=user_id, address=x["address"], kind=x["kind"]) for x in _norm_lists(items))


def restore(db: Session, user_id: int, target: str, snap: dict) -> None:
    kind, tid = _parse(target)
    if kind == "me":
        u = db.get(User, tid)
        u.department, u.position = snap["department"], snap["position"]
        _set_lists(db, tid, snap["mailing_lists"])
    elif kind == "contact":
        c = _owned_contact(db, user_id, tid)
        c.is_superior, c.is_favorite = snap["is_superior"], snap["is_favorite"]
        if "position" in snap:  # 11/11 전 기록에는 직급이 없다
            c.position = snap["position"]
        if "facts" in snap:
            db.flush()
            _set_facts(db, user_id, tid, snap["facts"])
    else:
        raise StatusError("invalid", f"알 수 없는 기억 항목: {target}")
    db.flush()


# ---------- 기록 ----------

def _record(db: Session, user_id: int, action: str, target: str, before: dict, source: str,
            extra: dict | None = None, via: str | None = None) -> ActionLog:
    db.flush()  # 세션은 자동 flush를 끄고 쓴다. 바꾼 값이 반영된 뒤에 스냅숏을 뜬다
    after = snapshot(db, user_id, target)
    log = ActionLog(user_id=user_id, action=action, source=source,
                    params_json={"target": target, "after": after, **({"via": via} if via else {}), **(extra or {})},
                    affected_ids=[], before_json={"state": before}, created_at=now())
    db.add(log)
    db.flush()
    return log


def top_actions(db: Session, user_id: int) -> dict[str, int]:
    """기억 항목마다 지금 되돌릴 수 있는 행동 id. task_status._top_actions와 같은 방식(되돌리기 · 다시 하기 반영)."""
    stacks: dict[str, list[int]] = {}
    by_id: dict[int, ActionLog] = {}
    rows = db.scalars(select(ActionLog).where(ActionLog.user_id == user_id).order_by(ActionLog.id))
    for x in rows:
        by_id[x.id] = x
        target = (x.params_json or {}).get("target")
        if not target:
            continue
        stack = stacks.setdefault(target, [])
        if x.action != UNDO:
            stack.append(x.id)
            continue
        undone = by_id.get(x.params_json.get("action_id"))
        if undone is None:
            continue
        if undone.action == UNDO:  # 다시 하기
            stack.append(undone.params_json["action_id"])
        elif stack and stack[-1] == undone.id:
            stack.pop()
    return {t: s[-1] for t, s in stacks.items() if s}


def undo(db: Session, log: ActionLog, *, source: str = "ui") -> ActionLog:
    """기억 변경 한 줄을 되돌린다. 뒤에 같은 항목을 바꾼 살아 있는 기록이 있으면 409(업무 되돌리기와 같은 규칙)."""
    target = log.params_json["target"]
    user_id = log.user_id
    if log.action == UNDO:
        later = db.scalars(select(ActionLog).where(ActionLog.user_id == user_id, ActionLog.id > log.id)).all()
        blocked = any((x.params_json or {}).get("target") == target for x in later)
    else:
        blocked = top_actions(db, user_id).get(target) != log.id
    if blocked:
        raise StatusError("conflict", "이 기록 뒤에 같은 항목을 바꾼 기록이 있어 되돌릴 수 없습니다")
    current = snapshot(db, user_id, target)
    expected = (log.params_json or {}).get("after")
    if expected is not None and current != expected:  # 기록 밖(시드 · 다른 경로)에서 바뀐 것을 덮어쓰지 않는다
        raise StatusError("conflict", "기록 밖에서 이 항목이 바뀌어 되돌릴 수 없습니다")
    restore(db, user_id, target, log.before_json["state"])
    at = now()
    log.undone_at = at
    if log.action == UNDO and (redone := db.get(ActionLog, log.params_json["action_id"])) is not None:
        redone.undone_at = None
    back = ActionLog(user_id=user_id, action=UNDO, source=source,
                     params_json={"action_id": log.id, "target": target, "after": log.before_json["state"]},
                     affected_ids=[], before_json={"state": current}, created_at=at)
    db.add(back)
    db.flush()
    return back


# ---------- 바꾸기 ----------

def _user(db: Session, user_id: int) -> User:
    u = db.get(User, user_id)
    if u is None:
        raise StatusError("not_found", f"없는 사용자: {user_id}")
    return u


def update_me(db: Session, user_id: int, *, department=_UNSET, position=_UNSET, mailing_lists=_UNSET,
              source: str = "ui", via: str | None = None, extra: dict | None = None) -> ActionLog | None:
    u = _user(db, user_id)
    target = f"me:{user_id}"
    before = snapshot(db, user_id, target)
    after = dict(before)
    if department is not _UNSET:
        after["department"] = department
    if position is not _UNSET:
        after["position"] = position
    if mailing_lists is not _UNSET:
        after["mailing_lists"] = _norm_lists(mailing_lists)
    if after == before:
        return None
    u.department, u.position = after["department"], after["position"]
    if after["mailing_lists"] != before["mailing_lists"]:
        _set_lists(db, user_id, after["mailing_lists"])
    return _record(db, user_id, "memory_me", target, before, source, extra, via=via)


def update_person(db: Session, user_id: int, contact_id: int, *, is_superior=_UNSET, is_favorite=_UNSET,
                  position=_UNSET, facts=_UNSET, source: str = "ui", via: str | None = None,
                  extra: dict | None = None) -> ActionLog | None:
    """facts: {종류: {"value", "evidence"?, "mail_id"?} 또는 None(지움)} — 보낸 종류만 바꾼다."""
    c = _owned_contact(db, user_id, contact_id)
    target = f"contact:{contact_id}"
    before = snapshot(db, user_id, target)
    if is_superior is not _UNSET:
        c.is_superior = is_superior
    if is_favorite is not _UNSET:
        c.is_favorite = is_favorite
    if position is not _UNSET:
        c.position = position
    if facts is not _UNSET:
        merged = _facts(db, contact_id, evidence=True)
        for kind, f in facts.items():
            if kind not in FACT_KINDS:
                raise StatusError("invalid", f"기억 종류는 {' · '.join(FACT_KINDS)}만: {kind}")
            if f is None:
                merged.pop(kind, None)
            else:
                merged[kind] = {"value": f["value"], "evidence": f.get("evidence"), "mail_id": f.get("mail_id")}
        db.flush()
        _set_facts(db, user_id, contact_id, merged)
    db.flush()
    if snapshot(db, user_id, target) == before:
        return None
    return _record(db, user_id, "memory_people", target, before, source, extra, via=via)


def apply_t11(db: Session, user_id: int, sender_email: str, level: str, *, name: str | None = None,
              source: str = "agent_rule") -> ActionLog | None:
    """T11 중요_발신자_지정("박 책임님 메일은 항상 중요로")의 실행. 그 발신자의 상급자 또는 즐겨찾기 표시를 켠다.
    연락처가 없으면 만든다. 확인창(설정 변경, D37)은 부르는 쪽(에이전트 실행기 BE-11)이 띄운다."""
    if level not in T11_LEVELS:
        raise StatusError("invalid", f"level은 {' · '.join(T11_LEVELS)} 중 하나: {level}")
    _user(db, user_id)
    email = sender_email.strip().lower()
    c = db.scalar(select(Contact).where(Contact.user_id == user_id, func.lower(Contact.email) == email))
    if c is None:
        c = Contact(user_id=user_id, email=email, name=name)
        db.add(c)
        db.flush()
    return update_person(db, user_id, c.id, source=source, **{f"is_{level}": True})


# ---------- 쓰는 곳에 넘기기 ----------

def classify_context(db: Session, mail: Mail) -> dict:
    """메일 분류 요청(ai `POST /classify`)의 owner · sender 칸. 기억이 분류에 들어가는 유일한 입구다.
    ai 스키마(ai/app/schemas/classify.py OwnerProfile · SenderFlags)와 칸 이름이 같다. backend는 ai를 import하지
    않으므로(D34) 칸 이름은 계약 문서 3.3절과 테스트로 맞춘다."""
    account = db.get(Account, mail.account_id)
    u = db.get(User, account.user_id)
    # 주소는 받은 그대로(대문자 섞임) 저장되므로 소문자로 맞춰 찾는다(제안 카드와 같은 기준)
    c = db.scalar(select(Contact).where(Contact.user_id == u.id, func.lower(Contact.email) == mail.sender.strip().lower()))
    lists = _lists(db, u.id)
    return {
        "owner": {"email": account.email, "name": u.name, "position": u.position, "team": u.department,
                  "member_of": [x["address"] for x in lists],
                  "role_lists": [x["address"] for x in lists if x["kind"] == "role"],
                  "team_lists": [x["address"] for x in lists if x["kind"] == "team"]},
        "sender": {"is_superior": bool(c and c.is_superior), "is_favorite": bool(c and c.is_favorite)},
    }


# ---------- 보기 ----------

def _how(log: ActionLog, by_id: dict[int, ActionLog]) -> str:
    if (log.params_json or {}).get("via") == MAIL_LEARN:
        return f"{log.created_at.month}/{log.created_at.day} 메일에서 알게 됐어요"
    who = {"agent_rule": "에이전트에게 말해서", "agent_model": "에이전트에게 말해서", "mcp": "다른 도구(MCP)에서"}.get(
        log.source, "화면에서")
    verb = "바꿨어요"
    if log.action == UNDO:
        undone = by_id.get((log.params_json or {}).get("action_id"))
        verb = "다시 했어요" if undone is not None and undone.action == UNDO else "되돌렸어요"
    return f"{log.created_at.month}/{log.created_at.day} {who} {verb}"


def _origin(latest: dict[str, ActionLog], by_id: dict[int, ActionLog], target: str) -> dict:
    log = latest.get(target)
    if log is None:
        return {"at": None, "text": "처음 설정에서 넣었어요"}
    return {"at": log.created_at, "text": _how(log, by_id)}


def _latest_by_target(db: Session, user_id: int) -> tuple[dict[str, ActionLog], dict[int, ActionLog]]:
    """항목마다 마지막으로 바꾼 기록(되돌리기 포함). '언제 어떻게 생겼는지' 한 줄에 쓴다."""
    out: dict[str, ActionLog] = {}
    by_id: dict[int, ActionLog] = {}
    for x in db.scalars(select(ActionLog).where(ActionLog.user_id == user_id).order_by(ActionLog.id)):
        by_id[x.id] = x
        if target := (x.params_json or {}).get("target"):
            out[target] = x
    return out, by_id


def view(db: Session, user_id: int) -> dict:
    u = _user(db, user_id)
    latest, by_id = _latest_by_target(db, user_id)
    with_facts = select(ContactFact.contact_id).where(ContactFact.user_id == user_id)
    people = db.scalars(select(Contact).where(Contact.user_id == user_id,
                                              Contact.is_superior.is_(True) | Contact.is_favorite.is_(True)
                                              | Contact.id.in_(with_facts))
                        .order_by(Contact.name, Contact.id)).all()
    from app.services import learn  # learn이 memory를 불러 쓰므로 함수 안에서 부른다

    return {
        "learn_from_mail": learn.enabled(db, user_id),
        "me": {"name": u.name, "department": u.department, "position": u.position,
               "mailing_lists": _lists(db, user_id), "uses": USES["me"], "used_by": USED_BY["me"],
               "origin": _origin(latest, by_id, f"me:{user_id}")},
        "people": [_person(db, c, latest, by_id) for c in people],
    }


def _person(db: Session, c: Contact, latest, by_id) -> dict:
    facts = _facts(db, c.id, evidence=True)
    on = [k for k, flag in (("superior", c.is_superior), ("favorite", c.is_favorite), ("facts", bool(facts))) if flag]
    used_by = list(dict.fromkeys(x for k in on for x in USED_BY[k]))
    return {"contact_id": c.id, "name": c.name, "email": c.email, "position": c.position,
            "is_superior": c.is_superior, "is_favorite": c.is_favorite,
            "facts": [{"kind": k, "label": FACT_LABEL[k], "value": f["value"], "evidence": f["evidence"]}
                      for k, f in facts.items()],
            "uses": " ".join(USES[k] for k in on), "used_by": used_by,
            "origin": _origin(latest, by_id, f"contact:{c.id}")}


def describe(log: ActionLog) -> str:
    """기록 탭 한 줄 문장."""
    p = log.params_json or {}
    learned = p.get("via") == MAIL_LEARN
    if learned and p.get("text"):
        return p["text"]
    if log.action == "memory_me":
        return "메일에서 내 배포 목록을 알게 됐어요" if learned else "내 정보(직책 · 팀 · 배포 목록)를 바꿨어요"
    if log.action == "memory_people":
        if learned:
            return "메일 서명에서 보낸 사람의 직급을 알게 됐어요"
        return "에이전트에게 말해 중요한 사람으로 정했어요" if log.source in ("agent_rule", "agent_model") \
            else "중요한 사람 표시를 바꿨어요"
    return log.action
