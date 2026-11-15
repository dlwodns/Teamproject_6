"""메일 조건 (AI-19 · AI-D15). 규칙은 글의 뜻을 해석하지 않고, 메일에 그대로 드러난 조건만 본다.

판단(할 일이 있나 · 무엇인가 · 어떤 유형인가 · 메일 성격)은 모델이 한다. 여기 있는 것은 모두 '있다 · 없다'로 답이 나는 조건이다.
- 수신 방식: 받는사람(to) · 참조(cc) · 배포 목록(list). 참조로 받은 메일의 '참조' 유형은 이 조건만으로 정한다
- 배포 목록 종류: 내 직책 목록(role) · 우리 팀 목록(team) · 그 밖(all). 직책 · 팀 목록으로 온 지시는 나에게 온 것이다(11/8)
- 나를 불렀나: 본문 · 제목에 내 이름 · '이 팀장' · 팀 이름 · 직책 무리, 또는 이름 없는 '팀장님'이 있나('참조로 넣었습니다'
  문장은 빼고). 참조로 받은 메일에 이것이 없으면 할 일을 만들지 않는다(11/8 사용자 결정: CC로 받은 다른 사람의 요청).
  개발 세트 7종의 참조 메일 46통(할 일 8 · 없음 38)에서 할 일 8통은 모두 부름, 없음 38통은 모두 안 부름
- 사내외: 보낸 사람 도메인이 메일함 주인과 다른가
- 자동 발송: 발신 전용 계정 · 수신 거부 · 자동 발송 표지 · 부재중 자동회신 제목
- 회신 제목: RE: · 회신:
- 긴급 · 재요청 단어(우선순위 칸)
- 할 일이 없다고 밝힌 문장: 조건 없이 '회신 · 참석 · 조치가 필요 없다'고 적은 문장. '이상 없으면 ~'처럼 조건이 붙은 문장은
  확인을 해야 하므로 여기에 들지 않는다(사용자 결정 11/7)
- 요청 어미: '부탁드립니다 · 주세요 · 바랍니다'로 끝나는 문장. 모델이 할 일을 비운 메일을 확인 칸에 표시할 때만 쓴다(할 일을 만들지 않는다)

규칙은 동결한다. 메일 한 통을 맞추려고 예외 · 단어를 더하지 않는다(AI-D15).
"""
import re
from dataclasses import dataclass, field

CONDITIONS_VERSION = "conditions_v1"

# backend/app/privacy/mask.py AUTO_LOCAL과 같은 패턴이다(가린 주소에서도 자동 발신이 그대로 보이게). 한쪽을 바꾸면 같이 바꾼다
AUTO_SENDER = re.compile(r"^(?:info|news|newsletter|noreply|no-?reply|donotreply|mailer|notice|alert|alerts|system|admin|marketing)\b", re.I)
AUTO_MARK = re.compile(r"수신\s*거부|수신을\s*원치|발신\s*전용|자동\s*발송|회신하실\s*수\s*없|unsubscribe", re.I)
AUTO_REPLY = re.compile(r"자동\s*회신|자동\s*응답|부재\s*중|Out\s*of\s*Office|Automatic\s*reply", re.I)
REPLY_SUBJECT = re.compile(r"^\s*(?:RE|Re|re|회신)\s*:")
# 긴급 · 재요청 단어는 규칙 v1.9 목록을 그대로 옮겼다(동결, 새 단어를 더하지 않는다)
URGENT = re.compile(r"긴급|급히|급하게|급함|시급|촉박|서둘러|ASAP|asap|즉시|최대한\s*빨리|가능한\s*(?:한\s*)?빨리|조속히")
URGENT_APOLOGY = re.compile(r"(?:급히|급하게)\s*(?:\S+\s*){0,2}?(?:죄송|양해|송구)")  # '급하게 변경드려 죄송합니다'는 사과다
FOLLOW_UP = re.compile(r"다시\s*(?:요청|연락|여쭙|여쭈|부탁|말씀드(?!리면))|재요청|아직\s*(?:도착|회신|받지|못|안\s*(?:왔|들어|오))|리마인드|재차|"
                       r"지난\S*\s*(?:\S+\s+)?(?:요청|부탁|말씀)드린\s*\S+\s*(?:건|진행|관련)")

