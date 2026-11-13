"""리마인더 유형 · 묶음 · 우선순위 · 알림 시각 규칙 (명세 reminders.md 3 · 4.1절, 공통 D57 · BE-D26 · BE-D27).

유형 코드 · 묶음 코드는 backend · frontend 공동 계약이다(`GET /api/reminders` 응답 그대로). 바꾸면 FE-16과 함께 고친다.
'나중' 단계 유형(delegated · recurring)은 코드 값만 예약하고 만들지 않는다(명세 3절).
"""
from dataclasses import dataclass

GROUPS = ("due", "waiting", "promise", "revisit", "prepare", "cleanup")  # 화면 왼쪽 메뉴 · 🔔 칩 순서
GROUP_LABEL = {"due": "기한", "waiting": "답 기다림", "promise": "내 약속", "revisit": "다시 볼 일", "prepare": "준비",
               "cleanup": "정리 제안"}

# 알림을 보내는 때(명세 4.1절)
MORNING = "morning"  # R-아침에 몰아서(날마다 다시 셀 수 있음, 간격 1일 → 2일, 3번이면 조용히 둠)
DUE = "due"  # 기한 3시간 전(R-기한). 근무 시간 밖에도 보낸다(조용한 시간 제외)
SNOOZE = "snooze"  # 미룬 시각(R-나중에)
MEETING = "meeting"  # 시작 30분 전
IMMEDIATE = "immediate"  # 알아챈 즉시(근무 시간이면)
NEVER = None  # 목록과 아침 브리핑에만

RULE_NAME = {MORNING: "R-아침", DUE: "R-기한", SNOOZE: "R-나중에", MEETING: "R-회의", IMMEDIATE: "R-즉시"}


@dataclass(frozen=True)
class ReminderType:
    code: str
    group: str
    label: str  # 항목 줄의 회색 글자
    notify: str | None  # 위 알림 시각 규칙. my_promise는 기한이 없으면 MORNING(rules가 정함)
    subject: str  # task | sent_mail | commitment | day
    later: bool = False  # '나중' 단계(만들지 않음)


_TYPES = [
    ReminderType("overdue", "due", "기한 지남", MORNING, "task"),
    ReminderType("due_soon", "due", "기한 임박", DUE, "task"),
    ReminderType("due_changed", "due", "기한 바뀜", IMMEDIATE, "task"),
    ReminderType("due_cluster", "due", "기한 몰림", MORNING, "day"),
    ReminderType("no_reply", "waiting", "답 없음", MORNING, "sent_mail"),
    ReminderType("their_promise", "waiting", "상대 약속 지남", MORNING, "commitment"),
    ReminderType("my_promise", "promise", "내가 한 약속", DUE, "commitment"),
    ReminderType("delegated", "promise", "넘긴 일", NEVER, "task", later=True),
    ReminderType("snooze_due", "revisit", "미룬 일", SNOOZE, "task"),
    ReminderType("priority_sender", "revisit", "상급자 메일", NEVER, "task"),
    ReminderType("cc_mention", "revisit", "참조 속 지목", NEVER, "task"),
    ReminderType("stale", "revisit", "오래 둔 일", MORNING, "task"),
    ReminderType("stalled_thread", "revisit", "끊긴 대화", NEVER, "task"),
    ReminderType("meeting_prep", "prepare", "회의 준비", MEETING, "task"),
    ReminderType("recurring", "prepare", "반복 업무", NEVER, "day", later=True),
    ReminderType("resolved", "cleanup", "끝난 것 같아요", IMMEDIATE, "task"),
    ReminderType("reply_confirm", "cleanup", "답장 보냈어요", IMMEDIATE, "task"),
]
TYPES: dict[str, ReminderType] = {t.code: t for t in _TYPES}
ACTIVE_TYPES = tuple(t.code for t in _TYPES if not t.later)  # 이번 단계에 만드는 유형

# 업무 하나에는 항목 하나(D50 원칙 4). 여러 유형에 걸리면 이 순서에서 앞선 것 하나만(명세 3절).
# reply_confirm은 명세 순서표에 없어 같은 정리 제안인 resolved 바로 뒤에 둔다(BE-D27): 이미 답장한 일을 "기한 지남"으로
# 재촉하지 않기 위해서다.
TASK_PRIORITY = ("resolved", "reply_confirm", "due_changed", "overdue", "due_soon", "meeting_prep", "snooze_due",
                 "priority_sender", "cc_mention", "stalled_thread", "stale")


def label(code: str) -> str:
    t = TYPES.get(code)
    return t.label if t else code
