"""메일 규칙 판별 v1 (AI-2). 요청 표현 · 공지 · 참조 · 지목 · 긴급 · 재요청을 보고 확신도를 낸다(D14).

확신도가 낮은 메일만 라우터가 엑사원으로 보낸다(AI-3). 규칙은 '할 일을 놓치지 않는 쪽'으로 기운다(D15).
"""
import re
from dataclasses import dataclass, field
from datetime import datetime

from app.pipeline.dates import DueParse, parse_deadline, parse_due_plain

RULES_VERSION = "mail_rules_v1.8"

REQUEST = re.compile(
    r"부탁드(?:립니다|려요|리겠습니다|립니다)|부탁합니다|바랍니다|주십시오|주세요|주실\s*수\s*있(?:을까요|을지)|주시겠어요|"
    r"주시면\s*(?:감사|좋겠)|요청드립니다|다시\s*요청|여쭙니다|문의드립니다|해\s*주시기|받을\s*수\s*있을까요|"
    # v1.6(DE-9 ①): 조건형 부탁 '의견 주시면 반영하겠습니다 · 결재해 주시면 정산됩니다'. '알려주시면 됩니다'처럼 뒤에 결과가 없으면 아니다
    r"주셨으면\s*(?:합니다|좋겠)|주시고(?=\s*,|$)|가능하실까요|가능할까요|가능하신지요|주시면\s+\S.*?(?:겠습니다|됩니다)|"
    # v1.6(DE-9 ③): 재요청 · 마감 변경 '내일 정오까지는 받아야 할 것 같습니다' · '명단 마감을 10/20로 당깁니다'
    r"까지는?\s*(?:꼭\s*)?받아야|주셔야\s*(?:합니다|해요|할\s*것)|"
    # v1.8: 착수 후 2주 이내에 제출해야 합니다 · 의견을 다음 주 초까지 받고 싶습니다 · 제 방으로 와 주세요
    r"(?:제출|회신|작성|보고|신청)해야\s*(?:합니다|해요)|(?:의견|회신|답)을?\s*(?:\S+\s+){0,3}?받고\s*싶|와\s*주세요|와\s*주십시오|마감(?:을|이|일을)?\s*.{0,25}?(?:당깁니다|앞당깁니다|변경합니다|연장합니다)"
)
# v1.6(DE-9 ⑥): '수신을 원치 않으시면 ~ 눌러주세요 · 관심 있으시면 등록해 주세요 · 필요하시면 연락 주세요'는 받는 사람이 고르는 선택이다
OPTIONAL = re.compile(r"(?:원하시|원치\s*않으시|관심\s*(?:있으시|이\s*있으시)|필요하시|궁금하시|희망하시|문의\s*사항이\s*있으시)면|"
                      r"(?:있으신|원하시는|희망하시는|관심\s*있으신)\s*분(?:은|들은|께서는)|희망자는|"  # v1.8 의견 있으신 분은 · 희망자는
                      r"(?:그\s*외|기타)\s*(?:문의|궁금)|문의\s*사항은|궁금한\s*점은")  # v1.7: 맺음말 '그 외 문의 사항은 ~로 연락 주세요'
# v1.7: 회의 초대의 '참석이 어려우시면 대리 참석자를 알려주세요'는 못 갈 때의 대안이다. 할 일은 회의 참석이다
CONTINGENT = re.compile(r"어려우시면|어려우실\s*경우|불참(?:하시는|하실|\s*시)|못\s*오시면")
# v1.7: '다시 말씀드리면 ~' · '정리하면 ~'은 앞 요청을 다시 말한 것이다(떨어져 있어도 같은 업무)
RESTATE = re.compile(r"^(?:다시\s*말씀드리면|정리하면|요약하면|다시\s*한\s*번\s*말씀)")
ALSO_SAME = re.compile(r"\S도\s*함께|\S도\s*같이")  # '동의 여부도 함께 표시해 주세요' → 바로 앞 요청에 딸린 일
NOT_TASK = re.compile(r"참고\s*(?:만\s*)?(?:부탁|해\s*주세요|해\s*주시|바랍니다|하시기)|양해\s*부탁|(?:주|하)시면\s*됩니다|협조\s*부탁|말씀\s*부탁|문의\s*(?:바랍|주시)|감사드립니다$|"
                      r"(?:두|세|네|몇|\d+)\s*(?:가지|건)\s*(?:를\s*)?(?:(?:요청|부탁|문의)드립니다|여쭙니다|여쭤봅니다)")  # 'N가지 요청드립니다'는 아래 목록의 머리말
