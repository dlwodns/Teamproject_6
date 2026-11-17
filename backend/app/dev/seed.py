"""시연용 데모 DB 시드 (BE-2 중 '정답 라벨로 데모 DB 채우기').

`data/dummy/dummy_mails.json`의 정답 라벨(gold)로 메일 · 업무 · 연락처를 바로 채운다. ai `/classify`를 거치는
`POST /dev/load-dummy`(classify_jobs 생성)와는 다른 경로이고, 시연 전용 SQLite 파일(`demo*.db`)에만 쓴다.

    python -m app.dev.seed load  --db demo.db --as-of 2026-10-19T16:16   # 그 시각까지 도착한 메일만
    python -m app.dev.seed check --db demo.db --sender "김 팀장"          # DB에서 센 값
    python -m app.dev.seed reset --db demo.db                             # 테이블을 비우고 다시 만든다
    python -m app.dev.seed load  --db demo.db --this-week                # 더미 메일함을 이번 주로 옮겨 지금까지 온 것만(11-18)
- 이번 주로 옮기기(--this-week): 더미는 2026-10-19(월) 하루치라 날이 지나면 기한이 모두 지나 버린다. 메일함 날짜를 이번 주 월요일
  (오늘이 월요일이면 지난주 월요일)로 옮겨 적재한다. 7일 단위로만 옮겨 본문의 '금요일까지' 같은 요일과 날짜가 맞는다.
  받은 시각 · 기한뿐 아니라 제목 · 본문 · 정답 속 날짜 글자(10/23 · 10월 23일 · 2026-10-23)도 같이 옮긴 사본을 DB 옆에
  `<db 이름>.mails.json`으로 쓴다. 본문을 읽는 곳(app/mail/body.py)이 같은 사본을 보게 `DUMMY_MAIL_SOURCE`에 그 경로를 넣는다.

- 반복 실행: 메일은 `(account_id, source_id)`로, 연락처는 `(user_id, email)`로 찾아 있으면 건너뛴다.
  이미 있는 메일의 업무는 건드리지 않으므로 사용자가 바꾼 상태(완료 등)가 남는다.
- 메일 1통과 그 업무 전체를 한 트랜잭션으로 저장한다. 도중에 실패하면 그 메일은 통째로 빠지고, 다시 실행하면 채운다.
- 시각: 원본은 시간대 없는 한국 시간이다. 시간대가 붙어 오면 KST로 바꿔 뗀다(BE-D15, `app/core/clock.py`와 같은 형식).
"""
import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.db import Base, make_engine

KST = ZoneInfo("Asia/Seoul")
DEFAULT_SOURCE = Path(__file__).resolve().parents[3] / "data" / "dummy" / "dummy_mails.json"
PROVIDER = "dummy"
GOLD = "gold"  # category_source · tasks.source에 '정답 라벨에서 옴'을 표시한다(rule | exaone 밖의 값, 시연 DB 전용)

# D39 묶음 [제안] — ai/app/pipeline/classify.py의 CATEGORY · _category와 같은 규칙(backend는 ai를 import하지 않는다, D34)
# 11/7 AI-D15: 조치요청(요청) · 공유(기타) 추가. 5분류 값은 그대로다
CATEGORY = {"회신요청": "회신", "자료제출요청": "요청", "수정재전송요청": "요청", "일정참석": "요청", "조치요청": "요청",
            "검토승인요청": "검토", "공지": "공지", "공유": "기타", "참조": "기타", "회신": "기타", "기타": "기타"}
NO_TASK_TYPES = {"공지", "공유", "참조", "회신", "기타"}
NOT_STORED = ("mail.body", "mail.is_vip", "mail.attachments", "gold.action_types", "gold.urgent",
              "gold.is_follow_up", "gold.tags", "gold.tasks[].format")  # 9절 테이블에 칸이 없다


MAILBOX_DAY = date(2026, 10, 19)  # 더미 메일함 날짜(월요일, data/dummy/README.md)
_ISO = re.compile(r"(?<!\d)(2026)-(1[01])-(\d{2})(?!\d)")
_MD = re.compile(r"(?<![\d/.])(1[01])/(\d{1,2})(?![\d/])")
_KMD = re.compile(r"(?<!\d)(1[01])월\s?(\d{1,2})일")


