"""backend ↔ ai `POST /classify` 형식 (구조도 v3.1 8절). 바꿀 때는 backend/app/schemas와 함께 고친다(AI-9 · BE-9)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Id, KstDateTime

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

    mail_id: Id  # backend DB id(정수)도 받는다. 응답에는 문자열로 돌려준다
    from_: str = Field(alias="from")
    to: list[str] = []
    cc: list[str] = []
    subject: str = ""
    body: str = ""  # 개인정보를 가린 본문
    attachments: list[str] = []
    received_at: KstDateTime  # 시간대가 붙어 오면 KST로 바꿔 시간대를 뗀다(common.py)
    owner: OwnerProfile
    sender: SenderFlags = SenderFlags()


class TaskOut(BaseModel):
    text: str
    format: str | None = None
    due_raw: str | None = None
    due_at: datetime | None = None  # 시간대 없는 KST
    evidence: str | None = None  # 근거 문장(AI-15 · AI-D14): 본문에 글자 그대로 있는 문장을 줄바꿈으로 이은 것, 못 찾으면 None


CheckReason = Literal["결과 회신", "완료 보고", "해당 여부 확인", "시스템 알림", "읽고 확인"]
Lane = Literal["할 일", "확인", "참고"]  # 화면 칸(사용자 항목 2): 할 일 목록 · 확인 칸 · 읽고 넘김


class CheckOut(BaseModel):
    """확인 칸 항목(사용자 항목 2, 11/3). 할 일은 아니지만 읽고 확인할 메일. 할 일이 없는 메일에만, 메일 1통에 1개(pipeline/checks.py)."""

    text: str  # 제목 요지. 엑사원 할 일을 옮긴 것은 그 할 일 문구
    reason: CheckReason
    evidence: str | None = None  # 근거 문장(완료 · 회신 · 당부 문장)
    source: Literal["rule", "exaone"] = "rule"  # exaone: 엑사원이 만든 할 일을 옮긴 것(채점에서 재현율 피해를 따로 센다)


class ClassifyResponse(BaseModel):
    mail_id: Id
    category: Category
    action_types: list[ActionType]  # 첫 번째가 주 유형 (data/dummy 라벨과 같다)
    tasks: list[TaskOut]
    checks: list[CheckOut] = []  # 확인 칸. 할 일 목록과 따로 보여 준다(Task 지표에 넣지 않는다)
    kind: str | None = None  # 메일 성격 K01~K21(pipeline/kinds.py, 사용자 항목 3). 맞는 형식이 없으면 None
    kind_name: str | None = None  # 예: 완료 보고 · 사외 홍보 · 초청
    kind_sure: bool = False  # kind 형식 점수가 확신(여유 · 근거 충분)이면 true. false면 유형은 엑사원 · 규칙이 정했다
    lane: Lane = "참고"  # 이 메일이 보일 칸. 할 일이 있으면 할 일, 확인 항목이 있으면 확인, 아니면 참고
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