SOFT = re.compile(r"시간\s*되실\s*때|번거로우시겠지만|혹시|가능하시면|괜찮으시면")
URGENT = re.compile(r"긴급|급히|급하게|급함|시급|촉박|서둘러|ASAP|asap|즉시|최대한\s*빨리|가능한\s*(?:한\s*)?빨리|조속히")
URGENT_APOLOGY = re.compile(r"(?:급히|급하게)\s*(?:\S+\s*){0,2}?(?:죄송|양해|송구)")  # v1.7 '급하게 변경드려 죄송합니다'는 사과다
FOLLOW_UP = re.compile(r"다시\s*(?:요청|연락|여쭙|여쭈|부탁|말씀드(?!리면))|재요청|아직\s*(?:도착|회신|받지|못|안\s*(?:왔|들어|오))|리마인드|재차|"
                       r"지난\S*\s*(?:\S+\s+)?(?:요청|부탁|말씀)드린\s*\S+\s*(?:건|진행|관련)")  # v1.8 지난주 요청드린 ~ 진행 상황
# v1.8: 할 일이 없다고 밝힌 문장(참고만 해 주세요 · 하실 일은 없습니다). 조건문(없으면 회신하지 않으셔도)은 아니다
NO_ACTION = re.compile(r"참고만|하실\s*(?:일|것)은\s*없|(?:필요한|하실)\s*(?:사항|조치)은\s*(?:아직\s*)?없|조치(?:는|하실\s*것은)?\s*필요\s*없|"
                       r"별도\s*(?:조치|회신)(?:는|은)?\s*(?:필요\s*)?없")
AUTO_REPLY = re.compile(r"자동\s*회신|자동\s*응답|부재\s*중|Out\s*of\s*Office|Automatic\s*reply", re.I)
# '견적을 다시 산정' · '다시 안내드리겠습니다'의 '다시'는 재요청이 아니다. 회신 제목에서도 FOLLOW_UP 표현만 본다
REPLY_SUBJECT = re.compile(r"^\s*(?:RE|Re|re|회신)\s*:")
NOTICE_SUBJECT = re.compile(r"\[(?:공지|안내|인사|정보보안|IT운영|공유)\]|안내$|안내\s*\(|공지")
NOTICE_BODY = re.compile(r"안내(?:드립니다|합니다)|실시합니다|공지(?:드립니다|합니다)|진행됩니다")
MISC_SUBJECT = re.compile(r"Weekly|뉴스레터|newsletter|동호회|소식|이벤트|광고|복지", re.I)  # v1.8 사내 소식 · 복지는 기타(11/5 결정)
MEETING = re.compile(r"\[(?:회의|초대|미팅)\]|회의(?!록)|미팅|보고회|설명회|워크숍|간담회")
EVENT_BLOCK = re.compile(r"^\s*(?:[-·•※]\s*)?장소\s*[:：]", re.M)  # '일시:' 줄과 함께 있으면 행사 안내 블록(DE-9 ⑤)
HAS_TIME = re.compile(r"\d{1,2}:\d{2}|\d{1,2}시(?!간)")
MEETING_WHEN = re.compile(r"일시\s*[:：]\s*(.+)")
ANSWER = re.compile(r"(?:요청하신|말씀하신|문의하신).{0,40}(?:첨부|드립니다|공유|보내|완료|확정|가능합니다|진행할\s*예정)|첨부(?:드립니다|했습니다)|공유드립니다")