def week_shift(today: date) -> int:
    """더미 메일함 날짜를 이번 주 월요일로 옮기는 날 수(7의 배수). 오늘이 월요일이면 지난주 월요일(메일이 아직 다 오지 않았다)."""
    base = today - timedelta(days=1)
    return ((base - timedelta(days=base.weekday())) - MAILBOX_DAY).days


def shift_text(text: str, days: int) -> str:
    """글 속 10 · 11월 날짜(2026-10-23 · 10/23 · 10월 23일)를 days만큼 옮긴다. 더미에는 10 · 11월 날짜만 있다."""
    def move(m: int, d: int) -> date:
        return date(2026, m, d) + timedelta(days=days)

    text = _ISO.sub(lambda g: move(int(g[2]), int(g[3])).isoformat(), text)
    text = _MD.sub(lambda g: (lambda x: f"{x.month}/{x.day}")(move(int(g[1]), int(g[2]))), text)
    return _KMD.sub(lambda g: (lambda x: f"{x.month}월 {x.day}일")(move(int(g[1]), int(g[2]))), text)


def shifted_source(source: Path, out: Path, days: int) -> Path:
    """더미 파일 전체(받은 시각 · 기한 · 제목 · 본문 · 정답)의 날짜를 옮긴 사본을 쓴다."""
    out.write_text(shift_text(Path(source).read_text(encoding="utf-8"), days), encoding="utf-8")
    return out


class SeedError(Exception):
    pass


def to_kst_naive(value: str | datetime) -> datetime:
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    return dt.astimezone(KST).replace(tzinfo=None) if dt.tzinfo else dt


def category(action_types: list[str], has_tasks: bool) -> str:
    # 공지 속 나를 지목한 요청은 '요청' 업무다(D40)
    first = next((t for t in action_types if t not in NO_TASK_TYPES), action_types[0]) if has_tasks else action_types[0]
    return CATEGORY[first]


def demo_engine(db_path: str | Path) -> Engine:
    """시연 전용 파일만 연다. 이름이 demo*.db가 아니면 거절한다(ax.db 등 다른 DB 보호)."""
    path = Path(db_path).expanduser().resolve()
    if not (path.name.startswith("demo") and path.suffix == ".db"):
        raise SeedError(f"시연 전용 DB(demo*.db)만 쓸 수 있다: {path.name}")
    import app.models  # noqa: F401  테이블 정의를 Base.metadata에 올린다

    engine = make_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    return engine


@dataclass
class LoadReport:
    as_of: datetime
    added_mails: int = 0
    skipped_mails: int = 0  # 이미 있어서 건너뜀
    added_tasks: int = 0
    added_contacts: int = 0
    learned: int = 0  # 메일 기억하기로 넣은 것(설정이 꺼져 있으면 0)
    missing: dict[str, int] = field(default_factory=dict)  # 원본에 없어 기본값으로 둔 칸

    def to_dict(self) -> dict:
        return {"as_of": self.as_of.isoformat(timespec="minutes"), "added_mails": self.added_mails,
                "skipped_mails": self.skipped_mails, "added_tasks": self.added_tasks,
                "added_contacts": self.added_contacts, "learned": self.learned, "missing": self.missing, "not_stored": list(NOT_STORED)}


def _owner(session: Session, data: dict, report: LoadReport) -> tuple[int, int]:
    """메일함 주인 → users · accounts 1행씩. (user_id, account_id)"""
    from app.models import Account, Contact, User

    box = data["mailbox"]
    account = session.scalar(select(Account).where(Account.provider == PROVIDER, Account.email == box["owner"]))
    if account is None:
        user = User(name=box["name"], department=box.get("team"), position=box.get("position"))
        session.add(user)
        session.flush()
        account = Account(user_id=user.id, provider=PROVIDER, email=box["owner"])
        session.add(account)
        session.flush()
    superiors, favorites = set(box.get("superiors", [])), set(box.get("favorites", []))
    have = set(session.scalars(select(Contact.email).where(Contact.user_id == account.user_id)))
    for person in data["people"].values():
        email = person["email"]
        if email == box["owner"] or email in have:
            continue  # 이미 있는 연락처는 건드리지 않는다(사용자가 바꾼 즐겨찾기 유지)
        session.add(Contact(user_id=account.user_id, email=email, name=person.get("name"),
                            position=person.get("position"), is_superior=email in superiors,
                            is_favorite=email in favorites))
        report.added_contacts += 1
    return account.user_id, account.id


