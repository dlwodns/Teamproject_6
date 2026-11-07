"""분류 파이프라인 (AI-19 · AI-D15): 조건 → 모델 판단 → 조건으로 다듬기.

원칙(11/7 사용자 결정): 판단은 모델이 하고, 규칙은 조건만 본다. 둘이 겹치지 않는다.
- 조건(pipeline/conditions.py): 수신 방식 · 사내외 · 자동 발송 · 회신 제목 · 지목 글자 · 긴급 · 재요청 단어 · '필요 없다'고 밝힌 문장
- 모델(prompts/classify_v6): 할 일이 있나, 할 일마다 유형 · 문구 · 기한 표현 · 형식 · 보낼 곳, 메일 성격, 긴급 · 재요청 단어가 그런 뜻인가
- 코드: 기한 날짜 계산 · 지어낸 기한 걸러내기 · 근거 문장 · 우선순위 · 칸 · 5분류 묶음

모델 판단을 규칙이 덮어쓰지 않는다. 예외는 둘이다(둘 다 메일에 글자로 드러난 조건이다):
1. 참조로 받은 메일에는 '참조'를 붙인다. 할 일이 있으면 할 일 유형 뒤에 붙는다.
2. 본문이 조건 없이 '회신 · 참석 · 조치가 필요 없다'고 밝히면 그 종류의 모델 할 일은 확인 칸으로 옮긴다(버리지 않는다, D15).
모델 호출이 실패하면 할 일을 지어내지 않고 조건만으로 유형을 두고 확인 칸에 '분류 실패'를 띄운다(다시 시도 대상).
"""
import re

from app.core.config import Settings
from app.llm.client import LLMClient, LLMError
from app.pipeline import checks, conditions, evidence, priority
from app.pipeline.conditions import CONDITIONS_VERSION, Conditions
from app.pipeline.dates import ASAP, DueParse, parse_deadline, parse_due_plain
from app.prompts import classify_v6 as PROMPT
from app.schemas.classify import ClassifyRequest, ClassifyResponse, TaskOut

NO_TASK_TYPES = ("회신", "공유", "공지", "참조", "기타")
# D39 5분류 묶음. 조치요청은 요청, 공유는 기타(예전 '참조'로 적던 메일이라 묶음이 바뀌지 않는다)
CATEGORY = {"회신요청": "회신", "자료제출요청": "요청", "수정재전송요청": "요청", "일정참석": "요청", "조치요청": "요청",
            "검토승인요청": "검토", "공지": "공지", "공유": "기타", "참조": "기타", "회신": "기타", "기타": "기타"}
EMPTY = ("", "없음", "null", "None", "요청자")
MEETING_WHEN = re.compile(r"일시\s*[:：]\s*(.+)")


def _squash(text: str) -> str:
    return re.sub(r"[\s()]+", "", text)


def _context(raw: str, req: ClassifyRequest) -> str:
    """모델 기한 글자가 나온 원문 자리 + 앞 20글자 · 뒤 10글자('10/22(목)' → '10/22(목)까지 보내').
    띄어쓰기 · 괄호만 다른 '10/22 (목)'도 원문 자리를 찾는다(#21 리뷰). 못 찾으면 글자 그대로."""
    return _locate(raw, req)[0]


def _locate(raw: str, req: ClassifyRequest) -> tuple[str, str]:
    """(기한 글자 앞뒤 문맥, 그 앞 본문). 앞 본문은 '그 전에 · 마감 전까지'가 가리키는 일시를 찾는 데만 쓴다(날짜 계산)."""
    core = _squash(raw)
    if not core:
        return raw, ""
    pat = re.compile(r"[\s()]*".join(map(re.escape, core)))
    for text in (req.body, req.subject):
        if (m := pat.search(text)):
            start = max(0, m.start() - 20)
            return text[start: m.end() + 10], text[:start] if text is req.body else ""
    return raw, ""


# 기한 문구 속 날짜 조각: 숫자 · 상대 날짜 · 요일 · 때. 모델이 본문 글자를 그대로 옮기지 않고 뜻을 살려 바꿔 써도
# ('10/29(목) 마감됩니다 … 마감 전까지' → '10/29(목) 마감 전까지') 이 조각이 모두 본문에 있으면 지어낸 기한이 아니다
DATE_PIECE = re.compile(r"\d+|오늘|금일|내일|명일|익일|모레|글피|이번\s*주|금주|다음\s*주|차주|[월화수목금토일](?=요일|\))|오전|오후|아침|저녁|점심|퇴근|EOD", re.I)


