"""메일 본문 가져오기 (구조도 9 · 10절: 본문은 DB에 저장하지 않고, 필요할 때 원본에서 가져온다).

- dummy 계정: 더미 메일 파일(`DUMMY_MAIL_SOURCE`, 기본 data/dummy/dummy_mails.json)에서 원본 id(source_id)로 찾는다.
- outlook_graph 계정: Graph `GET /me/messages/{id}`에서 글자(text) 본문으로 가져온다(BE-7). 연결이 끊겼거나 Graph가 실패하면 None.
가져오지 못하면 None이다. 부르는 쪽(분류 작업)은 빈 본문으로 분류하지 않고 다시 시도한다(조용히 품질이 떨어지지 않게).
"""
import json
import os
import re
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Account, Mail

CID_TEXT = re.compile(r"\[cid:[^\]\s]+\]")
DEFAULT_DUMMY = Path(__file__).resolve().parents[3] / "data" / "dummy" / "dummy_mails.json"


def _dummy_path() -> Path:
    return Path(os.environ.get("DUMMY_MAIL_SOURCE") or DEFAULT_DUMMY)


@lru_cache(maxsize=4)
def _dummy_index(path: str, mtime: float) -> dict[str, str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {m["mail"]["id"]: m["mail"].get("body", "") for m in data["mails"]}


def fetch_body(db: Session, mail: Mail, *, raise_transient: bool = False) -> str | None:
    """raise_transient: Outlook이 잠깐 실패하면(429 · 5xx · 연결 끊김) None 대신 GraphError를 올린다 — 분류 작업이
    시도 횟수를 세지 않고 미루게(jobs/classify.py). 메일이 없으면(404) 늘 None."""
    account = db.get(Account, mail.account_id)
    if account is None:
        return None
    if account.provider == "dummy":
        path = _dummy_path()
        if not path.exists():
            return None
        return _dummy_index(str(path), path.stat().st_mtime).get(mail.source_id)
    if account.provider == "outlook_graph":
        from app.mail import graph  # 더미만 쓰는 실행에서 Graph 모듈을 부르지 않게

        try:
            r = graph.call(db, account, "GET", f"/me/messages/{mail.source_id}", params={"$select": "body"},
                           prefer=('outlook.body-content-type="text"',))
        except graph.GraphError as e:
            if raise_transient and e.status != 404:
                raise
            return None
        # 본문에 박힌 그림은 글로 바꾸면 '[cid:…]'만 남는다 → '[그림]'(AI-42, 화면 글 본문 · 분류 입력 모두)
        return CID_TEXT.sub("[그림]", (r.json().get("body") or {}).get("content") or "")
    return None  # imap: 범위 밖


def fetch_html(db: Session, mail: Mail) -> str | None:
    """읽기 화면용 HTML 본문(AI-42, Outlook만). HTML이 아니거나 가져오지 못하면 None — 화면은 글 본문으로 보인다."""
    account = db.get(Account, mail.account_id)
    if account is None or account.provider != "outlook_graph":
        return None
    from app.mail import graph

    try:
        body = graph.call(db, account, "GET", f"/me/messages/{mail.source_id}", params={"$select": "body"}).json().get("body") or {}
    except graph.GraphError:
        return None
    return body.get("content") if body.get("contentType") == "html" else None