# '엑셀로 공유' · 'CSV로 내려받아'처럼 파일 형식을 정해 달라는 요청은 자료 제출이다('공유 바랍니다'만으로는 회신)
FILE_AS = r"(?:엑셀|xlsx|csv|CSV|워드|docx|PPT|pptx|PDF|pdf|파일)\s*(?:표\s*)?(?:로|으로)\s*(?:\S+\s*)?(?:공유|보내|받|내려받|전달|올려|회신)"
TYPE_RULES: list[tuple[str, re.Pattern]] = [
    ("수정재전송요청", re.compile(r"원본|재전송|재제출|다시\s*(?:보내|올려|공유|제출)|보완(?!할\s*(?:점|부분|사항))|(?:으로|로)\s*바꾼|바꿔\s*(?:서|주)")),
    # v1.8: '보완할 점 있으면 말씀 주세요'는 검토 의견이다
    ("검토승인요청", re.compile(r"보완할\s*(?:점|부분|사항)")),
    ("검토승인요청", re.compile(r"결재|승인|검토\s*(?:부탁|요청|해\s*주|후|하시고|하신\s*뒤)|봐\s*주(?:시|셨)")),
    ("수정재전송요청", re.compile(r"수정")),
    ("일정참석", re.compile(r"참석\s*(?:여부|가능|해\s*주|해서|하셔서|하시어|부탁|바랍)|와\s*주(?:세요|십시오)|모여\s*주")),
    # v1.8: 이름 · 성함 · 연락처 · 가부 · 의견처럼 짧은 답을 보내 달라는 것은 회신이다(자료 제출 아님). 판단 · 결정도 회신
    ("회신요청", re.compile(r"(?:이름|성함|연락처|가부|여부|의견)\S{0,2}\s*(?:만\s*)?(?:\S+\s+)?(?:보내|알려|회신|주시)|판단해\s*주|판단\s*부탁|결정해\s*주")),
    ("자료제출요청", re.compile(r"제출|작성|취합|자료|양식|공유해\s*주|보내\s*주|파일|안건도|입력|완료해|내려받|다운로드|" + FILE_AS)),
    ("회신요청", re.compile(r"의견|회신|알려|답변|확인|여부|지정|정리|보고해")),  # '현황을 정리해 보고' · '현황을 회신'은 회신
]
STRONG_REPLY = re.compile(r"의견|답변|여부|알려")  # 문장에 이 말이 있으면 제목 머리말('검토')보다 문장을 따른다
RESEND_SUBJECT = re.compile(r"원본|수정본|재전송")  # 제목이 원본 · 수정본을 다시 달라는 메일이면 '보내 주세요'도 재전송
BARE_CHECK = re.compile(r"^(?:[^\s,]+\s*)?(?:한번\s*|내용\s*)?(?:확인|검토)$")  # 대상 없는 '확인 부탁드립니다'(전달 메일의 머리말)
GENERAL_AUDIENCE = re.compile(r"미(?:이수|적용|제출|완료|조치)자|해당(?:자|되시는\s*분)|대상자|전\s*(?:직원|임직원|사원)|임직원\s*여러분|모든\s*(?:직원|임직원|구성원)|구성원\s*여러분")
DEFAULT_TYPE = "회신요청"  # 유형 단어가 없어도 나를 향한 요청은 버리지 않는다(D15)
ALSO_ME = re.compile(r"(?:께서도|님도)\s*(?:한번\s*|함께\s*|같이\s*)?(?:확인|검토|봐)")  # 앞사람에게 한 요청을 나에게도 거는 말
CONTINUES = re.compile(r"^(?:특히|또한|아울러)\b")  # 앞 요청을 덧붙이는 문장
ENUM = re.compile(r"^(?:첫째|둘째|셋째|넷째|다섯째|\d+\s*[.)]|[①-⑩])")  # '첫째, … 둘째, …'는 따로 세는 요청이다(한 메일 여러 업무)
SUBJECT_TYPE = [("검토승인요청", re.compile(r"검토|결재|품의|승인")), ("자료제출요청", re.compile(r"취합|제출|자료|명단|목록")),
                ("수정재전송요청", re.compile(r"원본|수정")), ("회신요청", re.compile(r"문의|의견"))]
