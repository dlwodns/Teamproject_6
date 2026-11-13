"""리마인더 · 알림 센터 · 브리핑 요청 · 응답 (BE-12, 명세 docs/10_planning/reminders.md 7.2절).

JSON 칸 이름은 snake_case다. 응답 시각은 +09:00이 붙은 KST다(D47). 형식을 바꾸면 FE-16 · FE-10과 함께 고친다.
"""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictBool

from app.schemas.actions import TaskState

Group = Literal["due", "waiting", "promise", "revisit", "prepare", "cleanup"]


class ReminderAction(BaseModel):
    id: str  # 버튼 id(draft · open_mail · snooze · done · apply · keep · not_mine · stop_waiting …)
    label: str
    action: str  # 행동 레지스트리 T코드 | open_mail | apply | dismiss
    primary: bool
    params: dict  # T05 until(null이면 화면이 고름) · T07 mail_id · tone · dismiss reason · open_mail mail_id · T13 start · end


class Counterpart(BaseModel):
    email: str
    name: str
    position: str | None
    label: str  # '김민준 팀장님(한빛은행 담당)'


class ReminderItem(BaseModel):
    key: str  # overdue:task:12 · no_reply:sent_mail:31 · my_promise:commitment:4 · due_cluster:day:20261114
    type: str
    type_label: str
    group: Group
    title: str
    reason: str
    evidence: str | None
    task_id: int | None
    task_ids: list[int]  # 기한 몰림은 그날 업무 전부, 업무 항목은 [task_id]
    mail_id: int | None
    commitment_id: int | None
    due_at: datetime | None
    counterpart: Counterpart | None
    created_at: datetime
    state: Literal["active", "quiet"]  # quiet = 3번 알린 뒤 '조용히 둠'(목록에만)
    notify_count: int
    last_notified_at: datetime | None = None  # 이 항목을 마지막으로 알린 시각(묶음 알림 포함). 알린 적 없으면 null
    notify: bool  # 이 항목이 알림을 보내는 유형인가(유형 알림 끔 · 목록에만 두는 유형이면 false)
    actions: list[ReminderAction]


class Counts(BaseModel):
    due: int
    waiting: int
    promise: int
    revisit: int
    prepare: int
    cleanup: int
    all: int


class ReminderList(BaseModel):
    as_of: datetime
    counts: Counts
    muted_types: list[str]
    items: list[ReminderItem]


class DismissRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # hide: 다음 R-아침까지 숨김 · not_mine: 내 일 아님(T10) · wrong_signal: 잘못 알아챘어요 · keep: 그대로 두기 / 아직 남았어요
    # · stop_waiting: 그만 기다리기
    reason: Literal["hide", "not_mine", "wrong_signal", "keep", "stop_waiting"]


class DismissResult(BaseModel):
    key: str
    reason: str
    hidden_until: datetime | None
    action_id: int | None  # not_mine이면 T10 기록(되돌리기 POST /api/actions/{id}/undo)


class ApplyResult(BaseModel):
    key: str
    action_id: int | None  # 되돌리기 POST /api/actions/{id}/undo
    task: TaskState | None
    due_at: datetime | None  # due_changed면 바뀐 기한
    commitment_id: int | None


class TypeNotify(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notify: StrictBool


class TypeNotifyResult(BaseModel):
    type: str
    notify: bool
    muted_types: list[str]


class NotificationView(BaseModel):
    id: int
    kind: Literal["reminder", "reply_confirm", "digest"]
    type: str | None  # 리마인더 유형. digest는 digest · away_return · evening · weekly
    group: str | None
    reminder_key: str | None
    reminder_keys: list[str]  # digest에 들어간 항목
    title: str
    body: str | None
    task_ids: list[int]
    rule: str | None  # R-아침 · R-기한 · R-나중에 · R-회의 · R-즉시 · R-복귀 · R-퇴근 · R-주간
    scheduled_at: datetime | None
    read_at: datetime | None
    answered_at: datetime | None
    created_at: datetime


class NotificationList(BaseModel):
    items: list[NotificationView]
    unread: int  # 🔔 숫자(안 읽은 알림 수, 화면이 10 이상을 9+로)


class NotificationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    read: Literal[True] | None = None
    answer: Literal["yes", "no"] | None = None  # reply_confirm에만. yes = 완료(T03), no = 아직 남았어요


class ReadAllResult(BaseModel):
    updated: int


class BriefingLine(BaseModel):
    task_id: int | None
    mail_id: int | None
    commitment_id: int | None
    reminder_key: str | None
    title: str
    reason: str | None
    due_at: datetime | None
    action_id: int | None  # 답장으로 바로 완료된 업무의 기록(되돌리기)
    actions: list[ReminderAction]


class BriefingSection(BaseModel):
    id: str  # morning: due_today · overdue · no_reply · my_promise · auto_done / evening: done_today · remaining ·
    # due_tomorrow / weekly: done_week · near_miss · waiting
    label: str
    count: int
    items: list[BriefingLine]


class Briefing(BaseModel):
    kind: Literal["morning", "evening", "weekly"]
    date: date
    as_of: datetime  # 센 기준 시각. 오늘이면 지금, 지난날은 scheduled_at, 앞날은 지금
    scheduled_at: datetime  # 이 브리핑을 만드는 시각(아침 R-아침 · 퇴근 근무 끝 30분 전 · 주간 그 주 금요일 같은 시각). as_of가 이보다 이르면 아직 만들 때가 아니다
    title: str
    summary: str  # 무엇이 있는지만 적은 정해진 문장(할 일을 권하지 않는다)
    total: int
    sections: list[BriefingSection]


class RunResult(BaseModel):
    at: datetime
    results: list[dict]
