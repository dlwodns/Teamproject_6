"""업무 상태 변경 · 일괄 변경 미리보기 · 실행 · 되돌리기 요청 · 응답 (구조도 v3.1 8절, BE-4).

응답 시각은 +09:00이 붙은 KST다(D47). 요청 시각은 시간대가 있어도 없어도 받는다(없으면 KST로 본다).
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Status = Literal["pending", "done", "excluded", "snoozed"]  # D36 · 구조도 5절. 그 밖의 값은 422


# 어느 화면에서 눌렀는지. 제안 카드(D50)는 suggestion:<카드 종류>, 기록 탭은 history (PL-16)
Via = Field(default=None, max_length=40, pattern=r"^[a-z_]+(:[a-z_]+)?$")


class StatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid")  # 'vai' 같은 오타 칸이 조용히 빠지지 않게(PL-16)

    status: Status
    snoozed_until: datetime | None = None  # status가 snoozed일 때만, 그때는 필수
    via: str | None = Via

    @field_validator("snoozed_until", mode="before")
    @classmethod
    def _date_and_time(cls, v):
        # 숫자(epoch) · 날짜만 있는 값은 받지 않는다. "2026-11-12T09:00:00+09:00"처럼 날짜와 시각을 함께(D47)
        if v is not None and (not isinstance(v, str) or "T" not in v.upper()):
            raise ValueError("snoozed_until은 날짜와 시각이 있는 ISO 문자열이어야 합니다")
        return v


class BulkPreviewRequest(StatusChange):
    task_ids: list[int] = Field(min_length=1, max_length=500)


class ExecuteRequest(BaseModel):
    # 확인한 뒤 대상 · 상태를 바꿔 끼우려면 새 미리보기가 필요하다(PL-16 S4). task_ids는 미리보기 대상 안에서 줄이기만 한다
    model_config = ConfigDict(extra="forbid")

    preview_id: str
    task_ids: list[int] | None = Field(default=None, max_length=500)  # 확인 카드에서 체크한 업무만(UX-D8, #31). 없으면 전부


class TaskState(BaseModel):
    id: int
    status: Status
    done_at: datetime | None
    snoozed_until: datetime | None
    status_changed_at: datetime | None


class ActionResult(BaseModel):
    action_id: int | None  # 되돌리기에 쓴다. 바뀐 업무가 없으면 None(기록도 남기지 않는다)
    tasks: list[TaskState]


class UndoResult(ActionResult):
    undone_action_id: int


class PreviewTarget(BaseModel):
    id: int
    text: str
    status: Status  # 지금 상태


class PreviewResult(BaseModel):
    preview_id: str
    expires_at: datetime
    status: Status  # 바뀔 상태
    snoozed_until: datetime | None
    targets: list[PreviewTarget]
