"""ai로 보내는 값에서 개인정보를 가리고, ai 응답은 원래 값으로 되돌린다 (BE-6 · D34 · 구조도 10절).

엑사원 API(D53)를 쓰면 메일 본문이 바깥으로 나간다. 그래서 요청 하나마다 대응표를 만들어 가리고, 대응표는 이 프로세스
메모리에만 둔다(DB · 로그 · ai에 남기지 않는다). 같은 값은 한 요청 안에서 늘 같은 대체어가 된다.

무엇을 어떻게 가리나 — ai 판단이 깨지지 않게 판단에 쓰는 부분은 남긴다(ai/app/pipeline/conditions.py):
- 메일 주소: 앞부분만 user1 · user2 …로 바꾸고 도메인은 남긴다(사내 · 외부 발신 판별). noreply · info 같은
  자동 발신 앞부분은 남긴다(자동 메일 판별). 받는 사람 · 내 주소 · 배포 목록이 같은 대체어라 '나에게 왔나'도 그대로다.
- 이름: 내 이름과 연락처 이름을 성 + ◯◯로 바꾼다(김민준 → 김◯◯). 성은 남긴다('김 팀장님께서' 지목 판별).
  성이 같은 다른 사람은 뒤에 번호를 붙인다(김민보 → 김◯◯2). 같은 대체어면 ai가 두 사람을 섞고, 되돌릴 때도 누구인지 모른다.
  이름만 부르는 경우(민준님)나 연락처에 없는 이름은 가리지 못한다.
- 전화번호 · 주민등록번호 · 카드번호: [전화번호 1] · [주민번호 1] · [카드번호 1].
- 팀 이름 · 직책 · 회사 도메인은 사람을 가리키지 않아 그대로 둔다(분류에 쓴다).

끄기: PII_MASK=0(디버깅용). 기본은 켜짐.
"""
import logging
import os
import re
from collections.abc import Iterable
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Contact, User

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
# ai 자동 발신 판별(ai/app/pipeline/conditions.py AUTO_SENDER)과 같은 앞부분은 남긴다. 한쪽을 바꾸면 다른 쪽도 같이 바꾼다.
# 한계: \b가 . · - 앞에서도 끊겨 info.kim@ · admin-park@ 같은 개인 주소도 앞부분이 그대로 남는다(ai 판별과 맞추려고 둔다)
AUTO_LOCAL = re.compile(r"^(?:info|news|newsletter|noreply|no-?reply|donotreply|mailer|notice|alert|alerts|system|admin"
                        r"|marketing)\b", re.I)
PHONE = re.compile(r"(?<![\d-])(?:\+82[-\s.]?|0)(?:1[016789]|2|[3-6][1-5]|70)[-\s.]?\d{3,4}[-\s.]?\d{4}(?![\d-])")
RRN = re.compile(r"(?<!\d)\d{6}-[1-4]\d{6}(?!\d)")
CARD = re.compile(r"(?<!\d)\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}(?!\d)")
MIN_NAME = 2
# 되돌린 뒤에도 남은 대체어 모양. 모델이 ◯를 ○ · O로 바꾸거나 user1@도메인에서 도메인을 빼면 되돌리지 못한다(#94 리뷰)
LEFTOVER = re.compile(r"[가-힣][◯○]{2}|\[(?:전화번호|주민번호|카드번호) \d+\]|(?<![A-Za-z0-9])user\d+(?!\d)")
log = logging.getLogger("app.privacy")

T = TypeVar("T", bound=BaseModel)


def enabled() -> bool:
    return os.environ.get("PII_MASK", "").strip().lower() not in ("0", "off", "false")


