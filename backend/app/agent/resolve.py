"""대상 해석 — ai가 고른 target(발신자 · 분류 · 기간 · 키워드 · 선택 메일)을 실제 업무 id로 바꾼다
(BE-11, docs/30_backend/detail.md 4절 4단계, 구조도 6절).

- 발신자 '김 팀장'은 연락처(contacts)의 이름 · 직급 · 메일 주소로 찾는다. 여러 명이 걸리면 후보가 여럿(ambiguous) → 확인 카드.
- 지시어('이거')는 프론트가 보낸 선택 메일 id(target.mail_ids)로 온다.
- 끝나지 않은 받은 메일 업무(미처리 pending · 나중에 snoozed)가 대상이다(#31 리뷰: 미뤘다고 끝난 일은 아니다).
- 조건이 하나도 없으면 전부를 고르지 않는다(no_filter) — '다 처리했어'만으로 모든 업무를 바꾸지 않게.
- 결과 카드 '어떻게 해석했나요'용 설명(notes)을 같이 돌려준다(UX-D8, wireframe 13-4절).
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.agent import people
from app.agent.ask import terms
from app.models import Account, Contact, Mail, Task
from app.models.mail import visible_mail


OPEN = ("pending", "snoozed")
MIN_PHRASE = 2  # 한 글자('민' · 'e')는 부분 일치가 너무 넓다. 후보가 1명이면 확인 없이 실행되므로 찾지 않는다(#31 리뷰)


@dataclass
class Resolution:
    task_ids: list[int] = field(default_factory=list)
    ambiguous: bool = False  # 발신자 후보가 여러 명
    no_filter: bool = False  # 조건이 하나도 없음
    notes: list[str] = field(default_factory=list)


def _day(v: Any) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def _norm(s: str) -> str:
    return re.sub(r"\s+|님$", "", s.strip())


def match_contacts(db: Session, user_id: int, phrase: str) -> list[Contact]:
    """'김 팀장' · '김민준' · '민준' · 'lead@…'을 연락처에서 찾는다. 성 + 직급('김 팀장'), 직급만('팀장님')도 본다.
    두 글자보다 짧으면 찾지 않는다."""
    p = _norm(phrase).lower()
    if len(p) < MIN_PHRASE:
        return []
    out = []
    for c in db.scalars(select(Contact).where(Contact.user_id == user_id).order_by(Contact.id)):
        name, pos = _norm(c.name or "").lower(), _norm(c.position or "").lower()
        if (p in c.email.lower()) or (name and (p in name or name in p)) or (pos and p == pos) or \
                (name and pos and p.startswith(name[0]) and p.endswith(pos) and len(p) <= len(pos) + 2) or \
                people.name_matches(phrase, c.name, c.position):  # '소희 책임'(이름 + 직급, AI-44)
            out.append(c)
    return out


def resolve_ids(db: Session, user_id: int, task_ids: list[int]) -> Resolution:
    """화면에서 고른 업무(캐치봇 '고른 리마인더' 칩 → task_ids)를 그대로 대상으로 한다. 내 것이고 끝나지 않은 것만 남긴다.
    '이거 내일로 미뤄'의 '내일'을 받은 날 조건으로 잘못 읽어 대상이 0건이 되지 않게(11-18), ai의 기간 조건은 보지 않는다."""
    res = Resolution()
    res.task_ids = list(db.scalars(
        select(Task.id).join(Mail, Task.mail_id == Mail.id).join(Account, Mail.account_id == Account.id)
        .where(Account.user_id == user_id, Task.status.in_(OPEN), Task.id.in_(task_ids)).order_by(Mail.sent_at, Task.id)))
    res.notes.append(f"고른 리마인더의 업무 {len(res.task_ids)}건")  # 남의 것 · 끝난 것은 빼고 센다
    return res


def resolve(db: Session, user_id: int, target: dict[str, Any], *, by_due: bool = False,
            allow_all: bool = False) -> Resolution:
    """by_due: 기간을 기한(due_at)으로 볼지(T02 '이번 주 기한인 거'), 받은 날(sent_at)로 볼지(T03 '이번 주 공지') `[제안]`.
    allow_all: 조건이 없을 때 전부를 돌려줄지. 조회(T02 '미처리 다 보여줘')만 켠다 — 상태 변경은 전부를 고르지 않는다."""
    res = Resolution()
    status = target.get("status") if target.get("status") in ("done", "snoozed") else None  # 11-18 '끝낸 거' · '미룬 거'
    q = (select(Task.id).join(Mail, Task.mail_id == Mail.id).join(Account, Mail.account_id == Account.id)
         .where(Account.user_id == user_id, Task.status.in_((status,) if status else OPEN), Mail.direction == "received",
                visible_mail()))
    used = False
    if status:
        res.notes.append("끝낸 업무" if status == "done" else "미룬 업무")
    if ids := [int(i) for i in target.get("mail_ids") or []]:
        q, used = q.where(Task.mail_id.in_(ids)), True
        res.notes.append(f"선택한 메일 {len(ids)}통")
    if sender := target.get("sender"):
        found = people.find(db, user_id, sender)  # 연락처 + 메일의 쓴 사람(AI-44)
        used = True
        if not found:
            res.notes.append(f"'{sender}'에 맞는 사람을 연락처 · 받은 메일에서 찾지 못했어요")
            return res
        res.ambiguous = len(found) > 1
        q = q.where(or_(*[people.wrote(p) for p in found]))
        res.notes.append(f"'{sender}'을(를) " + " · ".join(f"{p.name or p.email} {p.position or ''}".strip() for p in found)
                         + ("으로 (여러 명)" if res.ambiguous else "으로"))
    if category := target.get("category"):
        q, used = q.where(Mail.category == category), True
        res.notes.append(f"분류 '{category}'")
    if rng := target.get("date_range"):
        start = datetime.combine(_day(rng["start"]), time.min)
        end = datetime.combine(_day(rng["end"]) + timedelta(days=1), time.min)
        col = Task.done_at if status == "done" else Task.due_at if by_due else Mail.sent_at  # '이번 주에 끝낸 거'는 끝낸 날
        q, used = q.where(col >= start, col < end), True
        res.notes.append(f"{'끝낸 날' if status == 'done' else '기한' if by_due else '받은 날'} {start:%m/%d}~{end - timedelta(days=1):%m/%d}")
    if keyword := target.get("keyword"):
        # 낱말마다 업무 문장 · 제목 어딘가에 있으면 된다(11-18: '킥오프 발표 자료'가 '[누리물류] 킥오프 발표자료 …'에 붙어 있지 않아도).
        # 낱말을 못 뽑으면(전부 조사 · 의문사) 말 그대로 찾는다. '%' · '_'도 글자로 찾는다
        for w in terms(keyword) or [keyword]:
            q = q.where(or_(Task.text.contains(w, autoescape=True), Mail.subject.contains(w, autoescape=True)))
        used = True
        res.notes.append(f"'{keyword}'이(가) 들어간 업무")
    if not used and not allow_all:
        res.no_filter = True
        return res
    if not used and not status:
        res.notes.append("미처리 업무 전체")
    res.task_ids = list(db.scalars(q.order_by(Mail.sent_at, Task.id)))
    return res
