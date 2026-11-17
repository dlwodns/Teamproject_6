"""오늘 요약 · 메일 요약 · 회신 초안 (AI-13, D42). 엑사원이 없거나 실패하면 코드 요약 · 템플릿 초안으로 대신한다."""
import re
from dataclasses import dataclass, field
from datetime import datetime

from app.llm.client import LLMClient, LLMError
from app.pipeline.dates import parse_deadline
from app.prompts import assist_v4 as prompts
from app.schemas.assist import (BriefingItemIn, DraftRequest, DraftResponse, MailInput, MailSummary, SummarizeRequest,
                                SummarizeResponse, SummaryItem, TodayCounts)

WEEKDAYS = "월화수목금토일"
UNKNOWN_SENDER = "보낸 사람 모름"
# 일정(시각이 정해진 업무) 낱말. '회의 안건 회신' · '참석자 명단 회신'은 일정이 아니다 → '참석'만 보고 '참석자'는 뺀다
_EVENT = re.compile(r"참석(?!자)")
# 직책 낱말. 모델 문장에 '이름 + 직책'이 나오면 입력에 있던 사람인지 확인한다(지어낸 사람 막기)
_POSITIONS = ("사업단장", "본부장", "팀장", "실장", "부장", "차장", "과장", "대리", "사원", "주임", "선임", "책임", "수석",
              "담당", "이사", "상무", "전무", "매니저", "프로")
# 직책 뒤에 한글이 이어지면(프로젝트 · 이사회) 직책이 아니다. 조사 · 님은 허용(AI-29 리뷰)
_PERSON = re.compile(r"([가-힣]{2,4})\s?(" + "|".join(_POSITIONS) + r")(?=[님의께은는이가과와에도]|[^가-힣]|$)")
# 권하거나 지시하는 말. 오늘 요약은 무엇이 있는지만 알린다(AI-D21) — 이런 말이 나오면 모델 문장을 쓰지 않는다
_ADVICE = re.compile(r"세요|십시오|바랍니다|부탁드립니다|필요합니다|해야\s?합니다|하셔야|좋겠습니다|권합니다|추천|먼저\s|우선\s"
                     r"|서두르|처리하시")
_QUOTED = re.compile(r"'[^']*'|‘[^’]*’|\"[^\"]*\"")  # 업무 이름 인용(메일 제목의 '~바랍니다')은 권유 검사에서 뺀다(AI-29)
MAX_BRIEFING_CHARS = 450


@dataclass
class TodayFacts:
    """오늘 요약의 사실(AI-D21). 건수 · 묶음은 여기서만 센다 — 모델에는 세지 말라고 하고 이 값을 넘긴다."""

    now: datetime
    counts: TodayCounts
    overdue_superior: list[SummaryItem]  # 기한 지남 · 상급자 (기한 순)
    overdue_other: list[tuple[str, int]]  # 기한 지남 · 그 밖: (보낸 사람, 건수) 많은 순
    today_events: list[SummaryItem]  # 오늘 · 아직 안 지난 일정 (시각 순)
    today_other: list[tuple[str, int]]  # 오늘 · 그 밖 마감: (보낸 사람, 건수)
    heavy: list[tuple[str, int]]  # 기한 지남 + 오늘 합계가 3건 이상인 사람
    listed: list[SummaryItem] = field(default_factory=list)  # 기한 지남 + 오늘 전체(같은 업무 찾기용, 기한 순)


def _who(it: SummaryItem) -> str:
    return it.sender or UNKNOWN_SENDER


def _is_event(it: SummaryItem) -> bool:
    return it.is_event if it.is_event is not None else bool(_EVENT.search(it.text))


def _by_sender(items: list[SummaryItem]) -> list[tuple[str, int]]:
    order: dict[str, int] = {}
    for it in items:
        order[_who(it)] = order.get(_who(it), 0) + 1
    return sorted(order.items(), key=lambda kv: (-kv[1], list(order).index(kv[0])))


