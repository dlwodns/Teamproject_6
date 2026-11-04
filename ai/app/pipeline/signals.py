"""메일 구조 신호 (유형 체계 kinds-v1, 2026-11-03). 메일 성격(kind)을 정할 때 쓰는 유형 무관 신호만 뽑는다.

원칙: 특정 메일 문구를 베낀 패턴을 두지 않는다. 범주 어휘(완료 · 첨부 · 회의 · 홍보 · 산출물 …)와
구조(수신 방식 · 사내외 · 역할 계정 · 회신 제목 · 제목 머리말 · 일시 줄 · 부름말)만 본다. kind 점수기(kinds.py)는
이 파일의 신호 이름만 쓰고, 신호 이름 목록은 SIGNALS 한 곳에 둔다(test_kinds가 확인한다).

할 일 탐지는 규칙 v1.5(`mail_rules_v1.judge`)를 그대로 쓴다. 여기서는 '나를 향한 요청 문장이 있나'를 judge보다 느슨하게
한 번 더 본다(request_loose) — judge가 못 찾은 완곡 요청을 엑사원에 다시 묻게 하는 근거다.
"""
import re
from dataclasses import dataclass, field

from app.pipeline.rules.mail_rules_v1 import (GENERAL_AUDIENCE, HAS_TIME, NOT_TASK, REPLY_SUBJECT, REQUEST, RuleResult,
                                              _mentions_me, _sentences, judge, strip_body)

# ---------- 범주 어휘 ----------
ROLE_LOCAL = re.compile(r"(?:^|[-_.])(?:info|news|newsletter|noreply|no-?reply|donotreply|seminar|event|events|marketing|"
                        r"notice|alert|alerts|monitor\w*|admin|webmaster|mailer)(?:$|[-_.])", re.I)
BULK_MARK = re.compile(r"수신\s*거부|수신을\s*원치|수신\s*동의|구독|발신\s*전용|자동\s*발송|회신하지\s*마|unsubscribe|본\s*메일은.{0,20}발송", re.I)
GREETING = re.compile(r"^\s*(?:안녕하세요|안녕하십니까)")
FORWARD = re.compile(r"^\s*(?:FW|Fw|Fwd|FWD)\s*:|\[전달\]")

TAG_CLASSES = {  # 제목 [머리말] 안 글자의 범주
    "tag_notice": re.compile(r"공지|안내"),
    "tag_request": re.compile(r"요청|문의|협의|협조|결재|승인|검토|취합|견적"),
    "tag_share": re.compile(r"공유|보고|제출|전달|배포"),
    "tag_minutes": re.compile(r"회의록"),
    "tag_meeting": re.compile(r"회의(?!록)|초대|미팅|일정\s*변경|간담회|리뷰"),
    "tag_promo": re.compile(r"초청|세미나|웨비나|포럼|뉴스레터|weekly|소식|동호회|복지|이벤트|광고|홍보|무료", re.I),
    "tag_alert": re.compile(r"모니터링|알림|경보|시스템"),
}
SUBJ_CLASSES = {  # 제목 전체(머리말 포함)의 범주
    "subj_request": re.compile(r"요청|부탁|문의|여부|의견|검토|결재|승인|품의|취합|제출"),
    "subj_notice": re.compile(r"안내|공지|예고|알림|배포"),
    "subj_done": re.compile(r"완료|확정"),
    "subj_change": re.compile(r"변경|앞당|당김|연기|조정"),
    "subj_resend": re.compile(r"수정|정정|원본|재전송|수정본|재송부|보완"),
    "subj_opinion": re.compile(r"의견(?!\s*드)|문의|여부|아이디어"),
    "subj_approve": re.compile(r"결재|승인|품의|상신|서명"),
    "subj_review": re.compile(r"검토(?!\s*(?:결과|의견))"),
    "subj_artifact": re.compile(r"자료|제출|취합|목록|명단|파일|보고서|현황표|스캔|양식|산정표|로그"),
}

# '결재해 주시면 정산됩니다 · 방향만 주시면 공유하겠습니다'처럼 조건으로 맺는 정중한 요청도 요청이다(주시면 + 아무 말)
REQUEST_SOFT = re.compile(r"주셨으면|가능할까요|괜찮을까요|될까요|주셔야\s*합니다|주시면|"
                          r"(?:할|하실)까요\s*[?？]")
