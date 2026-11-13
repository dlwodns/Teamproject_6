"""backend ↔ ai `POST /memory/extract` 형식 (PL-16, BE-D21). 바꿀 때는 backend/app/schemas/ai.py와 함께 고친다.

문맥 기억: 메일 문장을 읽고, **보낸 사람**에 대해 업무에 쓸 사실을 정해진 칸으로만 뽑는다(BE-D18: 자유 문장 기억은 두지 않는다).
- works_on: 그 사람이 맡은 거래처 · 프로젝트 · 업무(짧은 명사구). 예: "한빛은행 2단계 전환"
- org: 그 사람의 소속(회사 · 부서). 예: "한빛은행 IT기획부"
근거 문장(evidence)은 본문에 글자 그대로 있어야 한다. 없으면 버린다(지어낸 기억 방지, AI-15와 같은 방식).
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Id

FactKind = Literal["works_on", "org"]


class MemoryOwner(BaseModel):
    email: str
    name: str | None = None
    position: str | None = None
    team: str | None = None


class MemoryExtractRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mail_id: Id
    from_: str = Field(alias="from")
    sender_name: str | None = None
    subject: str = ""
    body: str = ""  # 개인정보를 가린 본문(BE-6)
    owner: MemoryOwner


class Fact(BaseModel):
    kind: FactKind
    value: str
    evidence: str


class MemoryExtractResponse(BaseModel):
    mail_id: Id
    facts: list[Fact] = []
    source: Literal["exaone", "none"]  # none: 모델을 부르지 못해 뽑지 않음(fallback에 이유)
    model: str | None = None
    prompt_version: str
    fallback: str | None = None