FORMATS = [("xlsx", r"엑셀|xlsx|excel"), ("pptx", r"pptx|PPT|장표|발표\s*자료"), ("drawio", r"drawio"),
           ("pdf", r"pdf|PDF"), ("docx", r"워드|docx"), ("csv", r"csv|CSV")]


@dataclass
class RuleTask:
    text: str
    action_type: str
    evidence: str
    format: str | None = None
    due: DueParse | None = None
    weak_type: bool = False  # 유형 단어가 문장에 없어 제목 머리말 · 기본값으로 정한 유형
    specific: bool = False  # v1.8 유형을 콕 집는 단서(재제출 · 원본 · 와 주세요 · 이름만 보내)로 정함 → 형식(kind)보다 앞선다


@dataclass
class RuleResult:
    action_types: list[str]
    tasks: list[RuleTask]
    mentioned_me: bool
    urgent: bool
    is_follow_up: bool
    recipient: str  # to | cc | list
    confidence: float
    reasons: list[str] = field(default_factory=list)
    optional: list[str] = field(default_factory=list)  # v1.8 '의견 있으신 분은 ~'처럼 받는 사람이 고르는 요청 문장
    not_mine: list[str] = field(default_factory=list)  # 요청 문장인데 나를 향하지 않은 것('전 임직원은 ~' · 남을 부른 요청). 엑사원 합치기에 쓴다


def strip_body(body: str) -> list[str]:
    """서명란 · 첫 줄 자기소개 · 맺음말을 빼고 본문 줄만 남긴다."""
    lines = [ln.strip() for ln in re.split(r"\n\*{5,}|\n-{5,}", body)[0].split("\n")]
    if lines and re.match(r"^안녕하세요.*입니다\.?$", lines[0]):
        lines = lines[1:]
    return [ln for ln in lines if not re.fullmatch(r"(감사합니다|고맙습니다|수고하세요)\.?", ln)]


def _sentences(lines: list[str]) -> list[tuple[int, str]]:
    out = []
    for i, ln in enumerate(lines):
        for s in re.split(r"(?<=[.?!])\s+", ln):
            if s.strip():
                out.append((i, s.strip()))
    return out


def _clauses(sentence: str) -> list[str]:
    # '회신해 주시고, 안건도 보내주세요' → 요청 2개
    parts = re.split(r"(?<=주시고),\s*|(?<=하시고),\s*", sentence)
    return [p for p in parts if p.strip()]


def _mentions_me(text: str, owner) -> bool:
    keys = [k for k in (owner.name, owner.team) if k]
    if owner.team and (short := re.search(r"(\d+팀)$", owner.team)):  # v1.8 클라우드전환1팀 → '1팀에 ~'
        keys.append(short.group(1))
    if owner.position:
        keys += [f"{owner.position}님들", f"{owner.position}들"]
    # '팀장들과 공유' · '팀장님께 전달'처럼 나를 상대로만 부르는 말은 지목이 아니다('께서'는 주어라 지목)
    # '(이준호 팀장님 참조)'는 참고로 넣었다는 표시다 — 요청 대상이 아니다
    pos = rf"(?>(?:\s*{re.escape(owner.position)}님?)?)" if owner.position else ""  # 직급까지 붙여 읽고 되물리지 않는다
    return any(re.search(re.escape(k) + pos + r"(?!\s*(?:과|와|에게|한테|께(?!서)|참조))", text) for k in keys)


def role_pat(owner) -> re.Pattern | None:
    """'각 팀장은 · 전 팀장 · 팀장님들께서'처럼 내 직급을 무리로 부르는 말(v1.6, DE-9 ②). 상대로만 부르는 말은 지목이 아니다."""
    if not owner.position:
        return None
    p = re.escape(owner.position)
    return re.compile(rf"(?:(?:각|전|소속|모든|해당)\s*{p}(?:님)?|{p}님들|{p}들)(?!\s*(?:에게|께(?!서)|한테|과|와|의))")


def _external(req) -> bool:
    def dom(a: str) -> str:
        return a.rsplit("@", 1)[-1].strip("<> ").lower()
    return "@" in req.from_ and "@" in req.owner.email and dom(req.from_) != dom(req.owner.email)