# 할 일이 없다고 밝힌 문장. 무엇이 필요 없는지에 따라 그 유형의 할 일만 확인 칸으로 옮긴다(classify).
# 회신이 필요 없다는 말은 '확인'까지 없애지 않는다 — 확인 부탁은 검토 할 일이다(사용자 결정 11/7)
_NEED_NOT = r"\S{0,4}\s*(?:은|는|이|가|도)?\s*(?:따로\s*|별도로?\s*)?(?:주실\s*|하실\s*|드릴\s*)?(?:필요\s*(?:는|가|도)?\s*없|안\s*(?:하|주|오)셔도|(?:하|주|오)지\s*않으셔도|받지\s*않)"
NO_ACTION = {
    "회신요청": re.compile(rf"(?:회신|답장|답변|답신){_NEED_NOT}"),
    "일정참석": re.compile(rf"(?:참석|참여|참가){_NEED_NOT}|(?:오지|들어오지|오시지)\s*않으셔도"),
    "자료제출요청": re.compile(rf"(?:제출|보고|준비|작성){_NEED_NOT}"),  # '따로 자료는 준비하지 않으셔도 됩니다'는 참석까지 없애지 않는다
    "전부": re.compile(rf"조치{_NEED_NOT}|(?<![가-힣])하실\s*(?:일은?|것은?|건)\s*없|참고만\s*(?:하|해)|알고\s*(?:만\s*)?계시면\s*됩니다"),
}
# 조건이 붙은 문장: '~ 없으면 · 없는 경우 · 해당 사항이 없는 팀은'. 이런 문장은 확인을 해야 하므로 '필요 없다'로 보지 않는다
CONDITIONAL = re.compile(r"(?:없|않|있)으(?:시)?면|경우|이면|라면|시에는|(?:없|있)는\s*(?:팀|분|곳|부서)|해당\s*(?:사항|되지)")
REQUEST_END = re.compile(r"(?:부탁드(?:립니다|려요)|부탁합니다|주세요|주십시오|바랍니다|주실\s*수\s*있을까요|주시겠어요|주시면\s*감사하겠습니다)[.!?]?$")


@dataclass
class Conditions:
    recipient: str  # to | cc | list
    list_kind: str  # role | team | all (recipient가 list일 때만 뜻이 있다)
    mentioned: bool  # 나를 불렀나(참조로 받은 메일의 할 일 조건, called_me)
    sole_to: bool  # 받는사람이 나 한 명
    external: bool
    auto_sent: bool
    reply: bool
    urgent: bool
    follow_up: bool
    no_action: dict[str, str] = field(default_factory=dict)  # 유형(또는 '전부') → 할 일 없음을 밝힌 문장
    request_sentence: str | None = None  # 요청 어미로 끝나는 첫 문장


def strip_body(body: str) -> list[str]:
    """서명란 · 첫 줄 자기소개 · 맺음말을 빼고 본문 줄만 남긴다."""
    lines = [ln.strip() for ln in re.split(r"\n\*{5,}|\n-{5,}", body)[0].split("\n")]
    if lines and re.match(r"^안녕하세요.*입니다\.?$", lines[0]):
        lines = lines[1:]
    return [ln for ln in lines if not re.fullmatch(r"(감사합니다|고맙습니다|수고하세요)\.?", ln)]


def sentences(lines: list[str]) -> list[tuple[int, str]]:
    out = []
    for i, ln in enumerate(lines):
        for s in re.split(r"(?<=[.?!])\s+", ln):
            if s.strip():
                out.append((i, s.strip()))
    return out


def _domain(addr: str) -> str:
    return addr.rsplit("@", 1)[-1].strip("<> ").lower()


def external(req) -> bool:
    return "@" in req.from_ and "@" in req.owner.email and _domain(req.from_) != _domain(req.owner.email)


def recipient(req) -> str:
    me = req.owner.email.lower()
    return "to" if me in [a.lower() for a in req.to] else "cc" if me in [a.lower() for a in req.cc] else "list"


