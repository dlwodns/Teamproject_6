"""ai 서비스 응답을 backend가 쓰는 형식으로 받는다 (구조도 v3.1 8절, D47, BE-9).

ai 쪽 정의는 `ai/app/schemas/{classify,agent,assist}.py`가 기준이다. 바꿀 때는 양쪽을 함께 고친다(AI-9 · BE-9).
- ID: ai는 문자열로 돌려준다 → 여기서 정수로 바꾼다(D47 결정 2).
- 시각: ai 응답은 시간대 없는 KST다. 혹시 시간대가 붙어 와도 KST로 바꿔 뗀다(D47 결정 1, DB 저장 형식과 같다).
- ai가 필드를 더해도 깨지지 않게 모르는 필드는 버린다.
"""
from datetime import date, datetime
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from pydantic import AfterValidator, BaseModel, ConfigDict, field_validator

KST = ZoneInfo("Asia/Seoul")


def _kst_naive(v: datetime | None) -> datetime | None:
    return v.astimezone(KST).replace(tzinfo=None) if v is not None and v.tzinfo else v


KstNaive = Annotated[datetime | None, AfterValidator(_kst_naive)]


class _AI(BaseModel):
    model_config = ConfigDict(extra="ignore")


class AITask(_AI):
    text: str
    format: str | None = None
    due_raw: str | None = None  # 'ASAP' · '내일 미팅 전에'처럼 due_at 없이 문구만 올 수 있다(AI-D11)
    due_at: KstNaive = None
    evidence: str | None = None


class AICheck(_AI):
    text: str
    reason: str
    evidence: str | None = None
    source: str = "rule"


class ClassifyResult(_AI):
    mail_id: int
    category: Literal["회신", "요청", "검토", "공지", "기타"]
    action_types: list[str]
    tasks: list[AITask]
    checks: list[AICheck] = []
    kind: str | None = None
    kind_name: str | None = None
    kind_sure: bool = False
    lane: Literal["할 일", "확인", "참고"] = "참고"
    mentioned_me: bool  # 메일 단위 → 저장할 때 업무마다 복사(D47 · 구조도 8절)
    urgent: bool
    is_follow_up: bool
    priority: Literal["P1", "P2", "P3"]
    source: Literal["rule", "exaone"]
    confidence: float | None = None  # AI-19(AI-D15)부터 쓰지 않아 None이 온다. 예전 응답은 숫자
    model: str | None = None
    prompt_version: str | None = None
    rules_version: str
    fallback: str | None = None  # 엑사원 실패로 규칙 결과만 낸 이유


class DateRange(_AI):
    start: date
    end: date


class PlanTarget(_AI):
    sender: str | None = None
    category: str | None = None
    date_range: DateRange | None = None
    keyword: str | None = None
    mail_ids: list[int] = []
    awaiting_reply: bool = False


class PlanResult(_AI):
    action: str | None  # 행동 ID(T01~T14). None이면 reason을 본다
    action_name: str | None = None
    target: PlanTarget = PlanTarget()
    params: dict[str, Any] = {}  # 키는 행동별 고정(D47 결정 3). 못 읽은 값은 키를 두고 null
    source: Literal["rule", "model"]
    reason: Literal["unsupported", "ambiguous"] | None = None
    candidates: list[str] = []
    prompt_version: str | None = None
    rules_version: str
    fallback: str | None = None

    @field_validator("params")
    @classmethod
    def _until(cls, v: dict[str, Any]) -> dict[str, Any]:
        # T05 params.until은 시간대 없는 KST 시각 문자열 → datetime(저장 형식). null은 그대로 둔다
        if isinstance(v.get("until"), str):
            v = {**v, "until": _kst_naive(datetime.fromisoformat(v["until"]))}
        return v


class MailSummary(_AI):
    """메일 하나의 요약(AI-13 v2 · UX-D15). 외국어 메일 핵심 추출용."""
    # 원문 언어, ai가 코드로 판별: ko · en · ja · zh · other(영어가 아닌 라틴 문자 언어, 화면은 '기타 외국어', AI-13 #34 리뷰).
    # ai에 언어가 더 생겨도 backend가 응답을 버리지 않도록 값 목록으로 묶지 않는다
    lang: str
    gist: str  # 한국어 요지 1~2문장
    asks: list[str] = []  # 나에게 요청한 것(한국어), 없으면 []
    due_text: str | None = None  # 본문에 적힌 기한 원문 그대로


class SummarizeResult(_AI):
    text: str
    source: Literal["code", "exaone"]
    prompt_version: str | None = None
    fallback: str | None = None
    # mode=mail일 때만 채운다. None이면 요약 없음(외국어 메일 + 모델 실패 등) → 화면은 '요약 실패 · 원문 보기', 사유는 fallback
    mail_summary: MailSummary | None = None


class DraftResult(_AI):
    subject: str
    body: str  # 표시용. 보내지 않는다(발송은 POST /mails/{id}/reply, D48)
    source: Literal["template", "exaone"]
    prompt_version: str | None = None
    fallback: str | None = None