VOCATIVE = re.compile(r"^((?:[가-힣]{2,4}\s+)?[가-힣]{1,5}님)\s*[,，]")  # 문장 머리 부름말 '강 책임님,' · '팀장님,'
CC_NOTE = re.compile(r"\(\s*[^)]*참조[^)]*\)|참조로\s*넣")

# 요청 대상(무엇을 해 달라는가) — 요청 문장에서만 본다
OBJ = {
    "obj_create": re.compile(r"작성|정리(?:해|한|하여|하신)|만들|채워|기재|적어|입력|산정|요약(?:해|한)"),
    "obj_artifact": re.compile(r"양식|자료|파일|문서|장표|PPT|pptx|엑셀|xlsx|PDF|pdf|워드|docx|CSV|csv|drawio|"
                               r"(?<![대발공목지])표(?:로|를|가|에|\s)|목록|명단|보고서|계획서|산정표|확인서|사유서|점검표|현황표|"
                               r"체크리스트|스캔|증빙|영수증|로그|서명본|날인본|압축|리포트|산출물|구성도|다이어그램|계획표|견적서|경위서|시트"),
    "obj_send": re.compile(r"보내|제출|전달|송부|공유(?:해|\s*부탁)|올려|내려받|첨부해|(?:파일|엑셀|PDF|워드|표)\s*(?:로|으로)\s*회신"),
    "obj_revise": re.compile(r"수정|정정|고쳐|고치|바로잡|보완|반영해|반영하여|넣어서|빼고|통일|옮겨|최신(?:으로|화)|변환|미뤄서"),
    "obj_again": re.compile(r"다시|재전송|재송부|재제출|재상신|수정본|원본"),
    "obj_review": re.compile(r"검토|봐\s*주|봐주|살펴|훑어|맞는지|보시고"),
    "obj_approve": re.compile(r"결재|승인|품의|상신|서명(?!본)|전결|날인(?!본|하신)"),
    "obj_opinion": re.compile(r"의견|아이디어|방향|판단|결정|어느\s*쪽|어떻게|이견"),
    "obj_whether": re.compile(r"여부|할지|가능할지|가능한지|있을지|괜찮을까요|될까요|가능할까요|할까요|하실까요"),
    "obj_info": re.compile(r"현황|명단|인원|담당|원인|진행\s*상황|대응|상황|참석자|성함|직급|사용자\s*수|사유|진행률|리스크|이슈"),
    "obj_schedule": re.compile(r"가능(?:하신|한)\s*(?:일자|날|날짜|시간|요일)|희망\s*(?:일자|날짜|일정)|(?:날짜|일자)\s*후보|"
                               r"선호(?:하시는|하는)?\s*(?:요일|날짜|일자|시간)|시간대"),
    "obj_attend": re.compile(r"참석(?!자)|참여|참가|출석"),
    "obj_reply_verb": re.compile(r"회신|알려|답(?:을|변)|말씀|여쭙"),
    "obj_message_form": re.compile(r"메일로|한\s*줄|간단히|형식은\s*자유|한두\s*줄|알려\s*주|말씀\s*주|답(?:을|변)?\s*주|방향만"),
    "wish_first_person": re.compile(r"싶(?:은데|습니다|어서)|개인\s*사정|(?:써도|해도|가도)\s*(?:될까요|괜찮을까요)|괜찮을까요"),
}
REF_PRIOR_MINE = re.compile(r"(?:보내|제출하|작성하|올려)\s*주신|보내주신|(?<![요])주신\s|제출하신|작성하신|공유해\s*주신|올려\s*준|"
                            r"(?:PDF|이미지|파일)로\s*(?:잘\s*)?받았")

MEETING_BLOCK = re.compile(r"(?m)^\s*(?:일시|장소|변경\s*후)\s*[:：]")
MEETING_WORD = re.compile(r"회의(?!록)|미팅|리뷰|보고회|워크숍|간담회|리허설|킥오프|설명회|면담|저녁\s*자리|모임")
CHANGE_WORD = re.compile(r"변경|앞당|당겨|연기|옮기|옮깁|바뀌|바뀝|조정")
INVITE_WORD = re.compile(r"초대|초청|엽니다|열립니다|진행합니다|하려고\s*합니다|잡으려고|모시")