def _fmt(text: str, attachments: list[str]) -> str | None:
    found = [f for f, pat in FORMATS if re.search(pat, text)]
    if not found and re.search(r"양식|첨부", text):
        found = sorted({a.rsplit(".", 1)[-1].lower() for a in attachments if "." in a})
    return "/".join(found) or None


def _task_text(clause: str) -> str:
    t = re.sub(r"^(?:\d\)|[-·•]|(?:\w+\s*)?(?:팀장|책임|선임|차장|부장|과장|대리)님[,.]?)\s*", "", clause)
    t = re.sub(r"\s*(?:부탁드(?:립니다|려요)|바랍니다|주십시오|주세요|주실\s*수\s*있을까요|주시면\s*감사하겠습니다)[.?!]*$", "", t)
    return t.strip()[:80]


DRAFT = re.compile(r"초안|개정안|변경안|계획서|제안서|보고서|가이드|장표|설계서|점검표")  # 문서를 보고 의견을 달라 → 검토(1팀 의견을 모아 달라는 회신과 구분)


SPECIFIC = re.compile(r"판단해\s*주|결정해\s*주|원본|재전송|재제출|다시\s*(?:보내|올려|제출)|(?:으로|로)\s*바꾼|와\s*주(?:세요|십시오)|모여\s*주|"
                      r"(?:이름|성함|연락처|가부)\S{0,2}\s*(?:만\s*)?(?:\S+\s+)?(?:보내|알려|회신|주시)")


def _type_of(text: str, subject: str, follow_up_reply: bool = False) -> tuple[str, bool]:
    """(유형, 약함). 문장의 유형 단어로 정하면 강하고, 제목 머리말 · 기본값으로 정하면 약하다(근거 없으면 기권하는 약한 지도 원리).
    follow_up_reply(v1.8): 'RE: [검토 요청] ~' 재요청은 원래 요청의 유형이다 → 제목 머리말을 먼저 보고 강하게 친다."""
    if follow_up_reply:
        for name, pat in SUBJECT_TYPE:
            if pat.search(subject):
                return name, False
    for i, (name, pat) in enumerate(TYPE_RULES):
        if pat.search(text) and (name != DEFAULT_TYPE or i < len(TYPE_RULES) - 1):  # 마지막 줄(기본 회신 단어)만 뒤로 미룬다
            if name == "자료제출요청" and RESEND_SUBJECT.search(subject):
                return "수정재전송요청", False
            return name, False
    if STRONG_REPLY.search(text):
        if "의견" in text and (DRAFT.search(text) or DRAFT.search(subject)):  # v1.8 '개정안 공유 · 의견을 받고 싶습니다' → 검토
            return "검토승인요청", False
        return DEFAULT_TYPE, False
    # 문장에 뚜렷한 유형 단어가 없으면 제목 머리말('[결재요청]' 등)을 따른다
    for name, pat in SUBJECT_TYPE:
        if pat.search(subject):
            return name, True
    return DEFAULT_TYPE, not TYPE_RULES[-1][1].search(text)


def event_due(req) -> DueParse | None:
    """회의 · 행사 시각. 본문 '일시:' 줄 → 제목+본문 순서로 찾는다."""
    when = MEETING_WHEN.search(req.body)
    text = when.group(1) if when else f"{req.subject} {' '.join(strip_body(req.body))}"
    return parse_due_plain(text, req.received_at)


