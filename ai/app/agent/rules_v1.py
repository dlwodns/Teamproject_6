"""명령 해석 규칙 v1 (AI-11, AI detail 4.2절). 행동 1개가 정확히 걸리면 확정, 0개 · 2개 이상이면 엑사원으로 넘긴다.

모델은 메일 본문을 보지 않는다. 날짜 표현은 분류 후처리와 같은 코드로 환산한다(app.pipeline.dates).
"""
import re
from datetime import datetime, time, timedelta

from app.pipeline.dates import _find_time, parse_date_range, parse_due
from app.schemas.agent import DateRange, Target

RULES_VERSION = "agent_rules_v1.2"

# v1.2: 흔한 바꿔 말하기를 더 잡고(아래 '# v1.2' 표시), 지원 외 · 애매 일부를 모델 없이 판정한다(AI-1 응답 시간).
PATTERNS: dict[str, re.Pattern] = {
    "T01": re.compile(r"(?:오늘|내일).*(?:뭐\s*(?:해야|있)|할\s*(?:일|거|것)|해야\s*할|요약|정리)|하루\s*요약|브리핑"),
    "T02": re.compile(r"(?:미처리|안\s*한|못\s*한|못\s*끝낸|남은|남아\s*있는|밀린|처리\s*안\s*된|대기\s*중).*(?:보여|알려|뭐|있어|찾아|목록)|메일\s*중|건\s*중|(?:보여\s*줘|찾아\s*줘|목록)$"),
    "T03": re.compile(r"(?:처리|완료|끝|마무리|해결)\s*(?:했|됐|냈|함|했어|했음)|(?:끝냈|마쳤|끝났|다\s*했)|완료\s*(?:해|처리|로)|^\s*(?:이거|이것|그거)\s*완료"
                      r"|(?:회신|답장|답)\s*(?:은|도|을|를)?\s*(?:다\s*|전부\s*|모두\s*)?보냈"),  # v1.2 '회신은 다 보냈어'
    "T04": re.compile(r"취소|되돌려|되돌리|원래대로|원상\s*복구|방금\s*(?:거|것)\s*(?:취소|되돌)"),
    "T05": re.compile(r"다시\s*알려|나중에|미뤄|미루|연기\s*(?:해|시켜)|리마인드\s*해|알림\s*(?:줘|해\s*줘)"),
    "T06": re.compile(r"(?:답장|회신|답변|답)\s*(?:이)?\s*(?:안\s*(?:온|왔|오|준)|없는|못\s*받)|무응답"),
    "T07": re.compile(r"(?:회신|답장)\s*(?:초안|문안)|(?:답장|회신|답)\s*(?:좀\s*)?(?:써|작성)"),
    "T08": re.compile(r"왜\s*.*(?:미처리|중요|업무|떴|들어|할\s*일|잡혔|분류|올라)|(?:이유|근거)\s*(?:가|를|좀)?\s*(?:뭐|알려|설명)"),
    "T09": re.compile(r"(?:아침\s*알림|리마인드|알림).*(?:바꿔|설정|으로\s*해|로\s*해)|매일\s*.*(?:시|시에)\s*알려|알림\s*(?:시간|시각)"),
    "T10": re.compile(r"(?:빼\s*(?:줘|$)|빼$|제외\s*(?:해|시켜|처리)?|업무\s*아니|숨겨|안\s*보이게)"),
    "T11": re.compile(r"(?:항상|늘|앞으로|무조건).{0,15}중요(?:로|하게)|(?:항상|늘)\s*중요|중요\s*발신자|중요로\s*(?:해|지정|표시)|즐겨찾기\s*(?:해|추가)"),
    "T12": re.compile(r"(?:한테|에게|께)\s*.*(?:메일|초안)\s*(?:좀\s*)?(?:써|작성)|(?:메일|초안).*(?:한테|에게|께)\s*(?:좀\s*)?(?:써|작성)"),
    "T13": re.compile(r"(?:기한|마감).*(?:보여|언제|알려|몰린|봐\s*줘)|캘린더|달력"),
    "T14": re.compile(r"(?:재촉|독촉|다시\s*요청|팔로우\s*업).*(?:메일|보내|발송)|템플릿.*(?:보내|발송|전송)"),
}