DONE_WORD = re.compile(r"완료(?:되었|했|됐|하였)|마쳤|끝났|끝냈|반영(?:했|하였|되었|\s*끝)|처리(?:가\s*)?(?:되었|했)|"
                       r"통과했")
ANSWER_WORD = re.compile(r"(?:요청|문의|말씀|제안)(?:하신|해\s*주신|주신)|첨부(?:드립니다|했습니다|합니다)|보내\s*드립니다|"
                         r"다시\s*올립니다|가능합니다|진행할\s*예정")
ACK_WORD = re.compile(r"잘\s*받았습니다|확인했습니다|확인하였습니다|수신했습니다")
NO_REPLY = re.compile(r"회신(?:은|하지)?\s*(?:안|않)|따로\s*회신|안\s*주셔도|하지\s*않으셔도|"
                      r"(?:조치|신청|제출)(?:는|은|하지)?\s*(?:필요하지\s*않|필요\s*없|없습니다)|참고만|참고용|결정하실\s*사항은\s*없")
SHARE_WORD = re.compile(r"공유(?:드립니다|합니다|드려요)|배포합니다|보고(?:드립니다|합니다)|"
                        r"참고(?:용|만|하세요|하시면|해\s*주시고|\s*부탁|하시기)|전달드립니다|올려\s*두었습니다")
NOTICE_WORD = re.compile(r"안내(?:드립니다|합니다|드려요)|실시합니다|공지(?:드립니다|합니다)|진행됩니다|변경됩니다|바뀝니다|"
                         r"시행|예고|받습니다|권장|중단됩니다|열립니다")
OPT_IN = re.compile(r"(?:희망|원|관심|참여|참가|필요)(?:하시는|하실|하는|있으신|있는|하신)\s*(?:분|팀)|관심\s*있으시면|필요하시면")
MINUTES_WORD = re.compile(r"회의록|결정\s*사항|액션\s*아이템|참석자\s*[:：]|논의\s*내용")
PROMO_WORD = re.compile(r"초청|초대합니다|웨비나|세미나|포럼|컨퍼런스|사전\s*등록|등록(?:하실|해\s*주세요|하시면)|선착순|"
                        r"소개합니다|프로모션|할인|이벤트|무료|갱신|만료|견적이\s*필요하시면|연락\s*주세요|관심\s*있으시면")
NEWS_WORD = re.compile(r"뉴스레터|weekly|소식|동호회|산악회|복지몰|게시판", re.I)
ALERT_WORD = re.compile(r"자동\s*발송|발신\s*전용|임계치|초과(?:했|하였)|사용률|경보|감지")

# 신호 이름 → 뜻. kinds.KINDS의 형식 칸은 여기 있는 이름만 쓴다(앞에 '!'를 붙이면 '아님')
SIGNALS: dict[str, str] = {
    "to_me": "받는사람에 내가 있다", "cc_me": "참조로만 받았다", "list_me": "배포 목록(단체)으로 받았다",
    "external": "보낸 사람 도메인이 나와 다르다(사외)", "role_account": "보낸 주소가 역할 계정(info · news · noreply · seminar …)",
    "bulk_mark": "수신 거부 · 발신 전용 · 자동 발송 표시", "no_greeting": "본문이 인사말로 시작하지 않는다(대량 · 자동 메일 형식)",
    "reply": "회신 제목(RE:)", "forward": "전달 제목(FW: · [전달])", "has_attachment": "첨부가 있다",
    **{k: f"제목 머리말 범주 {k[4:]}" for k in TAG_CLASSES}, **{k: f"제목 범주 {k[5:]}" for k in SUBJ_CLASSES},
    "addressed_me": "본문 부름말이 나(내 직급 · 이름)", "addressed_other": "본문 부름말이 다른 사람", "cc_note": "'(○○님 참조)' 표시",
    "request_any": "요청 문장이 있다(누구에게든)", "request_loose": "나를 향한 요청 문장이 있다(느슨한 판정)",
    "rule_task": "규칙 v1.5가 나에게 온 할 일을 찾았다", "rule_tasks_2": "규칙 할 일이 2개 이상",
    "follow_up": "재요청 표현(다시 요청 · 아직 · 리마인드, 규칙 v1.5)",
    "mentions_me": "본문이 내 이름 · 팀 · 직급을 부른다", "role_mention_me": "'각 팀장 · 소속 팀장 · 팀장님들'처럼 내 직급을 역할로 지목",
    "list_mentions_me": "목록 줄(- · •)에 내 팀 · 이름이 있다",
    "general_audience": "해당자 · 미이수자 · 전 직원 같은 불특정 대상", "opt_in": "희망하는 분 · 필요하시면 같은 선택 참여",
    **{k: f"요청 대상 {k}" for k in OBJ}, "ref_prior_mine": "내가 앞서 보낸 것을 가리킨다(보내 주신 · 제출하신)",
    "meeting_block": "'일시: · 장소:' 줄", "meeting_word": "회의 · 미팅 · 리뷰 · 워크숍 등", "has_time": "시각 표현(14:00 · 10시)",
    "schedule_change": "일정 · 시간 · 장소 변경", "invite_word": "초대 · 엽니다 · 진행합니다",
    "done_word": "완료 · 마쳤 · 반영했 · 확정했", "answer_word": "요청하신 · 첨부드립니다 · 가능합니다", "ack_word": "잘 받았습니다 · 확인했습니다",
    "no_reply_needed": "회신 · 조치 불필요 · 참고만", "share_word": "공유드립니다 · 배포합니다 · 보고드립니다 · 참고용",
    "notice_word": "안내드립니다 · 실시합니다 · 변경됩니다", "minutes_word": "회의록 · 결정 사항 · 액션 아이템",
    "promo_word": "초청 · 웨비나 · 사전 등록 · 갱신 · 연락 주세요", "news_word": "뉴스레터 · 소식 · 동호회", "alert_word": "자동 발송 · 임계치 · 사용률",
}


