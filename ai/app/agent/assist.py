"""오늘 요약 · 메일 요약 · 회신 초안 (AI-13, D42). 엑사원이 없거나 실패하면 코드 요약 · 템플릿 초안으로 대신한다."""
import re
from datetime import datetime

from app.llm.client import LLMClient, LLMError
from app.pipeline.dates import parse_deadline
from app.prompts import assist_v2 as prompts
from app.schemas.assist import (DraftRequest, DraftResponse, MailInput, MailSummary, SummarizeRequest,
                                SummarizeResponse, SummaryItem)

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
            text = llm.chat_text(prompts.SUMMARY_TODAY, f"현재 시각: {req.now:%Y-%m-%d %H:%M}\n오늘의 업무 사실:\n{facts}")
            return SummarizeResponse(text=text, source="exaone", prompt_version=prompts.PROMPT_VERSION)
        except LLMError as e:
            return SummarizeResponse(text=facts, source="code", fallback=str(e))

    return summarize_mail(req, llm)


_HANGUL = re.compile(r"[\uac00-\ud7a3\u1100-\u11ff\u3130-\u318f]")
_KANA = re.compile(r"[\u3040-\u30ff]")
_HAN = re.compile(r"[\u4e00-\u9fff]")
_LATIN = re.compile(r"[A-Za-z\u00c0-\u024f]")


def detect_lang(text: str) -> str:
    """원문 언어(ISO 639-1)를 글자 비율로 고른다. 모델 전에 코드로 정한다.
    - 한글이 글자의 20% 이상이면 'ko'(국문 메일 속 영문 용어 · 서명은 흔하다)
    - 가나가 10% 이상이면 'ja'(일본어는 한자와 섞인다), 한자가 30% 이상이면 'zh'
    - 나머지 라틴 문자는 'en'(독일어 · 프랑스어 등은 구분하지 않는다)
    - 글자가 없으면 'ko'(옮길 내용이 없다)"""
    counts = {k: len(p.findall(text)) for k, p in (("ko", _HANGUL), ("ja", _KANA), ("zh", _HAN), ("en", _LATIN))}
    total = sum(counts.values())
    if total == 0 or counts["ko"] / total >= 0.2:
        return "ko"
    if counts["ja"] / total >= 0.1:
        return "ja"
    if counts["zh"] / total >= 0.3:
        return "zh"
    return "en" if counts["en"] else "ko"


def _core(body: str) -> str:
    """서명 · 구분선 앞 본문."""
    return re.split(r"\n\*{5,}|\n-{5,}", body)[0]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.?!])\s+|\n+", text) if len(s.strip()) > 5]


def _model_mail_summary(mail: MailInput, lang: str, llm: LLMClient) -> MailSummary:
    out = llm.chat_json(prompts.SUMMARY_MAIL, f"원문 언어: {lang}\n제목: {mail.subject}\n본문:\n{mail.body}",
                        prompts.SUMMARY_MAIL_SCHEMA)
    if not isinstance(out, dict):
        raise LLMError("요약 형식 오류: 객체가 아님")
    gist, asks, due = out.get("gist"), out.get("asks", []), out.get("due_text")
    if not isinstance(gist, str) or not gist.strip():
        raise LLMError("요약 형식 오류: gist 없음")
    if not _HANGUL.search(gist):
        raise LLMError("요약 형식 오류: gist가 한국어가 아님")  # 원문을 그대로 돌려준 경우
    if not isinstance(asks, list) or not all(isinstance(a, str) for a in asks):
        raise LLMError("요약 형식 오류: asks는 문자열 배열")
    if due is not None and not isinstance(due, str):
        raise LLMError("요약 형식 오류: due_text는 문자열 또는 null")
    return MailSummary(lang=lang, gist=gist.strip(), asks=[a.strip() for a in asks if a.strip()][:5],
                       due_text=(due or "").strip() or None)


def _code_mail_summary(mail: MailInput, now: datetime) -> MailSummary:
    """한국어 메일만: 서명 앞 본문의 앞 두 문장 + 본문에서 찾은 첫 기한 표현."""
    sents = _sentences(_core(mail.body))
    gist = " ".join(sents[:2])[:200] or mail.subject or "(내용 없음)"
    due = next((d.raw for s in sents if (d := parse_deadline(s, now)) is not None), None)
    return MailSummary(lang="ko", gist=gist, asks=[], due_text=due)


def summarize_mail(req: SummarizeRequest, llm: LLMClient) -> SummarizeResponse:
    """메일 요약(mode=mail). 언어는 코드가 먼저 정한다.
    모델이 없거나 실패하면 한국어 메일만 코드 요약을 낸다. 외국어 메일은 원문을 요약처럼 보이지 않도록
    text='' · mail_summary=None으로 돌려주고 fallback에 사유를 적는다(화면은 '요약 못 함 · 원문 보기')."""
    mail = req.mail
    if mail is None:
        return SummarizeResponse(text="", source="code", fallback="mail 없음")
    lang = detect_lang(f"{mail.subject}\n{mail.body}")
    try:
        if not req.use_model:
            raise LLMError("모델 미사용")
        ms = _model_mail_summary(mail, lang, llm)
        return SummarizeResponse(text=ms.gist, source="exaone", prompt_version=prompts.PROMPT_VERSION, mail_summary=ms)
    except LLMError as e:
        if lang != "ko":
            return SummarizeResponse(text="", source="code", fallback=f"외국어 메일({lang}) · 모델 없음: {e}")
        ms = _code_mail_summary(mail, req.now)
        return SummarizeResponse(text=ms.gist, source="code", fallback=str(e), mail_summary=ms)


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
        out = llm.chat_json(prompts.DRAFT, user, prompts.DRAFT_SCHEMA)
        subject, body = str(out.get("subject", "")).strip(), str(out.get("body", "")).strip()
        if not body:
            raise LLMError("빈 초안")
        return DraftResponse(subject=subject or template_draft(req).subject, body=body, source="exaone",
                             prompt_version=prompts.PROMPT_VERSION)
    except LLMError as e:
        return template_draft(req).model_copy(update={"fallback": str(e)})
