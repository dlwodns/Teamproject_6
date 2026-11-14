"""분류 파이프라인 (AI-19 · AI-D15 · AI-23 · AI-D19): 사실 읽기 → 모델 판단 → 구조로 담기.

원칙(11/13 사용자 결정, AI-D19): 판단은 모두 모델이 한다. 규칙은 구조 · 틀의 역할만 하고, 모델 답을 바꾸지 않는다. 예외 없음.
- 사실(pipeline/conditions.py): 수신 방식 · 배포 목록 종류 · 사내외 · 자동 발송. 모델 입력에 사실로만 적는다
- 모델(prompts/classify_v8): 할 일이 있나, 할 일마다 유형 · 문구 · 기한 표현 · 형식 · 보낼 곳, 메일 성격(공지 · 공유 · 참조 포함), 긴급 · 재요청
- 코드(구조): 기한 날짜 계산 · 메일에 없는 기한 걸러내기 · 근거 문장 · 우선순위 공식 · 칸 배치 · 5분류 묶음 ·
  모델이 할 일을 비운 메일에 '요청 문장 있음' 확인 칸 덧붙이기(누락 안전망, 모델 답은 그대로)
모델 호출이 실패하면 규칙으로 결과를 만들지 않고 LLMError를 그대로 올린다. API가 503으로 알리고, backend가 그 메일을 다시 부른다.
"""
import re

from app.core.config import Settings
from app.llm.client import LLMClient, LLMError
from app.pipeline import checks, conditions, evidence, priority
from app.pipeline.conditions import CONDITIONS_VERSION, Conditions
from app.pipeline.dates import ASAP, DueParse, parse_deadline, parse_due_plain, parse_event_at, parse_event_end
from app.prompts import classify_v8 as PROMPT
from app.schemas.classify import ClassifyRequest, ClassifyResponse, TaskOut

NO_TASK_TYPES = ("회신", "공유", "공지", "참조", "기타")
TAGGED_WITH_TASKS = ("공지", "참조")  # 할 일이 있어도 메일 성격으로 함께 보여 주는 유형(모델이 낸 값 그대로)


class ModelOutputError(LLMError):
    """모델 답이 서로 맞지 않는다(예: 요청 메일인데 할 일이 없음). 코드가 메웠던 자리 — 지금은 다시 부를 대상이다."""
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
    """회의 · 행사 시각. 본문 '일시:' 줄 → 제목 + 본문 순서로 찾는다(날짜 계산, 해석 아님).
    AI-20: 마감 표지가 붙은 시각('참석 여부를 18:00까지')은 회의 시각으로 쓰지 않는다(parse_event_at)."""
    when = MEETING_WHEN.search(req.body)
    text = when.group(1) if when else f"{req.subject} {' '.join(conditions.strip_body(req.body))}"
    return parse_event_at(text, req.received_at)


def flag(out: dict, key: str) -> bool:
    """긴급 · 재요청은 모델이 정한다(AI-D19). v7까지는 정해진 단어가 없으면 모델이 true라 해도 false였다."""
    return out.get(key) is True


def due_of(raw: str, kind: str, req: ClassifyRequest, verbatim: bool) -> DueParse | None:
    """모델이 기한이라고 판단한 문구의 날짜 · 시각을 계산한다. 무엇이 기한인지는 모델이 정한다(11/7, AI-D15).
    - 글자 그대로 있으면 원문 자리의 앞뒤 문맥으로, 뜻을 살려 줄여 썼으면 그 문구 자체로 계산한다
    - 회의 참석은 회의 일시가 기한이다
    - 마감 표지('까지 · 전 · 중 · 내로')가 붙으면 그 날짜(시각을 모르는 행사 앞이면 시각을 비운다)
    - 표지가 없어도 모델이 기한으로 골랐으면 문구의 날짜를 그대로 쓴다('다음 주 초' 회의에 들어갈 자료)"""
    ctx, prior = _locate(raw, req) if verbatim else (raw, " ".join(conditions.strip_body(req.body)))
    if kind == "일정참석":  # AI-20: 마감 표지가 붙은 시각은 회의 시각이 아니다(parse_event_at)
        return parse_event_at(ctx, req.received_at)
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
        # 기한 문구는 모델이 쓴 문구(본문에 근거가 있는 것만 남음)를 그대로 보여 준다. 날짜 계산용 문맥 조각(due.raw)은
        # 앞뒤 글자를 잘라 '오전 9시 7층 대회'처럼 깨져 보였다(11/11)
        tasks.append(TaskOut(type=kind, text=str(t["action"]).strip()[:80], due_raw=raw,
                             due_at=due.due_at if due else None, due_time_stated=bool(due and due.due_at and due.time_stated),
                             format=None if fmt in EMPTY else fmt,
                             deliver_to=None if to in EMPTY else to[:80]))
    return mail_type, tasks