# 행동 목록에 없는 메일 조작은 모델에 묻지 않고 지원 외로 막는다. 모델은 가장 가까운 T10(제외)을 골랐다(AI-T6).
# 규칙이 행동을 하나도 못 찾았을 때만 본다 — '김 팀장께 전달할 메일 써줘'는 T12가 먼저 걸린다
UNSUPPORTED = re.compile(r"삭제|지워|지우|휴지통|전달\s*해|포워드|포워딩|스팸\s*(?:신고|등록|처리)|차단|수신\s*거부"
                         r"|구독\s*(?:취소|해지)|첨부.*(?:다운|저장|열어)|인쇄|번역|읽음\s*(?:으로|표시|처리)|폴더.*(?:옮|이동)")
# 메일 업무와 무관한 요청. 메일 업무 낱말이 하나도 없을 때만 지원 외로 판정한다(MAIL_WORDS)
OFF_TOPIC = re.compile(r"날씨|주식|시세|환율|점심|저녁\s*메뉴|메뉴\s*추천|맛집|노래|음악|농담|게임|운세|퀴즈")
MAIL_WORDS = re.compile(r"메일|회신|답장|답변|건|기한|마감|알림|초안|발신|수신|보낸|받은|업무|할\s*일|처리|완료|템플릿|일정")
# 무엇을 할지 말하지 않은 지시('알아서 해' · '손 좀 봐줘' · '정리 좀'). 행동이 하나도 안 걸렸을 때만 되묻기로 보낸다
VAGUE = re.compile(r"알아서|어떻게\s*(?:좀\s*)?해|손\s*(?:좀\s*)?(?:봐|보)|(?:정리|처리|챙겨|해결)\s*(?:좀|해\s*줘|해\s*봐|해$)|좀\s*봐\s*줘")
# '취소'가 되돌리기가 아니라 메일 속 일정 · 구독을 가리키는 경우('회의 취소 메일 써줘' · '구독 취소해줘')
NOT_UNDO = re.compile(r"(?:구독|수신|회의|미팅|일정|약속|예약|주문|결제|신청|출장)\s*(?:을|를|은|는)?\s*취소")
QUESTION = re.compile(r"\?\s*$|(?:했|됐|냈)(?:나|니|는지|나요|어요\?)\s*\??\s*$")

# T05는 '날짜 + 다시 알려/나중에'가 함께 있어야 한다(아래 match에서 확인)
NEEDS_DATE = {"T05"}

# 충돌 규칙 (AI detail 4.1): 앞 행동이 걸리면 뒤 행동 후보를 지운다
BEATS = {
    "T04": {"T03", "T05", "T10", "T14"},  # '완료 취소' · '방금 거 취소'
    "T03": {"T07", "T02", "T06", "T01"},  # 과거형 완료 우선 — '회신 다 했어'
    "T14": {"T06", "T12", "T07", "T05"},  # '답장 안 온 거 재촉 메일 보내줘'
    "T05": {"T13", "T02", "T09"},
    "T09": {"T05"},
    "T07": {"T12"},
    "T13": {"T02"},
    "T06": {"T02"},
    "T11": {"T10"},
}

TITLES = r"팀장|책임|선임|차장|부장|과장|대리|사원|사업단장|담당|상무|전무|이사|매니저|프로"
SENDER = re.compile(rf"([가-힣]{{1,4}})\s?({TITLES})\s?님?")
CATEGORY = re.compile(r"(회신|요청|검토|공지|기타)\s*(?:메일|건|업무)")
DEICTIC = re.compile(r"이거|이것|저거|그거|아까\s*그|선택한|고른|위에\s*거|(?:^|\s)(?:이|저)\s+[가-힣]")  # '이 뉴스레터는'
FROM_LAST = re.compile(r"그\s*\d+\s*건|그\s*(?:메일|것)들|그것들|걔네|방금\s*(?:목록|나온)")
KEYWORD = re.compile(r"([가-힣A-Za-z0-9]{2,})\s*건(?:은|는|을|를|도|이|만)?(?:\s|$)")
NOT_KEYWORD = {"이번", "다음", "오늘", "내일", "방금", "모든", "전체", "남은", "그", "이", "공지", "회신", "요청", "검토", "기타"}
NUDGE = re.compile(r"재촉|독촉|다시\s*요청|팔로우\s*업")
TEMPLATE_NAME = re.compile(r"['\"‘“]([^'\"’”]+)['\"’”]")
MORNING_DEFAULT = time(8, 30)  # 리마인드 기본 시각 (기획 detail 4.2, 문규남 11-02)


