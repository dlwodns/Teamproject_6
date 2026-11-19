"""DB 테이블 (구조도 v3.1 9절). 여기서 모두 불러와야 create_all이 테이블을 만든다."""
from app.models.action import ActionLog, ActionPreview
from app.models.agent import AgentSettings, ContactFact, MailingList, SuggestionHide
from app.models.calendar import CalendarEvent
from app.models.mail import ClassifyJob, Mail, MailCheck, Task
from app.models.reminder import (BriefingHeadline, Commitment, Notification, PushSubscription, Reminder, ReminderFeedback, ReminderSignal,
                                 SignalCheck)
from app.models.user import Account, Contact, Template, User, UserSettings

__all__ = [
    "AgentSettings",
    "BriefingHeadline",
    "Account",
    "ActionLog",
    "ActionPreview",
    "CalendarEvent",
    "ClassifyJob",
    "Commitment",
    "Contact",
    "ContactFact",
    "Mail",
    "MailCheck",
    "MailingList",
    "Notification",
    "PushSubscription",
    "Reminder",
    "ReminderFeedback",
    "ReminderSignal",
    "SignalCheck",
    "SuggestionHide",
    "Task",
    "Template",
    "User",
    "UserSettings",
]