@dataclass
class Signals:
    on: set[str]
    rule: RuleResult
    request_text: str = ""  # 나를 향한 요청 문장(없으면 요청 문장 전체)
    vocative: str | None = None
    evidence: dict[str, str] = field(default_factory=dict)  # 신호 → 걸린 글자(엑사원 신호 카드 · 디버깅용)

    def __contains__(self, name: str) -> bool:
        return name[1:] not in self.on if name.startswith("!") else name in self.on


def _domain(addr: str) -> str:
    return addr.rsplit("@", 1)[-1].strip("<> ").lower()


def _local(addr: str) -> str:
    return addr.rsplit("@", 1)[0].strip("<> ").lower()


def _is_me_vocative(voc: str, owner) -> bool:
    return bool((owner.name and owner.name in voc) or (owner.position and voc.replace(" ", "") == f"{owner.position}님"))


def _role_pat(owner) -> re.Pattern | None:
    if not owner.position:
        return None
    p = re.escape(owner.position)
    # '각 팀장은 · 소속 팀장님께서 · 팀장님들께서는'. '소속 팀장에게 공유'처럼 나를 상대로만 부르는 말은 지목이 아니다
    return re.compile(rf"(?:(?:각|전|소속|모든|해당)\s*{p}(?:님)?|{p}님들|{p}들)(?!\s*(?:에게|께(?!서)|한테|과|와|의))")