def today_facts(req: SummarizeRequest) -> TodayFacts:
    now = req.now
    pending = [i for i in req.items if i.status == "pending"]  # 나중에(snoozed)는 빠진다
    dated = sorted((i for i in pending if i.due_at and i.due_at.date() <= now.date()), key=lambda i: i.due_at)
    overdue = [i for i in dated if i.due_at < now]
    today = [i for i in dated if i.due_at >= now]
    events = [i for i in today if _is_event(i)]
    totals = _by_sender(dated)
    return TodayFacts(
        now=now,
        counts=TodayCounts(pending=len(pending), due_today=len(dated), overdue=len(overdue),
                           awaiting_reply=req.awaiting_reply_count),
        overdue_superior=[i for i in overdue if i.is_superior],
        overdue_other=_by_sender([i for i in overdue if not i.is_superior]),
        today_events=events,
        today_other=_by_sender([i for i in today if not _is_event(i)]),
        heavy=[(w, n) for w, n in totals if n >= 3],
        listed=dated,
    )


def _counts_line(groups: list[tuple[str, int]]) -> str:
    return ", ".join(f"{w} {n}건" for w, n in groups)


def code_summary(req: SummarizeRequest) -> str:
    """코드가 쓰는 오늘 요약(AI-D21). 모델 문장과 같은 3문장 틀이고, 같은 업무로 보이는 쌍 찾기만 빠진다.
    모델이 없거나 실패하거나 검증에 걸리면 이 문장을 쓴다."""
    return code_briefing(today_facts(req))


def code_briefing(f: TodayFacts) -> str:
    out: list[str] = []
    n_other = sum(n for _, n in f.overdue_other)
    if f.overdue_superior:
        names = ", ".join(f"{_who(i)}의 '{i.text}'" for i in f.overdue_superior[:4])
        more = " 등" if len(f.overdue_superior) > 4 else ""
        tail = f"이고, 그 밖에 {n_other}건이 있습니다." if n_other else "입니다."
        out.append(f"기한이 지난 업무 가운데 상급자가 보낸 건은 {names}{more}{tail}")
    elif n_other:
        out.append(f"기한이 지난 업무가 {n_other}건 있습니다.")
    parts = [f"{i.due_at:%H:%M} {_who(i)} '{i.text}'" for i in f.today_events]
    n_today = sum(n for _, n in f.today_other)
    if parts and n_today:
        out.append(f"오늘은 {', '.join(parts)} 일정이 있고, 그 밖 마감이 {n_today}건 있습니다.")
    elif parts:
        out.append(f"오늘은 {', '.join(parts)} 일정이 있습니다.")
    elif n_today:
        out.append(f"오늘 마감인 업무가 {n_today}건 있습니다.")
    if f.heavy:
        out.append(f"{', '.join(f'{w}에게 {n}건' for w, n in f.heavy)}이 걸려 있습니다.")
    if not out:
        out.append("오늘까지 기한인 업무는 없습니다.")  # 응답 대기는 아래에서 그대로 붙인다(#61 리뷰: 빠지던 것)
    if f.counts.awaiting_reply:
        out.append(f"3일 이상 답장이 없는 보낸 메일이 {f.counts.awaiting_reply}건 있습니다.")
    return " ".join(out)


def model_input(f: TodayFacts) -> str:
    """모델에 넘기는 '이미 정리된 사실'. 칸 이름은 SUMMARY_TODAY(v3) 지시문과 맞춘다."""
    hm = lambda i: f"{i.due_at:%m/%d %H:%M}"  # noqa: E731
    lines = [f"현재 시각: {f.now:%Y-%m-%d %H:%M}"]
    lines.append("[기한 지남 · 상급자]")
    lines += [f"- {_who(i)}: {i.text} ({hm(i)})" for i in f.overdue_superior] or ["- 없음"]
    n_other = sum(n for _, n in f.overdue_other)
    lines.append(f"[기한 지남 · 그 밖] {n_other}건")  # 사람별 건수는 넘기지 않는다: 넘기면 모델이 그대로 늘어놓아 길어진다(11/13 실측)
    lines.append("[오늘 · 일정]")
    lines += [f"- {i.due_at:%H:%M} {_who(i)}: {i.text}" for i in f.today_events] or ["- 없음"]
    lines.append(f"[오늘 · 그 밖 마감] {sum(n for _, n in f.today_other)}건")
    lines.append("[3건 이상인 사람] " + (_counts_line(f.heavy) or "없음"))
    lines.append("[전체 업무 목록]")
    # 번호를 붙이지 않는다: 번호도 '입력에 있는 숫자'가 돼 지어낸 숫자 검사가 무뎌진다
    lines += [f"- {_who(i)} · {i.text} · {hm(i)}" for i in f.listed]
    if f.counts.awaiting_reply:
        lines.append(f"[참고] 3일 이상 답장이 없는 보낸 메일 {f.counts.awaiting_reply}건")
    return "\n".join(lines)


