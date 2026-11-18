"""메일을 찾아 답하는 조회(11-18): T18 메일 내용 질문 · T19 메일 찾기 · T08 근거 문장.

T18 '누리물류 킥오프 미팅 어디서 해' · '킥오프 미팅 장소 변경 어디야'.

질문 낱말로 받은 메일(제목 · 업무 문장)을 찾고, 후보 몇 통만 본문을 가져와(DB에는 본문이 없다, mail/body.py)
질문 종류(어디 · 언제 · 얼마)에 맞는 문장이 있는 메일 · 문장을 고른다. 모델은 쓰지 않는다 — 답은 본문 문장 그대로다.
'메일 본문 읽기'(user_settings.read_body)가 꺼져 있으면 본문을 보지 않고 제목으로만 답한다.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.mail.body import fetch_body
from app.models import Account, Contact, Mail, Task
from app.services.learn import reads_body

JOSA = re.compile(r"(?:에서|으로|에게|한테|이랑|이야|은|는|이|가|을|를|의|에|로|도|야|랑)$")
WH = re.compile(r"^(?:어디|언제|뭐|무엇|무슨|몇|얼마|누가|누구|어떻게|어느|알려|말해)")
STOP = {"메일", "내용", "그거", "이거", "저거", "확인", "해줘", "했어", "하는", "하나", "해요", "됐어", "있어", "거야", "건가",
        "관련", "전부", "모두", "보여줘", "찾아줘", "받은", "보낸", "온거", "통이야"}
# (질문 표지, 답 문장 표지). 질문에 표지가 있으면 답 문장 표지가 있는 문장을 고른다
CUES = [(re.compile(r"어디|장소|위치|주소"), re.compile(r"회의실|장소|\d+\s*층|호실|위치|주소|센터|빌딩|본사|사무실|강당|로비")),
        (re.compile(r"언제|몇\s*시|시간|날짜|며칠"), re.compile(r"\d+\s*시|\d+:\d+|오전|오후|\d+\s*[월일]|요일")),
        (re.compile(r"얼마|금액|비용|가격|예산"), re.compile(r"\d[\d,.]*\s*(?:만\s*)?원|금액|비용|예산"))]
SIGNATURE = re.compile(r"^\s*(?:\*{5,}|-{5,}|_{5,}|-+\s*Original Message)", re.M)
SKIP_LINE = re.compile(r"안녕하세요|감사합니다|수고하세요")
CANDIDATES = 50  # 제목 · 업무 문장으로 고르는 후보 수
BODY_READS = 8  # 그중 본문까지 가져와 보는 수. ponytail: 제목 · 업무 문장에 낱말이 없고 본문에만 있는 메일은 못 찾는다(전문 검색이 붙으면 넓힌다)


@dataclass
class Answer:
    mail: Mail
    line: str | None  # 본문에서 고른 문장. 본문을 못 읽었으면 None
    task_ids: list[int]


def terms(*texts: str | None) -> list[str]:
    """질문에서 찾을 낱말. 조사 · 의문사 · '해줘' 같은 말은 뺀다. '[누리물류]' → '누리물류'."""
    out: list[str] = []
    for tok in re.findall(r"[가-힣A-Za-z0-9]+", " ".join(t for t in texts if t)):
        if len(tok) > 2:
            tok = JOSA.sub("", tok)
        if len(tok) >= 2 and not WH.match(tok) and tok not in STOP and tok not in out:
            out.append(tok)
    return out


def _lines(body: str) -> list[str]:
    body = SIGNATURE.split(body, maxsplit=1)[0]  # 서명 · 인용한 앞 메일은 보지 않는다
    return [s.strip() for ln in body.splitlines() for s in re.split(r"(?<=[.!?])\s+", ln)
            if s.strip() and not SKIP_LINE.search(s.strip())]


def find(db: Session, user_id: int, question: str, keyword: str | None, mail_ids: list[int]) -> Answer | None | str:
    """답을 찾으면 Answer, 메일이 없으면 None, 무엇을 찾을지 낱말이 없으면 'no_terms'."""
    words = terms(keyword, question)
    q = (select(Mail).join(Account, Mail.account_id == Account.id).outerjoin(Task, Task.mail_id == Mail.id)
         .where(Account.user_id == user_id, Mail.direction == "received"))
    if mail_ids:  # '이 메일 장소 어디야' → 고른 메일 안에서
        q = q.where(Mail.id.in_(mail_ids))
    elif not words:
        return "no_terms"
    else:
        q = q.where(or_(*[c.contains(w, autoescape=True) for w in words for c in (Mail.subject, Task.text)]))
    mails = list(db.scalars(q.distinct().order_by(Mail.sent_at.desc()).limit(CANDIDATES)))
    if not mails:
        return None
    tasks: dict[int, list[Task]] = {}
    for t in db.scalars(select(Task).where(Task.mail_id.in_([m.id for m in mails])).order_by(Task.id)):
        tasks.setdefault(t.mail_id, []).append(t)

    def head_score(m: Mail) -> int:  # 제목 · 업무 문장에 든 낱말 수
        head = " ".join([m.subject or ""] + [t.text for t in tasks.get(m.id, [])])
        return sum(w in head for w in words)

    mails.sort(key=head_score, reverse=True)  # 안정 정렬: 같은 점수는 최근 메일이 앞
    cue = next((ans for ask, ans in CUES if ask.search(question)), None)
    use_body = reads_body(db, user_id)
    best: tuple[int, Mail, str | None] | None = None
    for m in mails[:BODY_READS]:
        line, line_score = None, 0
        body = fetch_body(db, m) if use_body else None
        for ln in _lines(body or ""):
            s = sum(w in ln for w in words) + (len(words) + 1 if cue and cue.search(ln) else 0)  # 질문 종류에 맞는 문장이 먼저
            if s > line_score:
                line, line_score = ln, s
        score = head_score(m) * 2 + line_score
        if best is None or score > best[0]:
            best = (score, m, line)
    _, m, line = best
    return Answer(mail=m, line=line, task_ids=[t.id for t in tasks.get(m.id, [])])


MAIL_LIST = 20  # T19 카드에 싣는 메일 수. 전체 수는 따로 센다


def find_mails(db: Session, user_id: int, target: dict, sent: bool) -> tuple[list[Mail], int, list[str]]:
    """T19 메일 찾기: (최근 순 메일 최대 MAIL_LIST통, 전체 수, 해석 설명).
    - 사람: 연락처에 있으면 받은 메일은 보낸 사람, 보낸 메일(sent)은 받는 사람으로 거른다. 없으면('한빛은행') 낱말로 찾는다
    - 낱말: 낱말마다 제목 · 업무 문장 · 보낸 사람 주소 어딘가에 있어야 한다
    - 기간: 받은 · 보낸 날. 조건이 없으면 전부(최근 순)"""
    from app.agent.resolve import match_contacts  # resolve가 terms를 가져다 쓴다(순환 import 피함)

    notes: list[str] = []
    words = terms(target.get("keyword"))
    emails: set[str] = set()
    if sender := target.get("sender"):
        people = match_contacts(db, user_id, str(sender))
        if people:
            emails = {c.email.lower() for c in people}
            notes.append(f"{'받는 사람' if sent else '보낸 사람'} " + " · ".join(c.name or c.email for c in people))
        else:
            words += [w for w in terms(str(sender)) if w not in words]
    q = (select(Mail).join(Account, Mail.account_id == Account.id)
         .where(Account.user_id == user_id, Mail.direction == ("sent" if sent else "received")))
    if ids := [int(i) for i in target.get("mail_ids") or [] if str(i).isdigit()]:
        q = q.where(Mail.id.in_(ids))
    if emails and not sent:
        q = q.where(func.lower(Mail.sender).in_(emails))
    for w in words:
        q = q.where(or_(Mail.subject.contains(w, autoescape=True), Mail.sender.contains(w, autoescape=True),
                        Mail.id.in_(select(Task.mail_id).where(Task.text.contains(w, autoescape=True)))))
    if words:
        notes.append("낱말 " + " · ".join(f"'{w}'" for w in words))
    if rng := target.get("date_range"):
        lo = datetime.combine(_day(rng["start"]), time.min)
        hi = datetime.combine(_day(rng["end"]) + timedelta(days=1), time.min)
        q = q.where(Mail.sent_at >= lo, Mail.sent_at < hi)
        notes.append(f"{'보낸' if sent else '받은'} 날 {lo:%m/%d}~{hi - timedelta(days=1):%m/%d}")
    rows = list(db.scalars(q.order_by(Mail.sent_at.desc(), Mail.id.desc())))
    if emails and sent:  # 받는 사람은 JSON 목록이라 여기서 거른다. ponytail: 보낸 메일이 수천 통이면 DB에서 거르게 바꾼다
        rows = [m for m in rows if emails & {str(r).lower() for r in (m.recipients or []) + (m.cc or [])}]
    return rows[:MAIL_LIST], len(rows), notes


def _day(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def who(db: Session, user_id: int, m: Mail) -> str:
    """받은 메일은 보낸 사람, 보낸 메일은 첫 받는 사람(이름 직급, 연락처에 없으면 주소)."""
    addr = m.sender if m.direction == "received" else str((m.recipients or [""])[0])
    c = db.scalar(select(Contact).where(Contact.user_id == user_id, func.lower(Contact.email) == addr.lower()))
    return f"{c.name} {c.position or ''}".strip() if c and c.name else addr


def evidence(db: Session, user_id: int, task: Task) -> str | None:
    """T08 근거 문장: 저장된 근거(evidence_text · span) → 없으면 본문에서 업무 문장 낱말이 가장 많이 든 문장."""
    if task.evidence_text or task.span:
        return task.evidence_text or task.span
    mail = db.get(Mail, task.mail_id)
    body = fetch_body(db, mail) if mail and reads_body(db, user_id) else None
    words = terms(task.text)
    best, score = None, 0
    for ln in _lines(body or ""):
        s = sum(w in ln for w in words)
        if s > score:
            best, score = ln, s
    return best


if __name__ == "__main__":
    assert terms("누리물류 킥오프 미팅", "누리물류 킥오프 미팅 어디서 해") == ["누리물류", "킥오프", "미팅"]
    assert terms(None, "킥오프 미팅 장소 변경 어디야") == ["킥오프", "미팅", "장소", "변경"]
    assert _lines("안녕하세요, 백 과장입니다.\n장소가 2층으로 변경되었습니다. 시간은 10시입니다.\n****************\n백 과장") == \
        ["장소가 2층으로 변경되었습니다.", "시간은 10시입니다."]
    assert terms("누리물류 관련 메일 전부") == ["누리물류"]