def mentions_me(text: str, owner) -> bool:
    """본문 · 제목에 내 이름 · '이 팀장' · 팀 이름 · 내 직책 무리가 있나. 규칙 v1.9 지목 글자 목록 + 성과 직책('이 팀장')."""
    keys = [k for k in (owner.name, owner.team) if k]
    if owner.team and (short := re.search(r"(\d+팀)$", owner.team)):  # 클라우드전환1팀 → '1팀에 ~'
        keys.append(short.group(1) + r"(?=은|는|도|에\s|에는|께서|\s*인원|\s*입장|\s*기준)")
    if owner.position:
        keys += [f"{owner.position}님들", f"{owner.position}들"]
    # '팀장님께 전달'처럼 나를 상대로만 부르는 말 · '(이준호 팀장님 참조)'는 지목이 아니다
    pos = rf"(?>(?:\s*{re.escape(owner.position)}님?)?)" if owner.position else ""
    if any(re.search((k if "(?=" in k else re.escape(k)) + pos + r"(?!\s*(?:과|와|에게|한테|께(?!서)|참조))", text) for k in keys):
        return True
    if owner.position:
        p = re.escape(owner.position)
        if owner.name and re.search(rf"(?<![가-힣]){re.escape(owner.name[0])}\s*{p}(?!\s*(?:과|와|에게|한테|께(?!서)|참조))", text):
            return True  # '이 팀장님께서도'
        return bool(re.search(rf"(?:(?:각|전|소속|모든|해당)\s*{p}(?:님)?|{p}님들|{p}들)(?!\s*(?:에게|께(?!서)|한테|과|와|의))", text))
    return False


CC_NOTE = re.compile(r"참조|참고")  # '이준호 팀장님도 참조로 넣었습니다 · 참고만 하시면 됩니다'는 나를 부른 문장이 아니다


def called_me(lines: list[str], owner) -> bool:
    """나를 불렀나(참조로 받은 메일의 조건). 내 이름 · '이 팀장' · 팀 이름 · 직책 무리, 또는 이름 없이 '팀장님'만 부른 문장.
    '참조 · 참고'를 말하는 문장은 빼고 본다. 이름 없는 '팀장님께서 정해 주셔야'는 나일 수 있어 부른 것으로 본다(누락 방지, D15)."""
    bare = re.compile(rf"(?<![가-힣] )(?<![가-힣]){re.escape(owner.position)}님(?!\s*(?:과|와|에게|한테|께(?!서)))") if owner.position else None
    for _, s in sentences(lines):
        if CC_NOTE.search(s):
            continue
        if mentions_me(s, owner) or (bare and bare.search(s)):
            return True
    return False


def list_kind(req) -> str:
    to = {a.lower() for a in req.to + req.cc}
    if to & {a.lower() for a in req.owner.role_lists}:
        return "role"
    if to & {a.lower() for a in req.owner.team_lists}:
        return "team"
    return "all"


def read(req) -> Conditions:
    lines = strip_body(req.body)
    body = "\n".join(lines)
    reply = bool(REPLY_SUBJECT.match(req.subject))
    no_action: dict[str, str] = {}
    first_request = None
    for _, s in sentences(lines):
        for clause in re.split(r",\s*", s):  # '이상 없으면 회신 안 하셔도 됩니다, 참석은 필요 없습니다'
            if CONDITIONAL.search(clause):
                continue
            for kind, pat in NO_ACTION.items():
                if pat.search(clause):
                    no_action.setdefault(kind, s)
        if first_request is None and REQUEST_END.search(s):
            first_request = s
    rcv = recipient(req)
    return Conditions(
        recipient=rcv,
        list_kind=list_kind(req),
        mentioned=called_me([req.subject, *lines], req.owner),
        sole_to=rcv == "to" and len(req.to) == 1,
        external=external(req),
        auto_sent=bool(AUTO_SENDER.match(req.from_.split("@")[0]) or AUTO_MARK.search(f"{req.subject} {req.body}")
                       or AUTO_REPLY.search(req.subject)),
        reply=reply,
        urgent=bool(URGENT.search(URGENT_APOLOGY.sub("", body))) or (not reply and bool(URGENT.search(req.subject))),  # 회신 제목의 [긴급]은 원 메일 것
        follow_up=bool(FOLLOW_UP.search(body)),
        no_action=no_action,
        request_sentence=first_request,
    )