def check_briefing(text: str, f: TodayFacts, source: str) -> str | None:
    """모델 문장을 코드가 센 사실과 대조한다. 문제가 없으면 None, 있으면 사유(→ 코드 문장으로 바꾼다).
    숫자 · 사람이 틀린 브리핑은 '할 일 놓침 0'을 해치므로 의심되면 쓰지 않는다."""
    allowed_counts = {n for _, n in f.overdue_other + f.today_other + f.heavy}
    allowed_counts |= {sum(n for _, n in f.overdue_other), sum(n for _, n in f.today_other), len(f.overdue_superior),
                       len(f.today_events),
                       f.counts.awaiting_reply, f.counts.pending, f.counts.due_today, f.counts.overdue,
                       2}  # 2: '같은 업무 2건'처럼 쌍을 말할 때. 전체 건수는 반복하지 말라고 했지만 맞는 숫자라 막지 않는다
    return check_text(text, source, allowed_counts, {_who(i) for i in f.listed})


def check_text(text: str, source: str, allowed_counts: set[int], people: set[str]) -> str | None:
    """요약 · 회고 머리 문장 공통 검증(AI-D21 결정 4, AI-29): 길이 · 권유 · 입력에 없는 숫자 · 맞지 않는 건수 · 입력에 없는 사람."""
    if not text.strip():
        return "빈 문장"
    if len(text) > MAX_BRIEFING_CHARS:
        return f"너무 김({len(text)}자)"
    if m := _ADVICE.search(_QUOTED.sub("", text)):
        return f"권유 표현({m.group(0).strip()})"
    allowed_numbers = set(re.findall(r"\d+", source)) | {str(n) for n in allowed_counts}  # 뺀 건수는 입력에 글자로 없다
    if bad := sorted({n for n in re.findall(r"\d+", text) if n not in allowed_numbers}):
        return f"입력에 없는 숫자({', '.join(bad)})"
    if bad := sorted({int(n) for n in re.findall(r"(\d+)\s?건", text) if int(n) not in allowed_counts}):
        return f"맞지 않는 건수({', '.join(map(str, bad))})"
    known = {w.replace(" ", "") for w in people}
    if bad := sorted(set(re.findall(r"[월화수목금토일]요일", text)) - set(re.findall(r"[월화수목금토일]요일", source))):
        return f"입력에 없는 요일({', '.join(bad)})"
    for name, pos in _PERSON.findall(text):
        if not any((name + pos) in k or k.startswith(name) for k in known):
            return f"입력에 없는 사람({name} {pos})"
    return None


def summarize_today(req: SummarizeRequest, llm: LLMClient) -> SummarizeResponse:
    """오늘 요약(mode=today, AI-D21). 숫자 줄은 counts(코드), 문장은 모델 — 모델이 없거나 실패 · 검증에 걸리면 코드 문장."""
    f = today_facts(req)
    code_text = code_briefing(f)
    if not req.use_model:
        return SummarizeResponse(text=code_text, source="code", counts=f.counts)
    if not f.listed:  # 오늘까지 기한인 업무가 없으면 모델이 더할 것이 없다 — 부르지 않는다
        return SummarizeResponse(text=code_text, source="code", counts=f.counts, fallback="오늘까지 기한 없음")
    source = model_input(f)
    try:
        text = llm.chat_text(prompts.SUMMARY_TODAY, source).strip()
    except LLMError as e:
        return SummarizeResponse(text=code_text, source="code", counts=f.counts, fallback=str(e))
    if problem := check_briefing(text, f, source):
        return SummarizeResponse(text=code_text, source="code", counts=f.counts, fallback=f"검증 실패: {problem}")
    return SummarizeResponse(text=text, source="exaone", prompt_version=prompts.PROMPT_VERSION, counts=f.counts)