def _task_row(mail_id: int, task: dict, gold: dict, type_: str | None = None):
    from app.models import Task

    due_at = to_kst_naive(task["due_at"]) if task.get("due_at") else None
    # D47: mentioned_me · priority는 메일 단위 → 그 메일의 업무마다 복사
    return Task(mail_id=mail_id, text=task["action"], due_raw=task.get("due_raw"), due_at=due_at,
                mentioned_me=gold.get("mentioned_me", False), priority=gold.get("priority"), source=GOLD, type=type_)


def _count_missing(report: LoadReport, gold: dict) -> None:
    for key in ("mentioned_me", "priority"):
        if key not in gold or gold[key] is None:
            report.missing[key] = report.missing.get(key, 0) + 1


def load(engine: Engine, as_of: str | datetime, source: Path = DEFAULT_SOURCE) -> LoadReport:
    from app.models import Mail

    data = json.loads(Path(source).read_text(encoding="utf-8"))
    report = LoadReport(as_of=to_kst_naive(as_of))
    with Session(engine) as session, session.begin():
        user_id, account_id = _owner(session, data, report)
    owner = data["mailbox"]["owner"]

    for item in sorted(data["mails"], key=lambda m: m["mail"]["received_at"]):
        raw, gold = item["mail"], item["gold"]
        received_at = to_kst_naive(raw["received_at"])
        if received_at > report.as_of:
            continue
        with Session(engine) as session, session.begin():  # 메일 1통 + 업무 전체 = 트랜잭션 1개
            exists = session.scalar(select(Mail.id).where(Mail.account_id == account_id, Mail.source_id == raw["id"]))
            if exists is not None:
                report.skipped_mails += 1
                continue
            tasks = gold.get("tasks") or []
            mail = Mail(account_id=account_id, source_id=raw["id"], conversation_id=raw.get("thread_id"),
                        direction="sent" if raw["from"] == owner else "received", sender=raw["from"],
                        recipients=raw.get("to"), cc=raw.get("cc"), subject=raw.get("subject", ""),
                        sent_at=received_at, category=category(gold["action_types"], bool(tasks)),
                        category_source=GOLD)
            session.add(mail)
            session.flush()
            # 업무 유형: 정답 라벨 action_types에서 메일 성격(공지 · 참조 …)을 뺀 것이 업무 순서와 같다(캐치봇 리마인더 칸)
            types = [t for t in gold["action_types"] if t not in NO_TASK_TYPES]
            for i, task in enumerate(tasks):
                session.add(_task_row(mail.id, task, gold, types[i] if i < len(types) else None))
            # 메일 기억하기(설정을 켰을 때만, PL-16). 본문은 저장하지 않고 이때 한 번 본다
            from app.services import learn

            report.learned += len(learn.on_mail_saved(session, user_id, mail, raw.get("body")))
            if tasks:
                _count_missing(report, gold)
        report.added_mails += 1
        report.added_tasks += len(tasks)
    return report


def tasks_from_sender(session: Session, phrase: str, status: str = "pending") -> list[tuple[str, str]]:
    """'김 팀장'(성 + 직급)을 연락처로 풀어 그 발신자의 업무를 찾는다. [(원본 메일 id, 할 일)]"""
    from app.models import Contact, Mail, Task

    surname, position = phrase.split()
    emails = select(Contact.email).where(Contact.name.startswith(surname), Contact.position == position)
    rows = session.execute(
        select(Mail.source_id, Task.text).join(Task, Task.mail_id == Mail.id)
        .where(Mail.sender.in_(emails), Task.status == status).order_by(Mail.sent_at, Task.id))
    return [tuple(r) for r in rows]


