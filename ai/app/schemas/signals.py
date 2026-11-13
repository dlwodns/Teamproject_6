"""backend ↔ ai `POST /signals` 형식 (AI-24 · AI-D20, 명세 `docs/10_planning/reminders.md` 8절). 바꿀 때는 backend(BE-12)와 함께 고친다.

리마인더 신호: 메일 한 통을 읽고 약속 · 기한 변경 · 해결 · 나에게 온 질문을 돌려준다. 판단은 모델이 하고, 코드는 형식만 지킨다.
- 근거(evidence)는 이 메일 본문에 글자 그대로 있는 문장이어야 한다. 못 찾으면 그 신호를 버린다(AI-D14 형식: 문장을 줄바꿈으로 이음)
- 날짜는 메일 보낸 시각(sent_at) 기준으로 코드가 계산한다(`pipeline/dates.py`). 못 정하면 due_at은 null, 문구(due_raw)는 남긴다
- task_id는 받은 open_tasks 안의 것만 돌려준다
- 모델이 판단하지 못하면 신호 없이 source=none · fallback에 이유를 적어 200으로 돌려준다. backend는 fallback을 보고 다시 부른다(AI-D19)
"""
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field

from app.schemas.common import Id, KstDateTime

THREAD_MAX = 5  # 같은 대화의 앞 메일은 최근 5통까지만 모델에 넣는다
THREAD_CHARS = 400  # 앞 메일 본문은 앞 400자만


class SignalMail(BaseModel):
    direction: Literal["received", "sent"]  # received: 받은 메일(상대가 씀) · sent: 내가 보낸 메일
    sender: str = ""
    recipients: list[str] = []
    cc: list[str] = []
    subject: str = ""
    body: str = ""  # 개인정보를 가린 본문(BE-6)
    sent_at: KstDateTime  # 날짜 계산의 기준 시각


class SignalMe(BaseModel):
    email: str
    name: str | None = None


class ThreadMail(BaseModel):
    sender: str = ""
    sent_at: KstDateTime | None = None
    subject: str = ""
    body: str = Field("", validation_alias=AliasChoices("body", "snippet"))  # 앞 400자. 더 길면 ai가 자른다


class OpenTask(BaseModel):
    task_id: Id
    text: str
    due_at: KstDateTime | None = None


class SignalsRequest(BaseModel):
    mail_id: Id | None = None  # 응답에 그대로 돌려준다(로그 · 짝 맞추기용, 없어도 된다)
    mail: SignalMail
    me: SignalMe
    thread: list[ThreadMail] = []  # 오래된 것 → 최근 순. 5통을 넘으면 최근 5통만 쓴다
    open_tasks: list[OpenTask] = []  # 이 대화의 미처리 업무


class Commitment(BaseModel):
    who: Literal["me", "them"]  # 보낸 메일이면 me(내 약속), 받은 메일이면 them(상대 약속)
    text: str  # 무엇을 하겠다(짧은 문구)
    due_raw: str | None = None  # 메일에 적힌 기한 문구. 없으면 null
    due_at: KstDateTime | None = None  # 시간대 없는 KST. 문구로 날짜를 정할 수 없으면 null
    evidence: str


class DueChange(BaseModel):
    task_id: Id
    new_due_raw: str
    new_due_at: KstDateTime | None = None
    evidence: str


class Resolved(BaseModel):
    task_id: Id
    reason: Literal["done_by_other", "cancelled", "not_needed"]
    evidence: str


class SignalsResponse(BaseModel):
    mail_id: Id | None = None
    commitments: list[Commitment] = []
    due_changes: list[DueChange] = []
    resolved: list[Resolved] = []
    asks_me_question: bool = False  # 받은 메일이 나에게 답을 바라는 질문을 했다(끊긴 대화 판정용). 보낸 메일은 늘 false
    source: Literal["exaone", "none"]  # none: 모델을 부르지 않았거나 판단하지 못함(fallback에 이유)
    model: str | None = None
    prompt_version: str
    elapsed_ms: int = 0  # 이 요청 처리 시간(모델 호출 포함)
    dropped: int = 0  # 모델이 냈지만 형식이 맞지 않아 버린 신호 수(근거 없음 · 없는 task_id · 방향과 다른 who 등)
    # null: 정상. empty_body: 본문이 비었거나 서명 · 인용뿐이라 이 메일이 쓴 문장이 없음(다시 부르지 않는다). quota: 하루 한도 소진(시도로 세지 않고 한도가 풀린 뒤 다시).
    # model_failed: 호출 실패 · JSON 아님(시도로 세며 다시). bad_output: JSON이지만 틀이 맞지 않음(시도로 세며 다시)
    fallback: Literal["empty_body", "quota", "model_failed", "bad_output"] | None = None
    detail: str | None = None  # fallback 이유 설명. 본문 · 키를 넣지 않는다
