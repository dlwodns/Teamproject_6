"""제안 카드 · 기록 탭 · 에이전트가 아는 것 요청 · 응답 (D50 · PL-16).

계약 문서: docs/30_backend/agent_api_contract.md. 형식을 바꾸면 계약 문서와 시나리오를 함께 고친다.
응답 시각은 +09:00이 붙은 KST다(D47).
"""
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

ADDRESS = re.compile(r"[^@\s,;<>\"']+@[^@\s,;<>\"']+")
Rule = Literal["morning", "overdue", "due_soon", "priority_sender", "meeting", "no_reply"]


class Target(BaseModel):
    task_ids: list[int]
    mail_ids: list[int]


class Button(BaseModel):
    label: str
    kind: Literal["action", "navigate", "hide"]  # action: 등록된 행동(T01~) · navigate: 화면 이동 · hide: 숨기기
    action: str
    primary: bool
    params: dict
    target: Target


class Suggestion(BaseModel):
    key: str
    rule: Rule
    via: str  # 버튼으로 행동을 부를 때 그대로 넘긴다(action_log.params_json.via)
    created_at: datetime
    title: str
    detail: list[str]
    task_ids: list[int]
    mail_ids: list[int]
    buttons: list[Button]
    menu: list[Button]


class SuggestionList(BaseModel):
    suggestions: list[Suggestion]
    more: int  # 접힌 카드 수("제안 N건 더 보기")
    total: int
    generated_at: datetime


class HideResult(BaseModel):
    key: str
    hidden_until: datetime


class HistoryItem(BaseModel):
    id: str  # log:<action_id> | preview:<preview_id>
    state: Literal["waiting", "done", "undone"]
    action: str
    action_id: int | None
    preview_id: str | None
    text: str
    via: str
    via_label: str
    auto: bool
    at: datetime
    expires_at: datetime | None
    can_undo: bool
    redo_action_id: int | None  # 되돌림 줄의 [다시 하기]: POST /api/actions/{redo_action_id}/undo


class HistoryList(BaseModel):
    items: list[HistoryItem]
    days: int


class Origin(BaseModel):
    at: datetime | None
    text: str


ListKind = Literal["role", "team", "all"]


class MailingListItem(BaseModel):
    address: str
    kind: ListKind  # role: 내 직책 목록 · team: 우리 팀 목록 · all: 전사 · 단체(나에게 온 지시로 보지 않음)


class MemoryMe(BaseModel):
    name: str
    department: str | None
    position: str | None
    mailing_lists: list[MailingListItem]
    uses: str
    used_by: list[str]  # 이 값을 실제로 읽는 곳(메일 분류 · 제안 카드)
    origin: Origin


class MemoryFactView(BaseModel):
    kind: Literal["works_on", "org"]
    label: str  # 맡은 일 · 소속
    value: str
    evidence: str | None  # 메일 본문에 그대로 있던 근거 문장


class MemoryPerson(BaseModel):
    contact_id: int
    name: str | None
    email: str
    position: str | None
    is_superior: bool
    is_favorite: bool
    facts: list[MemoryFactView]  # 문맥 기억(모델, BE-D21)
    uses: str
    used_by: list[str]
    origin: Origin


class MemoryView(BaseModel):
    learn_from_mail: bool  # 설정 '메일 기억하기'(화면 위쪽 켬 · 끔)
    me: MemoryMe
    people: list[MemoryPerson]


class MemoryChange(BaseModel):
    action_id: int | None  # 바뀐 것이 없으면 None(기록도 없다). 되돌리기는 POST /api/actions/{id}/undo
    memory: MemoryView


class MailingListIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: str
    kind: ListKind


class MeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    department: str | None = Field(default=None, max_length=100)
    position: str | None = Field(default=None, max_length=50)
    # 문자열(종류는 주소로 짐작) 또는 {"address", "kind"}
    mailing_lists: list[str | MailingListIn] | None = Field(default=None, max_length=20)

    @field_validator("mailing_lists")
    @classmethod
    def _addresses(cls, v):
        if v is None:
            return v
        out = []
        for x in v:
            a = (x if isinstance(x, str) else x.address).strip().lower()
            if not (3 <= len(a) <= 255) or not ADDRESS.fullmatch(a):
                raise ValueError(f"배포 목록 주소 형식이 아닙니다: {a!r}")
            out.append(a if isinstance(x, str) else {"address": a, "kind": x.kind})
        return out

    @field_validator("department", "position")
    @classmethod
    def _blank_is_none(cls, v: str | None) -> str | None:
        return (v.strip() or None) if isinstance(v, str) else v


class PersonUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_superior: StrictBool | None = None  # "no" · 0 같은 값은 받지 않는다
    is_favorite: StrictBool | None = None
    # 문맥 기억 고치기 · 지우기: {"works_on": "새 값"} · {"org": null}(지움)
    facts: dict[Literal["works_on", "org"], str | None] | None = None

    @field_validator("facts")
    @classmethod
    def _fact_values(cls, v):
        for k, x in (v or {}).items():
            if x is not None and not (1 <= len(x.strip()) <= 40):
                raise ValueError(f"{k} 값은 1~40자")
        return v


class AgentSettingsView(BaseModel):
    learn_from_mail: bool


class AgentSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    learn_from_mail: StrictBool