def mail_types(tasks: list[TaskOut], mail_type: str | None) -> list[str]:
    """메일의 유형 목록. 모델이 낸 값을 순서만 정해 담는다(바꾸지 않는다, AI-D19).
    할 일이 있으면 할 일 유형이 앞(해야 하는 것을 먼저 본다, 11/7)이고, 모델이 공지 · 참조라고 했으면 뒤에 붙인다."""
    if tasks:
        out: list[str] = []
        for t in tasks:
            if t.type not in out:
                out.append(t.type)
        if mail_type in TAGGED_WITH_TASKS:
            out.append(mail_type)
        return out
    if mail_type in NO_TASK_TYPES:
        return [mail_type]
    raise ModelOutputError(f"모델 답이 맞지 않음: 메일 성격 {mail_type or '없음'}인데 할 일이 없음")


def _fill_event_due(tasks: list[TaskOut], req: ClassifyRequest) -> None:
    """회의 참석 할 일에 기한 문구가 없으면 회의 일시를 기한으로 둔다."""
    ev = None
    for t in tasks:
        if t.type == "일정참석" and t.due_at is None and not t.due_raw:
            ev = ev or event_due(req)
            if ev:
                t.due_raw, t.due_at, t.due_time_stated = ev.raw, ev.due_at, bool(ev.due_at and ev.time_stated)


def _event_text(t: TaskOut, req: ClassifyRequest) -> str:
    """일정 시각이 나온 글자 주변: 본문 '일시:' 줄 + 기한 문구 자리 앞 20글자 · 뒤 40글자('14:00~15:30').
    끝 시각은 시작 시각과 같은 시각으로 시작하는 범위만 쓰므로(parse_event_end) 두 곳을 함께 봐도 다른 일정의 범위를 쓰지 않는다."""
    parts = []
    if (when := MEETING_WHEN.search(req.body)):
        parts.append(when.group(1))
    core = _squash(t.due_raw or "")
    if core:
        pat = re.compile(r"[\s()]*".join(map(re.escape, core)))
        for text in (req.body, req.subject):
            if (m := pat.search(text)):
                parts.append(text[max(0, m.start() - 20): m.end() + 40])
                break
    return " / ".join(parts) or (t.due_raw or "")


def _fill_event_end(tasks: list[TaskOut], req: ClassifyRequest) -> None:
    """회의 참석 할 일의 끝 시각(AI-20). 시작 시각이 메일에 적혀 있고 같은 시각으로 시작하는 범위가 있을 때만 채운다."""
    for t in tasks:
        if t.type == "일정참석" and t.due_at and t.due_time_stated:
            t.end_at = parse_event_end(_event_text(t, req), t.due_at)


def classify(req: ClassifyRequest, llm: LLMClient, settings: Settings) -> ClassifyResponse:
    """모델 호출이 실패하거나 모델 답이 맞지 않으면 LLMError를 올린다(규칙으로 메우지 않는다, AI-D19)."""
    c = conditions.read(req)
    out = llm.chat_json(PROMPT.SYSTEM, PROMPT.render_user(req, c), PROMPT.SCHEMA)
    mail_type, tasks = read_model(out, req)
    urgent, follow_up = flag(out, "urgent"), flag(out, "follow_up")
    types = mail_types(tasks, mail_type)
    _fill_event_due(tasks, req)
    _fill_event_end(tasks, req)
    evidence.attach(tasks, req)  # AI-15: 할 일마다 본문에 그대로 있는 근거 문장(UX-D16 형광펜)
    pts = priority.score(superior_or_favorite=req.sender.is_superior or req.sender.is_favorite,
                         dues=[t.due_at for t in tasks if t.due_at], received_at=req.received_at,
                         urgent=urgent, follow_up=follow_up, recipient=c.recipient)
    chk = checks.build(req, c, types, tasks)
    return ClassifyResponse(
        mail_id=req.mail_id, category=CATEGORY[tasks[0].type if tasks else types[0]], action_types=types, tasks=tasks,
        checks=chk, lane="할 일" if tasks else "확인" if chk else "참고",
        # 지목 = 나에게 맡긴 일이 있다(11/7). 단체 · 참조 메일은 내 이름 · 우리 팀 · 내 역할(팀장 목록 · 1팀 목록 포함)을 불러 맡길 때만
        # 할 일이 되므로(프롬프트 · 라벨 가이드) 할 일이 있으면 지목이다
        mentioned_me=bool(tasks),
        urgent=urgent, is_follow_up=follow_up, priority=priority.level(pts),
        source="exaone", confidence=None, model=llm.model,
        prompt_version=PROMPT.PROMPT_VERSION, rules_version=CONDITIONS_VERSION, fallback=None,
    )
