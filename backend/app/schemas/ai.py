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
    type: str | None = None  # AI-19(AI-D15) 업무 유형. 저장 칸은 #30 · AI-19 계약 정리 때
    text: str
    format: str | None = None
    due_raw: str | None = None  # 'ASAP' · '내일 미팅 전에'처럼 due_at 없이 문구만 올 수 있다(AI-D11)
    due_at: KstNaive = None
    due_time_stated: bool = False  # AI-20: 시각이 메일에 적혀 있었나(캘린더 자동 등록 조건)
    end_at: KstNaive = None  # AI-20: 일정참석 끝 시각
    evidence: str | None = None
    deliver_to: str | None = None  # DE-D21 보낼 곳


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
    summary: "MailSummary | None" = None  # AI-32: 분류 호출에서 같이 만든 메일 요약(classify_v8.3~)


class MemoryFact(_AI):
    kind: Literal["works_on", "org"]
    value: str
    evidence: str


class MemoryExtractResult(_AI):
    """ai `/memory/extract` 응답(PL-16, BE-D21). ai/app/schemas/memory.py가 기준이다."""
    mail_id: int
    facts: list[MemoryFact] = []
    source: Literal["exaone", "none"]
    model: str | None = None
    prompt_version: str
    fallback: str | None = None


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
    status: Literal["done", "snoozed"] | None = None  # 11-18 '끝낸 거' · '미룬 거'(T02). 없으면 미처리


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


class TodayCounts(_AI):
    """오늘 요약의 숫자 줄(mode=today, AI-13 v3 · AI-D21). ai가 코드로 센 값이라 화면은 문장 속 숫자 대신 이 값을 쓴다.
    단 '미처리'는 대시보드(UX-D2) 값을 쓴다 — pending은 뜻이 달라 화면에 보이지 않는다(#61 리뷰)."""
    # 지금 남은 미처리 업무 수: 상태가 미처리인 것만(나중에 · 제외 빼고), 받은 날과 관계없이 전부.
    # 대시보드 1열 '미처리'(UX-D2: 미처리 + 나중에, 받은 날 기준)와 다른 값이라 화면에 '미처리'로 보이지 않는다(#61 리뷰).
    # 브리핑 검증(맞는 건수 집합)에 쓰고, 화면의 미처리 숫자는 대시보드 값 하나만 쓴다
    pending: int
    due_today: int  # 오늘까지 기한(기한 지남 포함)
    overdue: int
    awaiting_reply: int


class SummarizeResult(_AI):
    text: str
    source: Literal["code", "exaone"]
    prompt_version: str | None = None
    fallback: str | None = None
    # mode=mail일 때만 채운다. None이면 요약 없음(외국어 메일 + 모델 실패 등) → 화면은 '요약 실패 · 원문 보기', 사유는 fallback
    mail_summary: MailSummary | None = None
    # mode=today일 때만 채운다(AI-13 v3). 요청 항목에는 is_superior(연락처 상급자) · is_event(업무 유형 일정참석)를 담아 보낸다 —
    # 빠지면 ai는 상급자 아님 · '참석' 낱말로 일정 판정으로 본다
    counts: TodayCounts | None = None
    section_counts: dict[str, int] | None = None  # mode=evening · weekly만(AI-29): {묶음 id: 건수}


class DraftResult(_AI):
    subject: str
    body: str  # 표시용. 보내지 않는다(발송은 POST /mails/{id}/reply, D48)
    source: Literal["template", "exaone"]
    prompt_version: str | None = None
    fallback: str | None = None


# ---------- 답장 다듬기 (POST /polish) ----------
# 화면 버튼과 1:1. ai/app/prompts/polish_v1.py STYLES · ai/app/schemas/assist.py PolishStyle과 함께 고친다
PolishStyle = Literal["polite", "concise", "proofread", "clear"]


class PolishResult(_AI):
    text: str  # 다듬은 글. 모델 실패 · 검사에 걸리면 보낸 글 그대로
    style: PolishStyle
    changed: bool
    source: Literal["exaone", "none"]
    prompt_version: str | None = None
    fallback: str | None = None


class TranslateResult(_AI):
    """메일 번역(AI-32, ai TranslateResponse)."""
    text: str  # 한국어 번역문. 번역하지 않았으면 ''
    lang: str
    source: Literal["exaone", "none"]
    prompt_version: str | None = None
    fallback: str | None = None