# ---------- 일일 회고 · 주간 회고 머리 문장 (AI-29, io_spec 3.3 · 3.4절) ----------

@dataclass
class Headline:
    """회고 머리 문장 재료. code: 코드 문장 · source: 모델 입력 · allowed: 문장에 나와도 되는 건수 · people: 입력에 있는 사람."""

    code: str
    source: str
    allowed: set[int]
    people: set[str]
    counts: dict[str, int]


def _names(items: list[BriefingItemIn], n: int = 3) -> str:
    more = " 등" if len(items) > n else ""
    return ", ".join(f"{i.sender or UNKNOWN_SENDER}의 '{i.text}'" for i in items[:n]) + more


def _list(title: str, items: list[BriefingItemIn]) -> list[str]:
    return [title] + ([f"- {i.sender or UNKNOWN_SENDER}: {i.text}" for i in items] or ["- 없음"])


def evening_facts(req: SummarizeRequest) -> Headline:
    """일일 회고(17:30): 금일 완료 · 미처리 · 익일 마감(io_spec 3.3절). 머리 문장 ① 완료 건수 + 상급자 건 ② 남은 건수 + 기한 지남
    ③ 내일 기한 건수 + 시각 있는 일정."""
    s = {x.id: x.items for x in req.sections}
    done, remaining, tomorrow = s.get("done_today", []), s.get("remaining", []), s.get("due_tomorrow", [])
    done_sup = [i for i in done if i.is_superior]
    overdue = [i for i in remaining if i.due_at and i.due_at < req.now]
    overdue_sup = [i for i in overdue if i.is_superior]
    events = sorted((i for i in tomorrow if i.due_at and _is_event(i)), key=lambda i: i.due_at)
    out = [f"오늘 완료한 업무는 {len(done)}건이며, 상급자 건은 {_names(done_sup)}입니다." if done_sup
           else f"오늘 완료한 업무는 {len(done)}건입니다." if done else "오늘 완료한 업무는 없습니다."]
    if remaining:
        tail = f"그중 기한이 지난 것은 {len(overdue)}건입니다." if overdue else "기한이 지난 것은 없습니다."
        out.append(f"남은 미처리 업무는 {len(remaining)}건이고, {tail}")
    else:
        out.append("남은 미처리 업무는 없습니다.")
    ev = ", ".join(f"{i.due_at:%H:%M} {i.sender or UNKNOWN_SENDER} '{i.text}'" for i in events)
    if tomorrow:
        out.append(f"내일 기한인 업무는 {len(tomorrow)}건이며, {ev} 일정이 있습니다." if ev
                   else f"내일 기한인 업무는 {len(tomorrow)}건입니다.")
    else:
        out.append("내일 기한인 업무는 없습니다.")
    lines = [f"현재 시각: {req.now:%Y-%m-%d %H:%M}", f"[금일 완료] {len(done)}건", *_list("[금일 완료 · 상급자]", done_sup),
             f"[미처리] {len(remaining)}건", f"[기한 지남] {len(overdue)}건", *_list("[미처리 · 기한 지남 · 상급자]", overdue_sup),
             f"[익일 마감] {len(tomorrow)}건", "[익일 · 일정]",
             *([f"- {i.due_at:%H:%M} {i.sender or UNKNOWN_SENDER}: {i.text}" for i in events] or ["- 없음"])]
    allowed = {len(done), len(done_sup), len(remaining), len(overdue), len(overdue_sup), len(tomorrow), len(events),
               len(remaining) - len(overdue), len(tomorrow) - len(events)}  # 뺀 값('그 밖 M건')도 맞는 숫자
    return Headline(" ".join(out), "\n".join(lines), allowed, {i.sender for i in done + remaining + tomorrow if i.sender},
                    {"done_today": len(done), "remaining": len(remaining), "due_tomorrow": len(tomorrow)})