def judge(req) -> RuleResult:
    owner, me = req.owner, req.owner.email.lower()
    to = [a.lower() for a in req.to]
    cc = [a.lower() for a in req.cc]
    recipient = "to" if me in to else "cc" if me in cc else "list"
    lines = strip_body(req.body)
    body = "\n".join(lines)
    subject = req.subject
    reasons: list[str] = []
    mentioned = _mentions_me(body, owner)
    is_reply = bool(REPLY_SUBJECT.match(subject))
    urgent = bool(URGENT.search(URGENT_APOLOGY.sub("", body))) or (not is_reply and bool(URGENT.search(subject)))  # 회신 제목의 [긴급]은 원 메일 것
    follow_up = bool(FOLLOW_UP.search(body))
    is_notice = recipient == "list" and bool(NOTICE_SUBJECT.search(subject) or NOTICE_BODY.search(body))
    # 회의 · 행사 초대: 제목 회의 단어, 또는 사내 단체 메일(공지 아님)의 '일시: · 장소:' 블록(DE-9 ⑤). 사외 행사 안내는 홍보다
    event_block = bool(MEETING_WHEN.search(req.body) and EVENT_BLOCK.search(req.body)) and not is_notice and not _external(req)
    is_meeting = (bool(MEETING.search(subject)) or event_block) and bool(HAS_TIME.search(subject + body)) and not is_reply
    role = role_pat(owner)

    # 1) 나를 향한 요청 문장 찾기
    sents = _sentences(lines)
    tasks: list[RuleTask] = []
    soft = False
    general_notice = False  # 대상이 '해당자 · 전 직원'인 당부가 있었다
    undirected = False  # 요청 문장은 있는데 나를 향했는지 못 정함 → '할 일 없음' 결론을 믿지 않는다
    prev_line = -1
    last_undirected = None  # (문장 번호, 문장) 바로 앞의 남을 향한 요청
    prev_named = (-9, False)  # (줄 번호, 그 문장이 나를 지목했나)
    named_task = False  # 직급 · 앞 문장 지목으로 나를 향한 요청을 찾았다 → 지목
    not_mine: list[str] = []
    optional: list[str] = []
    for n, (idx, s) in enumerate(sents):
        named = _mentions_me(s, owner) or bool(role and role.search(s))
        named_before = prev_named[1] and idx - prev_named[0] <= 1
        prev_named = (idx, named)
        if REQUEST.search(s) and OPTIONAL.search(s):
            optional.append(s)
        if not REQUEST.search(s) or NOT_TASK.search(s) or OPTIONAL.search(s) or (is_meeting and CONTINGENT.search(s)):
            continue
        general = recipient == "list" and bool(GENERAL_AUDIENCE.search(s))  # '미이수자는 · 해당자는 · 전 직원은' 당부
        # v1.6(DE-9 ② ④): '각 팀장은 ~' 직급 지목, 바로 앞 문장이 나를 대상으로 지목한 뒤의 요청('… 이준호 팀장님이 이번 대상입니다.
        # 가능하신 날을 회신 부탁드립니다')도 나를 향한 요청이다. 앞 문장이 남을 부른 요청이면 해당하지 않는다(그 문장은 named가 아님)
        directed = recipient == "to" or named or (named_before and not general) or (
            recipient == "list" and not is_notice and not general)
        named_task = named_task or named or (named_before and not general)
        if not directed and recipient == "list":
            # '아래 팀은 ... 제출 바랍니다' 다음 줄 목록에 내 팀이 있으면 나를 지목한 요청
            following = []
            for ln in lines[idx + 1:]:
                if not ln.startswith(("-", "·", "•")):
                    break
                following.append(ln)
            directed = _mentions_me(" ".join(following), owner)
        if not directed:
            # 단체 메일의 '미이수자는 · 해당자는 · 전 직원은' 당부는 할 일이 아니라 확인할 공지다(11/3 사용자 확인, 라벨 기준).
            # 제목 · 본문에 공지 표지가 없어도 공지로 본다. 엑사원도 여기서 할 일을 만들어(11/3 dev · dev2) 다시 묻지 않는다
            not_mine.append(s)
            if general:
                general_notice = True
                continue
            undirected = True
            last_undirected = (n, s)
            continue
        # '강 책임님, A를 이번 주 내로 회신 부탁드립니다. 이준호 팀장님께서도 한번 확인 부탁드립니다' → 나도 A를 같이 본다
        if ALSO_ME.search(s) and last_undirected and last_undirected[0] == n - 1:
            s = f"{last_undirected[1]} {s}"
        soft = soft or bool(SOFT.search(s))
        clauses = _clauses(s)
        new = []
        for c in clauses:
            prior = " ".join(x for _, x in sents[:n])  # '그 전에 · 마감 전까지'가 가리키는 앞 일시(v1.8)
            if new and not REQUEST.search(c):
                # v1.8 '판단해 주시고, 결론은 회의 때 얘기해 줘도 됩니다': 뒤 절은 요청이 아니라 앞 요청의 방법 · 기한이다
                new[-1].due = new[-1].due or parse_deadline(c, req.received_at, prior)
                continue
            t, weak = _type_of(c, subject, is_reply and follow_up)
            due = parse_deadline(c, req.received_at, prior) or (parse_deadline(s, req.received_at, prior) if len(clauses) == 1 else None)
            if due is None and new:
                due = new[-1].due  # '금요일까지 회신해 주시고, 안건도 함께 보내주세요' → 같은 기한
            if due is None and n + 1 < len(sents) and (not REQUEST.search(nxt := sents[n + 1][1]) or NOT_TASK.search(nxt)):
                # '... 주실 수 있을까요? 수요일 작업 전에 필요합니다.' · '... 요청드립니다. 수요일까지 어려우시면 말씀 부탁드립니다.'
                due = parse_deadline(nxt, req.received_at)
            if due is None and t == "일정참석":
                due = event_due(req)
            spec = bool(SPECIFIC.search(c)) or (is_reply and follow_up and any(p.search(subject) for _, p in SUBJECT_TYPE)) or (
                t == "검토승인요청" and "의견" in c and bool(DRAFT.search(c) or DRAFT.search(subject)))  # 원 요청 머리말 · 문서 + 의견
            new.append(RuleTask(_task_text(c), t, s, _fmt(c, req.attachments), due, weak, spec))
        # 대상 없는 '확인 부탁드립니다' 바로 뒤에 구체적인 요청이 오면 뒤 요청이 그 업무다(전달 · 캡처 메일)
        if tasks and len(new) == 1 and (idx - prev_line <= 1) and BARE_CHECK.match(tasks[-1].text):
            new[0].evidence = tasks[-1].evidence + " " + s
            tasks[-1] = new[0]
        # 같은 단락에서 이어지는 요청(같은 유형 · '특히 ~도')은 앞 업무에 합친다
        # 검토 요청 바로 뒤 '의견 주시면 반영하겠습니다'는 같은 검토의 회신 방법이다(DE-9 ①)
        elif tasks and len(new) == 1 and RESTATE.match(s):  # 떨어져 있어도 앞 요청을 다시 말한 것
            tasks[-1].due = tasks[-1].due or new[0].due
            tasks[-1].evidence += " " + s
        elif tasks and len(new) == 1 and (idx - prev_line <= 1) and not ENUM.match(s) and (
                ALSO_SAME.search(s) or
                CONTINUES.match(s) or new[0].action_type == tasks[-1].action_type
                or (tasks[-1].action_type == "검토승인요청" and new[0].action_type == DEFAULT_TYPE and "의견" in s)):
            tasks[-1].due = tasks[-1].due or new[0].due
            tasks[-1].evidence += " " + s
        else:
            tasks.extend(new)
        prev_line = idx

    if AUTO_REPLY.search(subject):  # v1.8 자동회신 · 부재중 알림의 '급한 건은 ~에게 연락 부탁드립니다'는 할 일이 아니다
        return RuleResult(["기타"], [], False, False, False, recipient, 0.9, ["자동회신"], optional, not_mine)

    # 2) 요청 문장이 없는 회의 초대 · 시간 변경: 회의 시각이 기한
    if not tasks and is_meeting:
        title = re.sub(r"^\s*\[[^\]]*\]\s*|\s*\([^)]*\)\s*$", "", subject).strip()
        task = RuleTask(f"{title} 참석", "일정참석", subject, None, event_due(req))
        return RuleResult(["일정참석"], [task], recipient == "to" or mentioned, urgent, follow_up, recipient, 0.85, ["회의 일정"])

    types = []
    for t in tasks:
        if t.action_type not in types:
            types.append(t.action_type)
    # 요청이 여럿이면 산출물이 있는 일을 주 유형으로, 단순 회신은 뒤로 (가장 중요한 것이 맨 앞)
    types.sort(key=lambda t: t == DEFAULT_TYPE)

    if tasks and is_meeting and MEETING_WHEN.search(req.body) and "일정참석" not in types and not any(t.weak_type for t in tasks):
        # v1.8: '일시:'가 있는 회의 초대에 '발표 자료는 ~까지 보내 주십시오'가 붙으면 회의 참석도 따로 할 일이다(사용자가 둘 다 한다)
        title = re.sub(r"^\s*\[[^\]]*\]\s*|\s*\([^)]*\)\s*$", "", subject).strip()
        tasks.insert(0, RuleTask(f"{title} 참석", "일정참석", subject, None, event_due(req)))
        types.insert(0, "일정참석")

    if tasks and is_meeting and all(t.weak_type for t in tasks):
        # 회의 초대에 붙은 '미리 훑어봐 주세요'처럼 유형 단어 없는 당부는 회의 준비다 → 회의 참석, 기한은 회의 일시
        for t in tasks:
            t.action_type, t.due = "일정참석", t.due or event_due(req)
        types = ["일정참석"]

    if tasks:
        mentioned = mentioned or recipient == "to" or named_task
        if is_notice:
            types = ["공지", *types]
        conf = 0.85
        for cond, c, why in ((soft, 0.6, "완곡 요청"), (len(tasks) > 1, 0.75, "요청 여러 개"), (recipient == "cc", 0.75, "참조 지목")):
            if cond:
                conf = min(conf, c)
                reasons.append(why)
        return RuleResult(types, tasks, mentioned, urgent, follow_up, recipient, conf, reasons, optional, not_mine)

    # 3) 할 일 없음. 누락이 가장 비싸므로(D15) 지목이 불확실한 요청 문장이 있으면 엑사원에게 다시 묻는다
    r = _no_task(recipient, mentioned, urgent, follow_up, is_reply, is_notice or general_notice, body, subject)
    r.not_mine, r.optional = not_mine, optional
    if undirected and r.confidence > 0.7:
        r.confidence = 0.7
        r.reasons.append("지목 불확실한 요청")
    elif general_notice and r.action_types == ["공지"] and r.confidence < 0.85:
        # 요청은 '미이수자는 · 해당자는' 당부뿐이고 내 직급은 안내 문장에만 나온다('팀장님들께서는 ~ 확인하실 수 있습니다').
        # 나에게 한 요청이 아니라 확인할 공지다 → 엑사원에 묻지 않는다(11/3 실측: 엑사원은 여기서 할 일 2개를 만들었다)
        r.confidence, r.mentioned_me = 0.85, False
        r.reasons.append("대상자 당부 공지")
    return r