class Masker:
    """요청 하나에 하나. mask_obj로 가리고, 같은 객체의 unmask_obj · unmask_model로 응답을 되돌린다."""

    def __init__(self, names: Iterable[str | None] = (), *, on: bool = True):
        self.on = on
        self._forward: dict[str, str] = {}  # 원래 값(소문자 키) → 대체어
        self._back: dict[str, str] = {}  # 대체어 → 원래 값
        self._count: dict[str, int] = {}
        uniq = {n.strip() for n in names if n and len(n.strip()) >= MIN_NAME}
        self._names = sorted(uniq, key=len, reverse=True)  # 긴 이름부터(김민준이 김민보다 먼저)
        self._name_re = (re.compile(r"(?<![가-힣A-Za-z])(?:" + "|".join(map(re.escape, self._names)) + ")")
                         if self._names else None)

    def _token(self, kind: str, original: str, make, counter: str | None = None) -> str:
        """original의 대체어. 처음 보면 counter(기본 kind)별 번호로 make(n)을 만든다."""
        key = f"{kind}:{original.lower()}"
        if key not in self._forward:
            counter = counter or kind
            self._count[counter] = self._count.get(counter, 0) + 1
            token = make(self._count[counter])
            self._forward[key], self._back[token] = token, original
        return self._forward[key]

    def _email(self, m: re.Match) -> str:
        addr = m.group(0)
        local, domain = addr.rsplit("@", 1)
        if AUTO_LOCAL.match(local):
            return addr
        return self._token("email", addr, lambda n: f"user{n}@{domain}")

    def mask_text(self, text: str) -> str:
        if not self.on or not text:
            return text
        text = EMAIL.sub(self._email, text)
        text = RRN.sub(lambda m: self._token("rrn", m.group(0), lambda n: f"[주민번호 {n}]"), text)
        text = CARD.sub(lambda m: self._token("card", m.group(0), lambda n: f"[카드번호 {n}]"), text)
        text = PHONE.sub(lambda m: self._token("phone", m.group(0), lambda n: f"[전화번호 {n}]"), text)
        if self._name_re:
            text = self._name_re.sub(self._name, text)
        return text

    def _name(self, m: re.Match) -> str:
        """김민준 → 김◯◯, 같은 성의 둘째 사람부터 김◯◯2 · 김◯◯3(성마다 번호를 따로 센다)."""
        name = m.group(0)
        surname = name[0]
        return self._token("name", name, lambda n: f"{surname}◯◯" + (str(n) if n > 1 else ""), counter=f"name:{surname}")

    def mask_obj(self, obj: Any) -> Any:
        """dict · list 안의 글자를 모두 가린다. 키 · 숫자 · 시각은 그대로."""
        if isinstance(obj, str):
            return self.mask_text(obj)
        if isinstance(obj, dict):
            return {k: self.mask_obj(v) for k, v in obj.items()}
        if isinstance(obj, list | tuple):
            return [self.mask_obj(v) for v in obj]
        return obj

    def unmask_text(self, text: str) -> str:
        if not self._back or not text:
            return text
        # 긴 대체어부터(user12가 user1보다 먼저)
        pattern = re.compile("|".join(map(re.escape, sorted(self._back, key=len, reverse=True))))
        return pattern.sub(lambda m: self._back[m.group(0)], text)

    def unmask_obj(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.unmask_text(obj)
        if isinstance(obj, dict):
            return {k: self.unmask_obj(v) for k, v in obj.items()}
        if isinstance(obj, list | tuple):
            return [self.unmask_obj(v) for v in obj]
        return obj

    def unmask_model(self, model: T) -> T:
        if not self._back:
            return model
        data = self.unmask_obj(model.model_dump(by_alias=True))
        left = self.leftover(data)
        if left:
            log.warning("되돌리지 못한 대체어 %d개 (%s)", left, type(model).__name__)  # 값은 남기지 않는다
        return type(model).model_validate(data)

    @staticmethod
    def leftover(obj: Any) -> int:
        """되돌린 결과에 남은 대체어 모양 수. 엑사원 평가 때 로그로 본다."""
        if isinstance(obj, str):
            return len(LEFTOVER.findall(obj))
        if isinstance(obj, dict):
            return sum(Masker.leftover(v) for v in obj.values())
        if isinstance(obj, list | tuple):
            return sum(Masker.leftover(v) for v in obj)
        return 0

    @property
    def masked(self) -> int:
        """가린 값 수(로그 · 테스트용. 값 자체는 내보내지 않는다)."""
        return len(self._back)


def masker_for(db: Session, user_id: int) -> Masker:
    """그 사용자의 이름 · 연락처 이름으로 가리개를 만든다. PII_MASK=0이면 아무것도 바꾸지 않는다."""
    if not enabled():
        return Masker(on=False)
    me = db.get(User, user_id)
    names = [me.name if me else None, *db.scalars(select(Contact.name).where(Contact.user_id == user_id)).all()]
    return Masker(names)
