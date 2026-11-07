"""backend ↔ ai `POST /classify` 형식 (구조도 v3.1 8절). 바꿀 때는 backend/app/schemas와 함께 고친다(AI-9 · BE-9)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Id, KstDateTime

Category = Literal["회신", "요청", "검토", "공지", "기타"]  # D39
TaskType = Literal["자료제출요청", "회신요청", "검토승인요청", "수정재전송요청", "일정참석", "조치요청"]  # 할 일 유형(AI-D15)
# 할 일 유형 6개 + 할 일 없는 유형 5개. 공유 · 조치요청은 11/7 추가(AI-D15). 참조는 CC로 받은 메일에만 붙는다(조건)
ActionType = Literal["자료제출요청", "회신요청", "검토승인요청", "수정재전송요청", "일정참석", "조치요청", "회신", "공유", "공지", "참조", "기타"]
Priority = Literal["P1", "P2", "P3"]


class OwnerProfile(BaseModel):
    """메일함 주인. backend가 개인정보를 가릴 때 주인 이름 · 팀도 같은 대체어로 바꿨다면 그 대체어를 넣는다."""

    email: str
    name: str | None = None
    position: str | None = None  # '팀장님들께서는' 같은 직급 지목 판별
    team: str | None = None
    member_of: list[str] = []  # 내가 속한 배포 목록 주소
    # 11/8(AI-D15): 내 직책(팀장 · 책임 · 대리 …)으로 받는 배포 목록과 우리 팀 배포 목록. 이 목록으로 온 지시는 나에게 온 것이다.
    # 비우면 단체 메일로만 본다(backend가 주소록 · 조직도에서 채운다)
    role_lists: list[str] = []
    team_lists: list[str] = []


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
    type: TaskType = "회신요청"  # 이 할 일의 유형(AI-D15, 모델이 정한다)
    text: str
    format: str | None = None
    due_raw: str | None = None
    due_at: datetime | None = None  # 시간대 없는 KST
    evidence: str | None = None  # 근거 문장(AI-15 · AI-D14): 본문에 글자 그대로 있는 문장을 줄바꿈으로 이은 것, 못 찾으면 None
    deliver_to: str | None = None  # 결과를 보낼 사람 · 곳(DE-D21 보낼 곳). None이면 요청자(보낸 사람)


# 확인 칸 이유(AI-D15): 나에게 온 회신 · 공유 · 공지 / 모델은 할 일을 비웠는데 요청 어미 문장이 있음 /
# 모델 할 일이었지만 본문이 조건 없이 필요 없다고 밝힘 / 참조로 받았는데 나를 부르지 않음 / 모델 호출 실패(다시 시도 대상)
CheckReason = Literal["회신", "공유", "공지", "요청 문장 있음", "필요 없다고 밝힘", "나를 부르지 않은 참조", "분류 실패"]
Lane = Literal["할 일", "확인", "참고"]  # 화면 칸: 할 일 목록 · 확인 칸 · 읽고 넘김


class CheckOut(BaseModel):
    """확인 칸 항목. 할 일은 아니지만 읽고 확인할 메일. 할 일이 없는 메일에만(pipeline/checks.py). 칸은 수신 조건으로 정한다(AI-D15)."""

    text: str  # 제목 요지. 모델 할 일을 옮긴 것은 그 할 일 문구
    reason: CheckReason
    evidence: str | None = None  # 근거 문장(요청 어미 문장 · 필요 없다고 밝힌 문장)
    source: Literal["rule", "exaone"] = "rule"  # exaone: 모델이 만든 할 일을 옮긴 것(채점에서 재현율 피해를 따로 센다)


class ClassifyResponse(BaseModel):
    mail_id: Id
    category: Category
    action_types: list[ActionType]  # 첫 번째가 주 유형 (data/dummy 라벨과 같다)
    tasks: list[TaskOut]
    checks: list[CheckOut] = []  # 확인 칸. 할 일 목록과 따로 보여 준다(Task 지표에 넣지 않는다)
    lane: Lane = "참고"  # 이 메일이 보일 칸. 할 일이 있으면 할 일, 확인 항목이 있으면 확인, 아니면 참고
    mentioned_me: bool
    urgent: bool
    is_follow_up: bool
    priority: Priority
    source: Literal["rule", "exaone"]  # exaone: 모델 판단을 썼다. rule: 모델 호출이 실패해 조건만으로 낸 결과(fallback에 이유)
    confidence: float | None = None  # 쓰지 않는다(AI-D15: 규칙 확신도 · 라우터 없음). 응답 호환용으로 칸만 둔다
    model: str | None = None
    prompt_version: str | None = None
    rules_version: str  # 조건 판정 버전(pipeline/conditions.py)
    fallback: str | None = None  # 모델 호출이 실패한 이유. 이때 할 일은 비어 있고 확인 칸에 '분류 실패'가 뜬다(다시 시도 대상)