def weekly_facts(req: SummarizeRequest) -> Headline:
    """주간 회고(금 17:30): 금주 완료 · 다음 주로 넘어가는 일 · 회신 대기 · 차주 마감(io_spec 3.4절). 머리 문장 ① 완료 건수 + 기한 후 완료
    ② 넘어가는 일 건수 + 상급자 건 ③ 다음 주 기한 건수 + 가장 몰린 요일."""
    s = {x.id: x.items for x in req.sections}
    done, carry, waiting, nxt = (s.get(k, []) for k in ("done_week", "carry_over", "waiting", "due_next_week"))
    late = [i for i in done if i.due_at and i.done_at and i.done_at > i.due_at]
    carry_sup = [i for i in carry if i.is_superior]
    by_day: dict[int, int] = {}
    for i in nxt:
        if i.due_at:
            by_day[i.due_at.weekday()] = by_day.get(i.due_at.weekday(), 0) + 1
    peak = max(by_day.items(), key=lambda kv: (kv[1], -kv[0])) if by_day else None  # 같으면 이른 요일
    out = [f"이번 주 완료한 업무는 {len(done)}건이며, 그중 기한 후 완료는 {len(late)}건입니다." if late
           else f"이번 주 완료한 업무는 {len(done)}건입니다." if done else "이번 주 완료한 업무는 없습니다."]
    wait = f" 회신을 기다리는 건은 {len(waiting)}건입니다." if waiting else ""
    if carry:
        sup = f"이며, 상급자 건은 {_names(carry_sup)}입니다." if carry_sup else "입니다."
        out.append(f"다음 주로 넘어가는 업무는 {len(carry)}건{sup}{wait}")
    else:
        out.append(f"다음 주로 넘어가는 업무는 없습니다.{wait}")
    if peak:
        out.append(f"다음 주 기한인 업무는 {len(nxt)}건이며, {WEEKDAYS[peak[0]]}요일에 {peak[1]}건으로 가장 많습니다.")
    else:
        out.append(f"다음 주 기한인 업무는 {len(nxt)}건입니다." if nxt else "다음 주 기한인 업무는 없습니다.")
    lines = [f"현재 시각: {req.now:%Y-%m-%d %H:%M}", f"[금주 완료] {len(done)}건", f"[기한 후 완료] {len(late)}건",
             f"[다음 주로 넘어가는 일] {len(carry)}건", *_list("[넘어가는 일 · 상급자]", carry_sup),
             f"[회신 대기] {len(waiting)}건", f"[차주 마감] {len(nxt)}건",
             "[가장 몰린 요일] " + (f"{WEEKDAYS[peak[0]]}요일 {peak[1]}건" if peak else "없음")]
    allowed = {len(done), len(late), len(done) - len(late), len(carry), len(carry_sup), len(waiting), len(nxt)}
    allowed |= {peak[1]} if peak else set()
    return Headline(" ".join(out), "\n".join(lines), allowed, {i.sender for i in done + carry + waiting + nxt if i.sender},
                    {"done_week": len(done), "carry_over": len(carry), "waiting": len(waiting), "due_next_week": len(nxt)})


def summarize_review(req: SummarizeRequest, llm: LLMClient) -> SummarizeResponse:
    """일일 · 주간 회고 머리 문장(AI-29). 오늘 요약과 같은 규칙: 모델이 없거나 실패 · 검증에 걸리면 코드 문장."""
    h = evening_facts(req) if req.mode == "evening" else weekly_facts(req)
    if not req.use_model:
        return SummarizeResponse(text=h.code, source="code", section_counts=h.counts)
    if not any(h.counts.values()):  # 모든 묶음이 비면 모델이 더할 것이 없다
        return SummarizeResponse(text=h.code, source="code", section_counts=h.counts, fallback="묶음 없음")
    system = prompts.SUMMARY_EVENING if req.mode == "evening" else prompts.SUMMARY_WEEKLY
    try:
        text = llm.chat_text(system, h.source).strip()
    except LLMError as e:
        return SummarizeResponse(text=h.code, source="code", section_counts=h.counts, fallback=str(e))
    if problem := check_text(text, h.source, h.allowed, h.people):
        return SummarizeResponse(text=h.code, source="code", section_counts=h.counts, fallback=f"검증 실패: {problem}")
    return SummarizeResponse(text=text, source="exaone", prompt_version=prompts.PROMPT_VERSION, section_counts=h.counts)