def summary(engine: Engine, sender: str = "김 팀장", probe: str = "M-0064") -> dict:
    """DB에서 센 값. 기대값(scripts/demo_expected.py, 원본 JSON만 읽음)과 대조한다."""
    from app.models import Contact, Mail, Task

    with Session(engine) as session:
        sender_tasks = tasks_from_sender(session, sender)
        return {
            "mails": session.scalar(select(func.count()).select_from(Mail)),
            "tasks": session.scalar(select(func.count()).select_from(Task)),
            "contacts": session.scalar(select(func.count()).select_from(Contact)),
            "sender_pending_tasks": len(sender_tasks),
            "sender_mail_ids": sorted({mid for mid, _ in sender_tasks}),
            f"{probe}_arrived": session.scalar(select(func.count()).select_from(Mail).where(Mail.source_id == probe)) > 0,
        }


def reset(engine: Engine) -> None:
    """시연 DB의 테이블을 모두 지우고 빈 테이블로 다시 만든다(demo_engine을 거친 엔진만 받는다)."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.dev.seed", description="시연용 데모 DB 시드 (정답 라벨)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_load = sub.add_parser("load", help="기준 시각까지 도착한 메일 · 업무 · 연락처 적재(반복해도 중복 없음)")
    p_load.add_argument("--as-of", help="기준 시각(KST), 예: 2026-10-19T16:16. --this-week면 비워 두면 지금")
    p_load.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    p_load.add_argument("--this-week", action="store_true", help="메일함 날짜를 이번 주로 옮겨 적재한다(사본 <db>.mails.json)")
    p_check = sub.add_parser("check", help="DB에서 센 값 출력")
    p_check.add_argument("--sender", default="김 팀장", help="성 + 직급")
    p_reset = sub.add_parser("reset", help="시연 DB만 비우기")
    p_reset.add_argument("--yes", action="store_true", help="확인 없이 비운다")
    for p in (p_load, p_check, p_reset):
        p.add_argument("--db", required=True, help="시연 전용 SQLite 파일(demo*.db)")
    args = parser.parse_args(argv)

    try:
        engine = demo_engine(args.db)
    except SeedError as e:
        print(f"거절: {e}", file=sys.stderr)
        return 2
    if args.cmd == "load":
        source, as_of = args.source, args.as_of
        if args.this_week:
            if as_of:
                print("거절: --this-week는 지금 시각까지 온 메일을 넣는다. --as-of와 함께 쓰지 않는다", file=sys.stderr)
                return 2
            from app.models import Mail

            with Session(engine) as s_:
                if s_.scalar(select(func.count()).select_from(Mail)):
                    # 이미 있는 메일은 건너뛰므로(source_id 같음) 다른 주의 날짜가 섞이고 본문 사본과 어긋난다
                    print("거절: DB에 메일이 이미 있다. 먼저 reset --yes로 비운 뒤 --this-week로 넣는다", file=sys.stderr)
                    return 2
            days = week_shift(datetime.now(KST).date())
            source = shifted_source(args.source, Path(args.db).with_suffix(".mails.json"), days)
            as_of = as_of or datetime.now(KST).replace(tzinfo=None, second=0, microsecond=0)
        elif not as_of:
            print("거절: --as-of가 필요하다(--this-week가 아니면)", file=sys.stderr)
            return 2
        result = load(engine, as_of, source).to_dict()
        if args.this_week:
            result |= {"shift_days": days, "mail_source": str(Path(source).resolve()),
                       "next": f"backend를 DUMMY_MAIL_SOURCE={Path(source).resolve()} 로 띄워 본문도 같은 날짜로 읽게 한다"}
    elif args.cmd == "check":
        result = summary(engine, args.sender)
    else:
        if not args.yes:
            print("거절: reset은 --yes가 있어야 실행한다", file=sys.stderr)
            return 2
        reset(engine)
        result = {"reset": str(Path(args.db).resolve())}
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