def extract(req, rule: RuleResult | None = None) -> Signals:
    owner, me = req.owner, req.owner.email.lower()
    rule = rule or judge(req)
    on: set[str] = set()
    ev: dict[str, str] = {}

    def hit(name: str, pat: re.Pattern, text: str):
        m = pat.search(text)
        if m:
            on.add(name)
            ev.setdefault(name, m.group(0))
        return bool(m)

    on.add({"to": "to_me", "cc": "cc_me", "list": "list_me"}[rule.recipient])
    if "@" in req.from_ and "@" in me and _domain(req.from_) != _domain(me):
        on.add("external")
    if ROLE_LOCAL.search(_local(req.from_)):
        on.add("role_account")
    hit("bulk_mark", BULK_MARK, req.body)
    if not GREETING.match(req.body):
        on.add("no_greeting")
    if REPLY_SUBJECT.match(req.subject):
        on.add("reply")
    if FORWARD.search(req.subject):
        on.add("forward")
    if req.attachments:
        on.add("has_attachment")
    tags = " ".join(re.findall(r"\[([^\]]+)\]", req.subject))
    for k, pat in TAG_CLASSES.items():
        hit(k, pat, tags)
    for k, pat in SUBJ_CLASSES.items():
        hit(k, pat, req.subject)

    lines = strip_body(req.body)
    body = "\n".join(lines)
    sents = [s for _, s in _sentences(lines)]
    voc = next((m.group(1) for s in sents if (m := VOCATIVE.match(s))), None)
    if voc:
        on.add("addressed_me" if _is_me_vocative(voc, owner) else "addressed_other")
    hit("cc_note", CC_NOTE, body)

    role = _role_pat(owner)
    mention = _mentions_me(body, owner)
    if mention:
        on.add("mentions_me")
    if role and hit("role_mention_me", role, body):
        on.add("mentions_me")
    bullets = " ".join(ln for ln in lines if ln.startswith(("-", "·", "•", "※")))
    if bullets and _mentions_me(bullets, owner):
        on.add("list_mentions_me")
    hit("general_audience", GENERAL_AUDIENCE, body)
    hit("opt_in", OPT_IN, body)

    # 요청 문장: 규칙 요청 표현 + 완곡 표현. 남을 부른 문장 · 불특정 대상 당부는 나를 향한 요청이 아니다
    reqs, mine = [], []
    other_turn, prev_named = False, False
    for s in sents:
        if (m := VOCATIVE.match(s)):
            other_turn = not _is_me_vocative(m.group(1), owner)
        named = _mentions_me(s, owner) or bool(role and role.search(s))
        is_req = bool((REQUEST.search(s) or REQUEST_SOFT.search(s)) and not NOT_TASK.search(s))
        if is_req:
            reqs.append(s)
            general = bool(GENERAL_AUDIENCE.search(s))
            # 바로 앞 문장이 나를 지목하고 이 문장이 그 요청이면('… 이준호 팀장님이 이번 대상입니다. 가능하신 날을 회신 부탁드립니다')
            if named or (not general and not other_turn and (rule.recipient == "to" or prev_named)):
                mine.append(s)
        prev_named = named
    if reqs:
        on.add("request_any")
    if mine or rule.tasks:
        on.add("request_loose")
    if rule.tasks:
        on.add("rule_task")
    if len(rule.tasks) > 1:
        on.add("rule_tasks_2")
    if rule.is_follow_up:
        on.add("follow_up")
    # 요청 대상은 나를 향한 요청 문장에서 본다. 요청 문장이 없으면(재요청 · 마감 변경처럼 대상이 앞 메일에 있음) 제목에서 본다
    # 요청이 여럿이면 규칙 주 유형(산출물 있는 일 우선, v1.5 관례)의 요청 문장을 본다
    main = next((t for t in rule.action_types if t != "공지"), None)
    task_text = " ".join(t.evidence for t in rule.tasks if t.action_type == main) or " ".join(t.evidence for t in rule.tasks)
    if task_text and len(rule.tasks) == 1:  # 할 일 하나: 그 문장 + 나를 향한 다른 요청 문장('쓰고 싶은데 괜찮을까요? … 답을 주시면')
        task_text = " ".join([task_text, *(x for x in mine if x not in task_text)])
    request_text = task_text or " ".join(mine) or " ".join(reqs) or REPLY_SUBJECT.sub("", req.subject)
    for k, pat in OBJ.items():
        hit(k, pat, request_text)
    hit("ref_prior_mine", REF_PRIOR_MINE, body)

    full = f"{req.subject}\n{body}"
    hit("meeting_block", MEETING_BLOCK, req.body)
    hit("meeting_word", MEETING_WORD, full)
    hit("has_time", HAS_TIME, full)
    if any(CHANGE_WORD.search(s) and (MEETING_WORD.search(s) or re.search(r"일정|시간|장소", s)) for s in [req.subject, *sents]):
        on.add("schedule_change")
    hit("invite_word", INVITE_WORD, full)
    hit("done_word", DONE_WORD, body)
    hit("answer_word", ANSWER_WORD, body)
    hit("ack_word", ACK_WORD, body)
    hit("no_reply_needed", NO_REPLY, body)
    hit("share_word", SHARE_WORD, body)
    hit("notice_word", NOTICE_WORD, body)
    hit("minutes_word", MINUTES_WORD, full)
    hit("promo_word", PROMO_WORD, full)
    hit("news_word", NEWS_WORD, full)
    hit("alert_word", ALERT_WORD, full)
    return Signals(on, rule, request_text, voc, ev)