def summarize(req: SummarizeRequest, llm: LLMClient) -> SummarizeResponse:
    if req.mode == "today":
        return summarize_today(req, llm)
    if req.mode in ("evening", "weekly"):
        return summarize_review(req, llm)
    return summarize_mail(req, llm)


_HANGUL = re.compile(r"[\uac00-\ud7a3\u1100-\u11ff\u3130-\u318f]")
_KANA = re.compile(r"[\u3040-\u30ff]")
_HAN = re.compile(r"[\u4e00-\u9fff]")
_LATIN = re.compile(r"[A-Za-z\u00c0-\u024f]")
_LATIN_WORD = re.compile(r"[A-Za-z\u00c0-\u024f]+")
_ACCENTED = re.compile(r"[\u00c0-\u024f]")
# 영어와 다른 라틴 문자 언어를 가르는 기능어. 양쪽에 다 있는 짧은 낱말(a · in · is · me · we · an · die · was · will
# · per · met · non · do · da · al · un · o · e · i · os · est · com 등)은 넣지 않는다 — 한쪽으로 기울이지 않게.
_EN_WORDS = frozenset("""
the and you your for please with this that are be to of it its from by as at or not but if all any my our
they them their would could should have has had can let there here what when which who how about been
thanks thank hi hello dear regards sincerely attached kindly
""".split())
_OTHER_LATIN_WORDS = frozenset("""
le la les des du et vous nous pour que qui une dans pas avec sur au aux ce cette sont avez votre vos notre
merci bonjour cordialement je
der das und ist sie wir nicht mit ein eine einen bitte ich zu den dem für auf bis von sind haben ihr ihre
ihnen danke hallo grüße freundlichen können
el los las y es por para una del se usted gracias hola su sus está muy saludos
il di che gli della sono grazie ciao è
você não em uma obrigado obrigada olá dos das
het een en van niet wij ik je jij voor dat hebben groeten bedankt
""".split())


def _latin_lang(text: str) -> str:
    """라틴 문자 글이 영어인지('en'), 영어가 아닌 다른 언어인지('other') 기능어 수로 가른다.
    서명 · 인용문 · 고유명사(Café Müller · José)보다 본문 기능어가 많으니 수가 많은 쪽을 따른다.
    둘 다 없거나 같으면(아주 짧은 글) 악센트 글자가 3% 이상일 때만 'other'다."""
    words = [w.lower() for w in _LATIN_WORD.findall(text)]
    en = sum(w in _EN_WORDS for w in words)
    other = sum(w in _OTHER_LATIN_WORDS for w in words)
    if en != other:
        return "en" if en > other else "other"
    letters = len(_LATIN.findall(text))
    return "other" if letters and len(_ACCENTED.findall(text)) / letters >= 0.03 else "en"


def detect_lang(text: str) -> str:
    """원문 언어를 글자 비율로 고른다. 모델 전에 코드로 정한다.
    - 한글이 글자의 20% 이상이면 'ko'(국문 메일 속 영문 용어 · 서명은 흔하다)
    - 가나가 10% 이상이면 'ja'(일본어는 한자와 섞인다), 한자가 30% 이상이면 'zh'
    - 나머지 라틴 문자는 영어면 'en', 불어 · 독일어 · 스페인어처럼 영어가 아니면 'other'(기타 외국어).
      카드에 '원문 언어: 영어'로 잘못 보이지 않게 한다(이재운 리뷰). 언어 이름을 더 나누지는 않는다.
    - 글자가 없으면 'ko'(옮길 내용이 없다)"""
    counts = {k: len(p.findall(text)) for k, p in (("ko", _HANGUL), ("ja", _KANA), ("zh", _HAN), ("en", _LATIN))}
    total = sum(counts.values())
    if total == 0 or counts["ko"] / total >= 0.2:
        return "ko"
    if counts["ja"] / total >= 0.1:
        return "ja"
    if counts["zh"] / total >= 0.3:
        return "zh"
    return _latin_lang(text) if counts["en"] else "ko"


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
