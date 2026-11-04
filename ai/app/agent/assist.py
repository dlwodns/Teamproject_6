"""오늘 요약 · 메일 요약 · 회신 초안 (AI-13, D42). 엑사원이 없거나 실패하면 코드 요약 · 템플릿 초안으로 대신한다."""
import re
from datetime import datetime

from app.llm.client import LLMClient, LLMError
from app.prompts import assist_v1
from app.schemas.assist import DraftRequest, DraftResponse, SummarizeRequest, SummarizeResponse, SummaryItem

WEEKDAYS = "월화수목금토일"


def _when(due: datetime | None, now: datetime) -> str:
    if due is None:
        return "기한 없음"
    days = (due.date() - now.date()).days
    hm = due.strftime("%H:%M")
    if due < now:
        return f"기한 지남({due:%m/%d} {hm})"
    return {0: f"오늘 {hm}", 1: f"내일 {hm}"}.get(days, f"{due:%m/%d}({WEEKDAYS[due.weekday()]}) {hm}")


def _rank(it: SummaryItem, now: datetime):
    overdue = it.due_at is not None and it.due_at < now
    return (not overdue, it.priority, it.due_at or datetime.max)


def code_summary(req: SummarizeRequest) -> str:
    """사실만 담은 브리핑. 모델 입력으로도 쓴다."""
    now, items = req.now, [i for i in req.items if i.status == "pending"]
    today = [i for i in items if i.due_at and i.due_at.date() <= now.date()]
    overdue = [i for i in items if i.due_at and i.due_at < now]
    lines = [f"미처리 {len(items)}건 · 오늘까지 {len(today)}건 · 기한 지남 {len(overdue)}건 · 응답 대기 {req.awaiting_reply_count}건"]
    for it in sorted(items, key=lambda i: _rank(i, now))[:5]:
        who = f"{it.sender} · " if it.sender else ""
        lines.append(f"- [{it.priority}] {it.text} ({who}{_when(it.due_at, now)})")
    if len(items) > 5:
        lines.append(f"- 외 {len(items) - 5}건")
    if req.awaiting_reply_count:
        lines.append(f"- 3일 이상 답장이 없는 보낸 메일 {req.awaiting_reply_count}건이 있습니다.")
    return "\n".join(lines)


def summarize(req: SummarizeRequest, llm: LLMClient) -> SummarizeResponse:
    if req.mode == "today":
        facts = code_summary(req)
        if not req.use_model or not req.items:
            return SummarizeResponse(text=facts, source="code")
        try:
            text = llm.chat_text(assist_v1.SUMMARY_TODAY, f"현재 시각: {req.now:%Y-%m-%d %H:%M}\n오늘의 업무 사실:\n{facts}")
            return SummarizeResponse(text=text, source="exaone", prompt_version=assist_v1.PROMPT_VERSION)
        except LLMError as e:
            return SummarizeResponse(text=facts, source="code", fallback=str(e))

    mail = req.mail
    if mail is None:
        return SummarizeResponse(text="", source="code", fallback="mail 없음")
    try:
        if not req.use_model:
            raise LLMError("모델 미사용")
        text = llm.chat_text(assist_v1.SUMMARY_MAIL, f"제목: {mail.subject}\n본문:\n{mail.body}")
        return SummarizeResponse(text=text, source="exaone", prompt_version=assist_v1.PROMPT_VERSION)
    except LLMError as e:
        # 코드 요약: 서명 앞 본문의 앞 두 문장
        core = re.split(r"\n\*{5,}|\n-{5,}", mail.body)[0]
        sents = [s.strip() for s in re.split(r"(?<=[.?!])\s+|\n+", core) if len(s.strip()) > 5]
        return SummarizeResponse(text=" ".join(sents[:2])[:200] or mail.subject, source="code", fallback=str(e))


def template_draft(req: DraftRequest) -> DraftResponse:
    sign = f"\n\n{req.signer} 드림" if req.signer else ""
    if req.kind == "reply" and req.mail:
        subject = req.mail.subject if re.match(r"^\s*RE:", req.mail.subject, re.I) else f"RE: {req.mail.subject}"
        to = f"{req.mail.sender}님, " if req.mail.sender else ""
        body = f"{to}메일 잘 받았습니다.\n요청하신 내용 확인 후 [확인 필요: 회신 일정]까지 회신드리겠습니다.\n감사합니다.{sign}"
    else:
        to = f"{req.recipient}님, " if req.recipient else ""
        topic = req.topic or "[확인 필요: 주제]"
        subject = f"[문의] {topic}"
        body = f"{to}안녕하세요.\n{topic} 관련하여 연락드립니다.\n[확인 필요: 내용]\n감사합니다.{sign}"
    return DraftResponse(subject=subject, body=body, source="template")


def draft(req: DraftRequest, llm: LLMClient) -> DraftResponse:
    if req.kind == "reply" and req.mail:
        user = f"종류: 회신\ntone: {req.tone}\n원 메일 제목: {req.mail.subject}\n원 메일 본문:\n{req.mail.body}"
    else:
        user = f"종류: 새 메일\ntone: {req.tone}\n받는 사람: {req.recipient or '[확인 필요]'}\n주제: {req.topic or '[확인 필요]'}"
    if req.signer:
        user += f"\n보내는 사람: {req.signer}"
    try:
        out = llm.chat_json(assist_v1.DRAFT, user, assist_v1.DRAFT_SCHEMA)
        subject, body = str(out.get("subject", "")).strip(), str(out.get("body", "")).strip()
        if not body:
            raise LLMError("빈 초안")
        return DraftResponse(subject=subject or template_draft(req).subject, body=body, source="exaone",
                             prompt_version=assist_v1.PROMPT_VERSION)
    except LLMError as e:
        return template_draft(req).model_copy(update={"fallback": str(e)})
