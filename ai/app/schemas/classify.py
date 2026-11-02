"""backend ↔ ai `POST /classify` 형식 (구조도 v3.1 8절). 바꿀 때는 backend/app/schemas와 함께 고친다(AI-9 · BE-9)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Category = Literal["회신", "요청", "검토", "공지", "기타"]  # D39
ActionType = Literal["자료제출요청", "수정재전송요청", "회신요청", "검토승인요청", "일정참석", "공지", "참조", "회신", "기타"]
Priority = Literal["P1", "P2", "P3"]


class OwnerProfile(BaseModel):
    """메일함 주인. backend가 개인정보를 가릴 때 주인 이름 · 팀도 같은 대체어로 바꿨다면 그 대체어를 넣는다."""

    email: str
    name: str | None = None
    position: str | None = None  # '팀장님들께서는' 같은 직급 지목 판별
    team: str | None = None
    member_of: list[str] = []  # 내가 속한 배포 목록 주소


class SenderFlags(BaseModel):
    is_superior: bool = False  # contacts.is_superior (D9)
    is_favorite: bool = False  # contacts.is_favorite


class ClassifyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    mail_id: str
    from_: str = Field(alias="from")
    to: list[str] = []
    cc: list[str] = []
    subject: str = ""
    body: str = ""  # 개인정보를 가린 본문
    attachments: list[str] = []
    received_at: datetime
    owner: OwnerProfile
    sender: SenderFlags = SenderFlags()


class TaskOut(BaseModel):
    text: str
    format: str | None = None
    due_raw: str | None = None
    due_at: datetime | None = None
    evidence: str | None = None  # 근거 문장 (T08 · 본문 비저장 정책과 함께 사용 여부 결정)


class ClassifyResponse(BaseModel):
    mail_id: str
    category: Category
    action_types: list[ActionType]  # 첫 번째가 주 유형 (data/dummy 라벨과 같다)
    tasks: list[TaskOut]
    mentioned_me: bool
    urgent: bool
    is_follow_up: bool
    priority: Priority
    source: Literal["rule", "exaone"]
    confidence: float
    model: str | None = None
    prompt_version: str | None = None
    rules_version: str
    fallback: str | None = None  # 엑사원으로 보내려 했으나 실패해 규칙 결과를 쓴 이유
