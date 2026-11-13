"""메일 본문 가져오기 (구조도 9 · 10절: 본문은 DB에 저장하지 않고, 필요할 때 원본에서 가져온다).

- dummy 계정: 더미 메일 파일(`DUMMY_MAIL_SOURCE`, 기본 data/dummy/dummy_mails.json)에서 원본 id(source_id)로 찾는다.
- outlook_graph 계정: Outlook 연결(BE-7)이 붙으면 여기서 Graph로 가져온다. 지금은 None(가져오지 못함).
가져오지 못하면 None이다. 부르는 쪽(분류 작업)은 빈 본문으로 분류하지 않고 다시 시도한다(조용히 품질이 떨어지지 않게).
"""
import json
import os
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Account, Mail

DEFAULT_DUMMY = Path(__file__).resolve().parents[3] / "data" / "dummy" / "dummy_mails.json"


def _dummy_path() -> Path:
    return Path(os.environ.get("DUMMY_MAIL_SOURCE") or DEFAULT_DUMMY)


@lru_cache(maxsize=4)
def _dummy_index(path: str, mtime: float) -> dict[str, str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {m["mail"]["id"]: m["mail"].get("body", "") for m in data["mails"]}


def fetch_body(db: Session, mail: Mail) -> str | None:
    account = db.get(Account, mail.account_id)
    if account is None:
        return None
    if account.provider == "dummy":
        path = _dummy_path()
        if not path.exists():
            return None
        return _dummy_index(str(path), path.stat().st_mtime).get(mail.source_id)
    return None  # outlook_graph · imap: BE-7