def match(text: str, now: datetime) -> list[str]:
    hits = [aid for aid, pat in PATTERNS.items() if pat.search(text)]
    if "T03" in hits and QUESTION.search(text):  # '답장 보냈어?' · '다 처리했나?' — 완료 보고가 아니라 질문
        hits.remove("T03")
    if "T04" in hits and NOT_UNDO.search(text) and not re.search(r"되돌|원래대로|원상\s*복구|방금|아까", text):
        hits.remove("T04")
    if "T05" in hits and not (parse_due(text, now) or re.search(r"나중에|미뤄|미루|연기", text)):
        hits.remove("T05")
    for winner in list(hits):
        for loser in BEATS.get(winner, ()):
            if loser in hits and winner in hits:
                hits.remove(loser)
    return hits


def extract_target(text: str, ctx) -> Target:
    t = Target()
    m = SENDER.search(text)
    if m:
        t.sender = f"{m[1]} {m[2]}"
    m = CATEGORY.search(text)
    if m:
        t.category = m[1]
    rng = parse_date_range(text, ctx.now)
    if rng:
        t.date_range = DateRange(start=rng[0], end=rng[1])
    if DEICTIC.search(text) and ctx.selected_mail_ids:
        t.mail_ids = list(ctx.selected_mail_ids)
    elif FROM_LAST.search(text) and ctx.last_result_ids:
        t.mail_ids = list(ctx.last_result_ids)
    for m in KEYWORD.finditer(text):
        word = m[1]
        if word not in NOT_KEYWORD and not word.isdigit() and not re.search(rf"(?:{TITLES})님?$", word):
            t.keyword = word
            break
    return t


def extract_params(action: str, text: str, ctx, target: Target) -> dict:
    now = ctx.now
    if action == "T01":
        return {"date": (now.date() + timedelta(days=1 if "내일" in text else 0)).isoformat()}
    if action == "T05":
        due = parse_due(text, now)
        until = due.due_at if due else None
        if until is not None and _find_time(text) is None:
            until = until.replace(hour=MORNING_DEFAULT.hour, minute=MORNING_DEFAULT.minute)  # 시각 없으면 아침 알림 시각
        return {"until": until.isoformat() if until else None}
    if action == "T06":
        m = re.search(r"(\d+)\s*일\s*(?:이상|넘|지난)", text)
        return {"min_days": int(m[1]) if m else 3}
    if action == "T09":
        t = _find_time(text)
        m = re.search(r"기한\s*(\d+)\s*시간\s*전", text)
        if m:
            return {"rule": "before_due", "hours": int(m[1])}
        return {"rule": "morning", "time": t.strftime("%H:%M") if t else None}
    if action == "T11":
        return {"level": "superior" if re.search(r"상급자|윗분|상사", text) else "favorite"}
    if action == "T14":
        nudge = bool(NUDGE.search(text))
        name = TEMPLATE_NAME.search(text)
        if nudge and not target.mail_ids:
            target.awaiting_reply = True  # '재촉 메일 보내줘' → 직전 무응답 목록(3일 이상)
        return {"template_kind": "nudge" if nudge else "send", "template_name": name[1] if name else None}
    if action == "T07":
        tone = "short" if re.search(r"짧게|간단", text) else "polite"
        return {"tone": tone}
    if action == "T12":
        m = re.search(r"(?:한테|에게|께)\s*(.+?)\s*(?:관련|에\s*대한)?\s*(?:메일|초안)", text)
        return {"topic": m[1].strip() if m else None}
    return {}


def reject_reason(text: str) -> str | None:
    """규칙이 행동을 하나도 못 찾았을 때, 모델 없이 정할 수 있는 거절 사유. 없으면 None (모델로 넘긴다)."""
    if UNSUPPORTED.search(text) or (OFF_TOPIC.search(text) and not MAIL_WORDS.search(text)):
        return "unsupported"
    if VAGUE.search(text):
        return "ambiguous"
    return None
