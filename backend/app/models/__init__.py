"""DB 테이블 (구조도 v3.1 9절). 여기서 모두 불러와야 create_all이 테이블을 만든다."""
from app.models.action import ActionLog, ActionPreview
from app.models.agent import AgentSettings, ContactFact, MailingList, SuggestionHide
from app.models.mail import ClassifyJob, Mail, Task
from app.models.reminder import Notification, PushSubscription, Reminder
from app.models.user import Account, Contact, Template, User, UserSettings

__all__ = [
    "AgentSettings",
    "Account",
    "ActionLog",
    "ActionPreview",
    "ClassifyJob",
    "Contact",
    "ContactFact",
    "Mail",
    "MailingList",
    "Notification",
    "PushSubscription",
    "Reminder",
    "SuggestionHide",
    "Task",
    "Template",
    "User",
    "UserSettings",
]