def _no_task(recipient, mentioned, urgent, follow_up, is_reply, is_notice, body, subject) -> RuleResult:
    if recipient == "cc" and not mentioned:
        return RuleResult(["참조"], [], False, urgent, follow_up, recipient, 0.9, ["참조 수신"])
    if is_reply:
        conf = 0.85 if ANSWER.search(body) else 0.7
        return RuleResult(["회신"], [], False, urgent, follow_up, recipient, conf, ["내 요청에 대한 회신"])
    if recipient == "list":
        if MISC_SUBJECT.search(subject):
            return RuleResult(["기타"], [], False, urgent, follow_up, recipient, 0.85, ["뉴스레터 · 사내 소식"])
        if is_notice:
            return RuleResult(["공지"], [], mentioned, urgent, follow_up, recipient, 0.85 if not mentioned else 0.5, ["공지"])
        return RuleResult(["기타"], [], mentioned, urgent, follow_up, recipient, 0.6, ["단체 수신"])
    if recipient == "cc":
        return RuleResult(["참조"], [], True, urgent, follow_up, recipient, 0.5, ["참조인데 본문에서 지목"])
    # 나에게 직접 왔는데 요청 표현을 못 찾음 → 애매함, 엑사원으로
    if ANSWER.search(body) or re.search(r"공유(?:드립니다|합니다)", body):
        return RuleResult(["기타"], [], False, urgent, follow_up, recipient, 0.6, ["공유 · 회신성"])
    return RuleResult(["기타"], [], False, urgent, follow_up, recipient, 0.4, ["요청 표현 없음"])
