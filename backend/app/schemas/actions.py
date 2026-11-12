"""업무 상태 변경 · 일괄 변경 미리보기 · 실행 · 되돌리기 요청 · 응답 (구조도 v3.1 8절, BE-4).

응답 시각은 +09:00이 붙은 KST다(D47). 요청 시각은 시간대가 있어도 없어도 받는다(없으면 KST로 본다).
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["pending", "done", "excluded", "snoozed"]  # D36 · 구조도 5절. 그 밖의 값은 422


class StatusChange(BaseModel):
    status: Status
    snoozed_until: datetime | None = None  # status가 snoozed일 때만, 그때는 필수


class BulkPreviewRequest(StatusChange):
    task_ids: list[int] = Field(min_length=1, max_length=500)


class ExecuteRequest(BaseModel):
    preview_id: str
    task_ids: list[int] | None = None  # 확인 카드에서 체크한 업무만(미리보기 대상 안에서). 없으면 전부(UX-D8)


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
