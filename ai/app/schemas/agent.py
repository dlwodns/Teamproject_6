"""backend ↔ ai `POST /agent/plan` 형식 (구조도 v3.1 6 · 8절, AI detail 4.4절)."""
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel

from app.schemas.common import Id, KstDateTime


class ActionSpec(BaseModel):
    """backend 행동 레지스트리가 보내는 허용 행동. 이 목록 밖의 행동은 고르지 않는다(D27)."""

    id: str  # T01 ~ T14
    name: str  # 오늘_요약 등
    description: str | None = None


class PlanContext(BaseModel):
    now: KstDateTime  # 시간대가 붙어 오면 KST로 바꿔 시간대를 뗀다(common.py)
    selected_mail_ids: list[Id] = []  # 지시어('이거' · '선택한') 해석용, 프론트가 보낸다
    last_result_ids: list[Id] = []  # 직전 조회 결과(예: T06 무응답 목록). '그 2건 재촉해' 해석용


class PlanRequest(BaseModel):
    text: str
    actions: list[ActionSpec]
    context: PlanContext


class DateRange(BaseModel):
    start: date
    end: date


class Target(BaseModel):
    sender: str | None = None  # '김 팀장' — backend가 contacts와 맞춘다
    category: Literal["회신", "요청", "검토", "공지", "기타"] | None = None
    date_range: DateRange | None = None
    keyword: str | None = None  # '견적 건' → 견적 (제목 키워드)
    mail_ids: list[Id] = []  # 문자열로 돌려준다(정수 id도 문자열)
    awaiting_reply: bool = False  # 무응답 목록 전체가 대상 (T14 재촉)


class PlanResponse(BaseModel):
    action: str | None  # 행동 ID (T03 등). 지원하지 않으면 None
    action_name: str | None = None
    target: Target = Target()
    params: dict[str, Any] = {}
    source: Literal["rule", "model"]
    reason: Literal["unsupported", "ambiguous"] | None = None
    candidates: list[str] = []  # 규칙이 여러 행동에 걸렸을 때 후보 (디버깅 · 평가용)
    prompt_version: str | None = None
    rules_version: str
    fallback: str | None = None