def _grounded(raw: str, mail_text: str) -> bool:
    """기한 문구가 메일에 근거가 있나(지어낸 기한 걸러내기, AI-D11). 글자 그대로 있거나, 날짜 조각이 하나 이상이고 모두 메일에 있으면 근거가 있다.
    날짜 조각 없이 바꿔 쓴 문구('그 전에'가 본문에 없음)는 근거가 없다. ASAP는 메일에 서두르라는 말이 있으면 근거가 있다."""
    if _squash(raw) in mail_text:
        return True
    if ASAP.search(raw):  # '급히 · 급하게'처럼 서두르는 말도 ASAP다(11/7)
        return bool(ASAP.search(mail_text) or conditions.URGENT.search(mail_text))
    pieces = [_squash(x) for x in DATE_PIECE.findall(raw)]
    return bool(pieces) and all(x in mail_text for x in pieces)


def event_due(req: ClassifyRequest) -> DueParse | None:
    """회의 · 행사 시각. 본문 '일시:' 줄 → 제목 + 본문 순서로 찾는다(날짜 계산, 해석 아님)."""
    when = MEETING_WHEN.search(req.body)
    text = when.group(1) if when else f"{req.subject} {' '.join(conditions.strip_body(req.body))}"
    return parse_due_plain(text, req.received_at)


def flag(c_word: bool, out: dict, key: str) -> bool:
    """긴급 · 재요청: 단어가 있는지는 조건, 그 단어가 그런 뜻인지는 모델. 둘 다 맞을 때만 true.
    모델이 칸을 내지 않았으면(호출 실패 등) 단어 조건만 쓴다."""
    v = out.get(key)
    return c_word and v if isinstance(v, bool) else c_word


def due_of(raw: str, kind: str, req: ClassifyRequest, verbatim: bool) -> DueParse | None:
    """모델이 기한이라고 판단한 문구의 날짜 · 시각을 계산한다. 무엇이 기한인지는 모델이 정한다(11/7, AI-D15).
    - 글자 그대로 있으면 원문 자리의 앞뒤 문맥으로, 뜻을 살려 줄여 썼으면 그 문구 자체로 계산한다
    - 회의 참석은 회의 일시가 기한이다
    - 마감 표지('까지 · 전 · 중 · 내로')가 붙으면 그 날짜(시각을 모르는 행사 앞이면 시각을 비운다)
    - 표지가 없어도 모델이 기한으로 골랐으면 문구의 날짜를 그대로 쓴다('다음 주 초' 회의에 들어갈 자료)"""
    ctx, prior = _locate(raw, req) if verbatim else (raw, " ".join(conditions.strip_body(req.body)))
    if kind == "일정참석":
        return parse_due_plain(ctx, req.received_at)
    return parse_deadline(ctx, req.received_at, prior) or parse_due_plain(raw, req.received_at)


def read_model(out: dict, req: ClassifyRequest) -> tuple[str | None, list[TaskOut]]:
    """모델 출력 → (메일 성격, 할 일). 날짜 계산과 지어낸 기한 걸러내기만 코드가 한다."""
    mail_type = out.get("mail_type") if out.get("mail_type") in PROMPT.MAIL_TYPES else None
    mail_text = _squash(f"{req.subject} {req.body}")
    tasks = []
    for t in out.get("tasks") or []:
        if not isinstance(t, dict) or not str(t.get("action", "")).strip():
            continue
        kind = t.get("type") if t.get("type") in PROMPT.TASK_TYPES else "회신요청"
        raw = str(t.get("due_raw") or "").strip()
        raw = None if raw in EMPTY else raw
        if raw and not _grounded(raw, mail_text):  # 메일에 근거가 없는 기한은 모델이 지어낸 것이다
            raw = None
        due = None
        if raw:
            due = due_of(raw, kind, req, _squash(raw) in mail_text)
        fmt = str(t.get("format") or "").strip()
        to = str(t.get("to") or "").strip()
        # 날짜를 계산하지 못해도 근거가 있는 기한 문구는 남긴다('내일 고객 보고 전'처럼 시각을 모르는 기한, AI-D11)
        tasks.append(TaskOut(type=kind, text=str(t["action"]).strip()[:80], due_raw=due.raw if due else raw,
                             due_at=due.due_at if due else None, format=None if fmt in EMPTY else fmt,
                             deliver_to=None if to in EMPTY else to[:80]))
    return mail_type, tasks


