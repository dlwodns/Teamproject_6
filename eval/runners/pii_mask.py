"""평가에서도 서비스와 같은 개인정보 가리기(BE-6 · #94)를 켠다 — `run_dummy.py --mask`.

서비스는 분류 요청을 ai로 보내기 전에 이름 · 메일 주소 · 전화번호 등을 가리고(backend/app/jobs/classify.py),
응답은 원래 값으로 되돌려 저장한다. 평가도 같은 입력을 모델에 보내야 '서비스 그대로' 점수가 된다.

가리는 규칙은 backend/app/privacy/mask.py를 그대로 쓴다. backend와 ai가 둘 다 `app` 패키지라 한 프로세스에서
import할 수 없어서, DB에 묶인 import 세 줄만 빼고 파일을 그대로 실행해 Masker만 꺼낸다. backend가 그 줄을 바꾸면
여기서 멈춰 알린다(조용히 다른 규칙으로 재지 않게).
이름 목록은 시연 데이터를 넣을 때(backend/app/dev/seed.py)와 같다: 메일함 주인 이름 + 사람 목록(연락처)의 이름.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MASK = ROOT / "backend/app/privacy/mask.py"
DB_IMPORTS = ("from sqlalchemy import select\n", "from sqlalchemy.orm import Session\n", "from app.models import Contact, User\n")


def load_masker():
    """backend 가리개 클래스(Masker). 같은 코드라 서비스와 같은 대체어(김◯◯ · user1@도메인 · [전화번호 1])가 나온다."""
    src = MASK.read_text(encoding="utf-8")
    missing = [x.strip() for x in DB_IMPORTS if x not in src]
    if missing:
        raise SystemExit(f"{MASK.relative_to(ROOT)}의 import가 바뀌었다({', '.join(missing)}) — eval/runners/pii_mask.py를 맞춘다")
    for line in DB_IMPORTS:
        src = src.replace(line, "")
    ns = {"__name__": "backend_privacy_mask", "select": None, "Session": object, "Contact": None, "User": None}
    exec(compile(src, str(MASK), "exec"), ns)  # noqa: S102 — 레포 안 backend 파일(서비스와 같은 규칙)
    return ns["Masker"]


def names_of(data: dict) -> list[str]:
    """가릴 이름: 메일함 주인 이름 + 연락처(사람 목록, 주인 제외) — seed.py가 User · Contact로 넣는 것과 같다."""
    box = data["mailbox"]
    return [box.get("name"), *(p.get("name") for p in data["people"].values() if p.get("email") != box["owner"])]