def drop_said_not_needed(tasks: list[TaskOut], c: Conditions) -> tuple[list[TaskOut], list[TaskOut]]:
    """본문이 조건 없이 필요 없다고 밝힌 종류의 할 일을 옮긴다. '회신 필요 없음'은 확인(검토) 할 일을 없애지 않는다."""
    if not c.no_action:
        return tasks, []
    gone = set(PROMPT.TASK_TYPES) if "전부" in c.no_action else set(c.no_action)
    return [t for t in tasks if t.type not in gone], [t for t in tasks if t.type in gone]


def mail_types(tasks: list[TaskOut], mail_type: str | None, c: Conditions, failed: bool) -> list[str]:
    """메일의 유형 목록. 할 일이 있으면 할 일 유형이 앞(해야 하는 것을 먼저 본다, 11/7). 참조는 CC 조건으로만 붙는다."""
    if tasks:
        out: list[str] = []
        for t in tasks:
            if t.type not in out:
                out.append(t.type)
        if mail_type == "공지":
            out.append("공지")
        if c.recipient == "cc":
            out.append("참조")
        return out
    if c.recipient == "cc":
        return ["참조"]
    if failed:  # 모델 판단이 없다. 조건만으로 둔 임시 유형이고, 확인 칸 '분류 실패'로 다시 시도한다
        return ["기타" if c.auto_sent else "회신" if c.reply else "공지" if c.recipient == "list" else "공유"]
    if mail_type in NO_TASK_TYPES:
        return [mail_type]
    return ["공지" if c.recipient == "list" else "공유"]  # 모델이 '요청'이라 하고 할 일을 비웠다 → 확인 칸에서 사람이 본다


def _fill_event_due(tasks: list[TaskOut], req: ClassifyRequest) -> None:
    """회의 참석 할 일에 기한 문구가 없으면 회의 일시를 기한으로 둔다."""
    ev = None
    for t in tasks:
        if t.type == "일정참석" and t.due_at is None and not t.due_raw:
            ev = ev or event_due(req)
            if ev:
                t.due_raw, t.due_at = ev.raw, ev.due_at


def classify(req: ClassifyRequest, llm: LLMClient, settings: Settings) -> ClassifyResponse:
    c = conditions.read(req)
    mail_type, tasks, fallback, out = None, [], None, {}
    try:
        out = llm.chat_json(PROMPT.SYSTEM, PROMPT.render_user(req, c), PROMPT.SCHEMA)
        mail_type, tasks = read_model(out, req)
    except LLMError as e:
        fallback = str(e)
    urgent, follow_up = flag(c.urgent, out, "urgent"), flag(c.follow_up, out, "follow_up")
    tasks, moved = drop_said_not_needed(tasks, c)
    types = mail_types(tasks, mail_type, c, fallback is not None)
    _fill_event_due(tasks, req)
    evidence.attach(tasks, req)  # AI-15: 할 일마다 본문에 그대로 있는 근거 문장(UX-D16 형광펜)
    pts = priority.score(superior_or_favorite=req.sender.is_superior or req.sender.is_favorite,
                         dues=[t.due_at for t in tasks if t.due_at], received_at=req.received_at,
                         urgent=urgent, follow_up=follow_up, recipient=c.recipient)
    chk = checks.build(req, c, types, tasks, moved, mail_type, failed=fallback is not None)
    return ClassifyResponse(
        mail_id=req.mail_id, category=CATEGORY[tasks[0].type if tasks else types[0]], action_types=types, tasks=tasks,
        checks=chk, lane="할 일" if tasks else "확인" if chk else "참고",
        # 지목 = 나에게 맡긴 일이 있다(11/7). 단체 · 참조 메일은 내 이름 · 우리 팀 · 내 역할(팀장 목록 · 1팀 목록 포함)을 불러 맡길 때만
        # 할 일이 되므로(프롬프트 · 라벨 가이드) 할 일이 있으면 지목이다
        mentioned_me=bool(tasks),
        urgent=urgent, is_follow_up=follow_up, priority=priority.level(pts),
        source="rule" if fallback else "exaone", confidence=None, model=None if fallback else llm.model,
        prompt_version=None if fallback else PROMPT.PROMPT_VERSION, rules_version=CONDITIONS_VERSION, fallback=fallback,
    )
