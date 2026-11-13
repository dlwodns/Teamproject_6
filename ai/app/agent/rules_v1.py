"""명령 해석 규칙 v1 (AI-11, AI detail 4.2절). 행동 1개가 정확히 걸리면 확정, 0개 · 2개 이상이면 엑사원으로 넘긴다.

모델은 메일 본문을 보지 않는다. 날짜 표현은 분류 후처리와 같은 코드로 환산한다(app.pipeline.dates).

v1.4 (11/3): 상태 변경 행동(MUTATING)은 문장의 주된 지시일 때만 후보로 둔다. 부정('~하지 마') · 의문('~맞아?' · '어떻게 ~해?') ·
과거 서술('~했었는데') · 관형절('완료 처리한 거') 안의 행동 낱말과 메일이 아닌 대상('회의 미뤄줘')은 후보에서 지운다(analyze).
대상 · 값이 빠진 지시('빼줘' · '알림 바꿔줘')와 가리킬 메일이 없는 지시어('이거' · '그거')는 실행하지 않고 되묻는다(slots_ok).

v1.5 (11/10, AI-20 · D50): T15 일정_등록. '회의 · 미팅 잡아줘' · '캘린더에 넣어줘'를 잡고 시작 · 끝 시각 · 제목을 뽑는다(event_params).
CNE 앱 캘린더에만 넣는다(Outlook 쓰기 없음). 시각 글자가 없으면('내일 회의 잡아줘' · '오전에') 지어내지 않고 되묻는다.
backend가 T15를 허용 목록에 넣기 전에는 이전처럼 지원 외(NOT_MAIL_TASK)다. 초안(T07 · T12)과 한 문장에 함께 시키면
행동 하나만 실행하지 않도록 되묻는다(plan, COMPOUND_WITH).
"""
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from app.pipeline.dates import (RELATIVE_WHEN, _DATE_PATTERNS, _RANGE, _TIME, _find_time, parse_date_range, parse_due, parse_due_plain,
                                parse_event_at, parse_event_end)
from app.schemas.agent import DateRange, Target

RULES_VERSION = "agent_rules_v1.5"

# ── v1.4 글자 정리: 한글 수사 → 숫자. 날짜 · 시각 코드와 아래 정규식은 숫자만 읽는다('열 시 반' · '이틀 뒤' · '일주일 넘게' · '그 두 건')
_NATIVE = {"열한": 11, "열두": 12, "열": 10, "한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9}
_NATIVE_UNIT = re.compile(r"(?<![가-힣])(열한|열두|열|한|두|세|네|다섯|여섯|일곱|여덟|아홉)\s*"
                          r"(시간|시(?![작장청])|건|개(?!월)|통(?!화)|번(?!역|호)|주(?![문소간말])|달(?!력))")
_DAYS = {"하루": 1, "이틀": 2, "사흘": 3, "나흘": 4, "닷새": 5, "엿새": 6, "이레": 7, "열흘": 10, "보름": 15, "일주일": 7, "1주일": 7}
# '하루 요약'은 그대로 둔다 — 기간 뒤에 오는 말(넘게 · 뒤 · 째 …)이 있을 때만 바꾼다
_DAY_WORD = re.compile(r"(?<![가-힣\d])(하루|이틀|사흘|나흘|닷새|엿새|이레|열흘|보름|일주일|1주일)"
                       r"(?=\s*(?:이상|넘|뒤|후|째|지난|동안|정도|만에|전|이내|안에|있다가|지나))")
_SINO_MIN = {"오": 5, "십": 10, "십오": 15, "이십": 20, "삼십": 30, "사십": 40, "사십오": 45, "오십": 50}
_SINO_MIN_RE = re.compile(r"(?<![가-힣])(사십오|십오|이십|삼십|사십|오십|십|오)\s*분")


def normalize(text: str) -> str:
    text = _DAY_WORD.sub(lambda m: f"{_DAYS[m[1]]}일", text)
    text = _NATIVE_UNIT.sub(lambda m: f"{_NATIVE[m[1]]}{m[2]}", text)
    return _SINO_MIN_RE.sub(lambda m: f"{_SINO_MIN[m[1]]}분", text)


# v1.2: 흔한 바꿔 말하기를 더 잡고(아래 '# v1.2' 표시), 지원 외 · 애매 일부를 모델 없이 판정한다(AI-1 응답 시간).
# v1.4: 낱말 묶음을 넓혔다(아래 '# v1.4' 표시). 정규식은 normalize · 따옴표 가림을 거친 글자에 건다.
PATTERNS: dict[str, re.Pattern] = {
    # v1.4 '정리'만으로는 요약이 아니다('오늘 거 정리해줘'는 되묻기) · 금일 · 투데이 추가
    "T01": re.compile(r"(?:오늘|금일|투데이|today|내일).*(?:뭐\s*(?:해야|있)|할\s*(?:일|거|것)|해야\s*할|요약|정리해서\s*(?:보여|알려))"
                      r"|하루\s*요약|브리핑", re.I),
    # v1.4 '메일 중요'를 '메일 중'으로 잘못 읽지 않는다 · 띄워 · 뽑아 · 명사로 끝나는 조회('미처리 메일')
    "T02": re.compile(r"(?:미처리|안\s*한|못\s*한|못\s*끝낸|안\s*끝난|안\s*끝낸|남은|남아\s*있는|밀린|처리\s*안\s*된|대기\s*중|아직\s*안)"
                      r".*(?:보여|알려|뭐|있어|찾아|목록|띄워|뽑아|추려|리스트|남았|있나)"
                      r"|(?:메일|건)\s*중(?:에|에서)?(?=\s|$)|(?:보여|찾아|띄워|뽑아)\s*(?:줘|주세요|줘요|줄래|봐)?\s*[.!~?]*$|목록\s*(?:좀)?\s*$"
                      r"|(?:미처리|남은|밀린)\s*(?:메일|건|업무|일|거|것)(?:들)?\s*(?:만|은|는|좀)?\s*\??\s*$"),
    "T03": re.compile(r"(?:처리|완료|끝|마무리|해결)\s*(?:했|됐|냈|함|했어|했음|완료)|(?:끝냈|마쳤|끝났|다\s*했)|완료\s*(?:해|처리|로|표시|체크|상태로)"
                      r"|^\s*(?:이거|이것|그거|요거|이건)\s*(?:는|은)?\s*(?:다\s*)?완료"
                      r"|(?:끝난|처리한|완료한|처리된|완료된|한)\s*(?:걸로|것으로|거로)\s*(?:해|표시|바꿔|처리)"  # v1.4
                      r"|(?:회신|답장|답)\s*(?:은|도|을|를)?\s*(?:다\s*|전부\s*|모두\s*)?보냈"  # v1.2 '회신은 다 보냈어'
                      r"|(?:회신|답장|답변)\s*(?:은|도|을|를)?\s*(?:다\s*|전부\s*|모두\s*)?했"),  # v1.4 '이 메일 답장했어'
    # v1.4 undo · 없던 걸로 · '방금 거 돌려놔'
    "T04": re.compile(r"취소|되돌려|되돌리|원래대로|원상\s*복구|복구|복원|undo|언두|없던\s*(?:걸로|일로)"
                      r"|(?:원래|이전|직전|방금|아까)\s*(?:\S+\s*){0,2}?돌려\s*(?:놔|놓|줘|둬)", re.I),
    # v1.4 다시 띄워 · 보여 · 스누즈 · 미룰래 · 보류 · '~로 넘겨'
    "T05": re.compile(r"다시\s*(?:알려|띄워|보여|올려)|나중에|이따가?(?:\s|$)|미뤄|미루|미룰|연기\s*(?:해|시켜|좀)|리마인드\s*(?:해|좀|걸어|부탁|설정|$)"
                      r"|리마인더\s*(?:해|걸어|맞춰)|알림\s*(?:줘|해\s*줘|걸어)|스누즈|snooze|보류|(?:로|으로)\s*넘겨"
                      r"|(?:에|때)\s*(?:다시\s*)?알려\s*(?:줘|주세요|줄래)", re.I),  # v1.4 '금요일에 알려줘'(날짜가 있어야 남는다)
    "T06": re.compile(r"(?:답장|회신|답변|답|응답)\s*(?:이)?\s*(?:안\s*(?:온|왔|오|준)|없는|없어|못\s*받)|무응답|(?:답|회신|답장)\s*(?:을|를)?\s*기다리는"),
    # v1.4 드래프트 · 리플라이 · '답장 ~ 초안'이 떨어져 있어도 · '답장해줘'
    "T07": re.compile(r"(?:회신|답장|답변|리플라이|reply)\s*(?:은|을|를|용|할\s*말)?\s*(?:초안|문안|문구|드래프트|draft)"
                      r"|(?:답장|회신|답변|답|리플라이)\s*(?:좀\s*)?(?:써|작성|만들|잡아)|(?:답장|회신|리플라이)\s*(?:좀\s*)?해\s*(?:줘|주세요|줄래)"
                      r"|(?:회신|답장|답변|리플라이|reply).{0,20}(?:초안|드래프트|draft)\s*(?:좀\s*)?(?:부탁|써|작성|만들|잡아)", re.I),
    # v1.4 '왜'가 메일 상태 · 분류를 묻는 경우를 넓혔다 · '어떤 근거로' · '이유로'
    "T08": re.compile(r"(?:왜|어째서)\s*.*(?:미처리|중요|업무|떴|떠|들어|할\s*일|잡혔|잡혀|분류|올라|나와|나오|돼|됐|되어|제외|빠졌|빠져|검토|공지|요청|회신|기타"
                      r"|기한|마감|임박|우선|이야|야\??\s*$)|(?:이유|근거)\s*(?:가|를|좀|는)?\s*(?:뭐|알려|설명|보여)|(?:어떤|무슨)\s*(?:이유|근거)|근거로|이유로"
                      r"|(?:뭐|뭣)\s*때문에"),
    # v1.4 '기한 5시간 전에 알려주게 바꿔' · 변경 · 조정 · 맞춰
    "T09": re.compile(r"(?:아침\s*알림|리마인드|리마인더|알림|브리핑)\s*.*(?:바꿔|변경|설정|조정|맞춰|으로\s*해|로\s*해)|매일\s*.*\d+\s*시.*(?:알려|알림|보내)"
                      r"|(?:알림|브리핑|리마인드|리마인더)\s*(?:시간|시각)|(?:기한|마감)\s*\d+\s*(?:시간|일)\s*전.*(?:바꿔|변경|설정|조정|맞춰|로\s*해|으로\s*해|알림)"
                      r"|알려\s*주(?:게|도록)\s*(?:바꿔|변경|설정|해)"
                      r"|(?:알림|리마인드|리마인더|브리핑)\S*\s*(?:\S+\s*)?\d+\s*시(?:\s*\d+\s*분|\s*반)?\s*(?:으로|로)\s*[.!~]*$"),  # v1.4 '아침 알림 7시로'
    "T10": re.compile(r"빼\s*(?:줘|주세요|줘요|줄|주실|놔|버려|$)|빼$|제외\s*(?:해|시켜|처리|좀|$)?|업무\s*아니|할\s*일\s*아니|처리\s*대상\s*아(?:님|니)"
                      r"|숨겨|숨기|안\s*보이게|무시해"),
    # v1.4 우선 · 상단 · VIP. '중요한 분이야'처럼 서술만 한 문장은 잡지 않는다(지시형 '중요로 · 중요하게'만)
    "T11": re.compile(r"(?:항상|늘|앞으로|무조건|계속|언제나).{0,15}(?:중요(?:로|하게|\s*표시|\s*처리|\s*메일로)|우선(?:으로|순위로|적으로)?\s*(?:올려|표시|해|보여|처리)"
                      r"|상단(?:에|으로)|위로\s*올려|먼저\s*보이게|VIP)|중요\s*발신자|VIP\s*(?:로|등록|지정)|중요로\s*(?:해|지정|표시|등록|설정)"
                      r"|즐겨찾기\s*(?:해|추가|등록)"),
    # v1.4 '메일 하나 써줘' · draft · 받는 사람 없는 새 메일('고객사에 감사 인사 메일 작성해줘')
    "T12": re.compile(r"(?:한테|에게|께)\s*.*(?:메일|초안|드래프트|draft)\s*(?:좀\s*|하나\s*|1통\s*)?(?:써|작성|만들|잡아|부탁)"
                      r"|(?:메일|초안|드래프트|draft)\s*(?:좀\s*|하나\s*|하나만\s*|1통\s*)?(?:써|작성|만들|잡아|부탁)"
                      r"|(?:메일|초안).*(?:한테|에게|께)\s*(?:좀\s*)?(?:써|작성)", re.I),
    "T13": re.compile(r"(?:기한|마감|데드라인).*(?:보여|언제|알려|몰린|봐\s*줘|확인|띄워|목록|있어|뭐)|캘린더|달력"
                      r"|(?:기한|마감|데드라인)(?:들|일)?\s*(?:은|는|만|좀)?\s*\??\s*$"),
    # v1.4 재촉 · 독촉은 보내는 동사가 있어야 한다('재촉 메일은 보내지 마'의 남은 '재촉 메일'을 잡지 않게) · '재촉해줘' · 리마인드 메일
    "T14": re.compile(r"(?:재촉|독촉|팔로우\s*업|follow\s*up|리마인드\s*메일|리마인더\s*메일|(?:다시|1번\s*더)\s*요청)\s*(?:메일|문자|연락)?\s*(?:을|를|좀|도)?\s*"
                      r"(?:\S+\s*){0,2}?(?:보내|발송|전송|쏴|날려|넣어|드려)|(?:재촉|독촉|(?:다시|1번\s*더)\s*요청)\s*(?:좀\s*)?(?:해|하자)"
                      r"|템플릿\s*(?:으로|을|를)?\s*(?:\S+\s*){0,3}?(?:보내|발송|전송|쏴|날려|회신|답장)", re.I),
    # v1.5 일정 등록(D50). '일정 잡는 메일'처럼 꾸미는 말은 잡지 않는다 — 시키는 꼴(잡아 · 등록해 · 넣어 …)만
    "T15": re.compile(r"(?:캘린더|달력|일정표|스케줄러?|일정)\s*(?:에|으로|로)\s*(?:\S+\s*){0,4}?"
                      r"(?:등록|추가|넣어|넣어\s*줘|저장|잡아|만들어|올려)"
                      r"|(?:회의|미팅|일정|약속|면담|통화|세미나|워크숍|워크샵|리뷰|발표|교육|모임|점검|면접|인터뷰|간담회|설명회|킥오프)\s*(?:을|를|도|하나|1개)?\s*(?:좀\s*)?(?:새로\s*)?"
                      r"(?:잡아|등록\s*(?:해|좀|$)|추가\s*(?:해|좀|$)|만들어|넣어|생성\s*(?:해|$))"),
}

# 행동 목록에 없는 메일 조작은 모델에 묻지 않고 지원 외로 막는다. 모델은 가장 가까운 T10(제외)을 골랐다(AI-T6).
# 규칙이 행동을 하나도 못 찾았을 때만 본다 — '김 팀장께 전달할 메일 써줘'는 T12가 먼저 걸린다
UNSUPPORTED = re.compile(r"삭제|지워|지우|휴지통|전달\s*해|(?:발송|보낸\s*메일)\s*(?:을|를)?\s*취소|포워드|포워딩|스팸\s*(?:신고|등록|처리)|차단|수신\s*거부"
                         r"|구독\s*(?:취소|해지)|첨부.*(?:다운|저장|열어)|인쇄|번역|읽음\s*(?:으로|표시|처리)|폴더.*(?:옮|이동)"
                         # v1.4 보낸 메일 회수 · 재촉 메일 취소, 보관 · 별표 · 라벨 · 출력
                         r"|보낸\s*(?:\S+\s*){0,2}?메일\s*(?:을|를)?\s*(?:발송\s*)?취소|(?:재촉|독촉|템플릿)\s*메일\s*(?:을|를)?\s*(?:발송\s*)?취소"
                         r"|회수|보관|아카이브|archive|별표|플래그|라벨|태그|출력", re.I)
# v1.4 메일이 아닌 대상을 만들거나 바꾸는 요청 — 캘린더 일정 등록, 앱 · 계정 설정. 초안(T07 · T12)이 걸리면 메일 주제일 수 있어 보지 않는다
NOT_MAIL_TASK = re.compile(r"(?:캘린더|달력|일정표|스케줄러?)\s*(?:에|으로|로)\s*(?:\S+\s*){0,3}?(?:등록|추가|넣어|저장|만들|잡아)"
                           r"|(?:일정|회의|미팅|약속)\s*(?:을|를)?\s*(?:새로\s*)?(?:등록|추가|생성|만들어|잡아)"
                           r"|(?:서명|비밀번호|암호|테마|다크\s*모드|글자\s*크기|폰트|언어|소리|진동|벨소리|음량|배경|프로필|자동\s*응답|자동응답|부재\s*중|자동\s*회신|푸시)"
                           r"\s*(?:을|를|은|는|도|이|가)?\s*(?:좀\s*)?(?:\S+\s*)?(?:바꿔|바꾸|변경|설정|켜|꺼|추가|등록|로\s*해|으로\s*해)")
# 메일 업무와 무관한 요청. 메일 업무 낱말이 하나도 없을 때만 지원 외로 판정한다(MAIL_WORDS)
OFF_TOPIC = re.compile(r"날씨|주식|시세|환율|점심|저녁\s*메뉴|메뉴\s*추천|맛집|노래|음악|농담|게임|운세|퀴즈"
                       r"|영화|드라마|스포츠|축구|야구|여행지|항공권|택시|배달|레시피|요리|운동|산책|청소|빨래|설거지|로또|뉴스(?!레터)")  # v1.4
MAIL_WORDS = re.compile(r"메일|회신|답장|답변|건|기한|마감|알림|초안|발신|수신|보낸|받은|업무|할\s*일|처리|완료|템플릿|일정")
# 무엇을 할지 말하지 않은 지시('알아서 해' · '손 좀 봐줘' · '정리 좀'). 행동이 하나도 안 걸렸을 때만 되묻기로 보낸다
VAGUE = re.compile(r"알아서|어떻게\s*(?:좀\s*)?해|손\s*(?:좀\s*)?(?:봐|보)|(?:정리|처리|챙겨|해결|확인|체크)\s*(?:좀|해\s*줘|해\s*봐|해\s*주세요|해$|부탁)|좀\s*봐\s*줘"
                   # v1.4 '그거 해줘' · '싹 다 해줘' — 지시어 · 수량어 뒤에 일반 동사 '해'만 있다
                   r"|(?:^|\s)(?:그거|이거|저거|그것|이것|그걸|이걸|다|싹|전부|모두|빨리|얼른|일단|그냥)\s*(?:좀\s*)?(?:다\s*)?해\s*(?:줘|주세요|줘요|봐|라)?\s*[.!~]*$")
# '취소'가 되돌리기가 아니라 메일 속 일정 · 구독을 가리키는 경우('회의 취소 메일 써줘' · '구독 취소해줘')
NOT_UNDO = re.compile(r"(?:구독|수신|회의|미팅|일정|약속|예약|주문|결제|신청|출장|발송|보낸\s*메일|참석|등록|가입|티켓|항공|숙소|호텔|택시|휴가|면접)\s*(?:을|를|은|는)?\s*취소"
                      r"|취소\s*(?:메일|공지|안내|요청|건|관련|문의|소식|됐다는|되었다는)")  # v1.4 '취소 안내 메일'은 메일 주제다
# v1.3 '완료 처리하지 마' · '빼지 말고' — 부정 · 금지 지시. v1.4: 모델 경로 안전장치(non_command)에서만 쓴다. 규칙 경로는 NEG_PRED · PROHIBIT_END로 범위를 나눠 본다
NEGATION = re.compile(r"(?:하|빼|보내|미루|취소하|바꾸)지\s*(?:마|말)|\s말고\b|그만\s*(?:해|둬)|안\s*해도\s*(?:돼|된다)")
# 메일 · 설정 상태를 바꾸거나 밖으로 보내는 행동. 부정 · 지원 외 낱말과 함께 걸리면 실행하지 않는다(D37 확인 정책 앞단)
MUTATING = {"T03", "T04", "T05", "T09", "T10", "T11", "T14", "T15"}  # v1.5 T15: 앱 캘린더에 일정을 만든다(되돌리기 가능)

# T05는 '날짜 + 다시 알려/나중에'가 함께 있어야 한다(아래 analyze에서 확인)
NEEDS_DATE = {"T05"}
NO_DATE_OK = re.compile(r"나중에|미뤄|미루|미룰|연기|보류|이따|스누즈|snooze|넘겨", re.I)  # 날짜 없이도 '미루기'가 분명한 낱말

# 충돌 규칙 (AI detail 4.1): 앞 행동이 걸리면 뒤 행동 후보를 지운다
BEATS = {
    "T01": {"T02"},  # v1.4 '오늘 할 일 보여줘'
    "T04": {"T03", "T05", "T10", "T14", "T09", "T11"},  # '완료 취소' · '방금 거 취소'
    "T03": {"T07", "T02", "T06", "T01"},  # 과거형 완료 우선 — '회신 다 했어'
    "T14": {"T06", "T12", "T07", "T05", "T02"},  # '답장 안 온 거 재촉 메일 보내줘'
    "T05": {"T13", "T02", "T01"},  # v1.4 T05 · T09는 서로 지우지 않고 analyze에서 가른다(RULE_SETTING)
    "T09": {"T13", "T01"},  # v1.4 '기한 5시간 전에 알려주게 바꿔' — 기한 보기가 아니라 설정이다
    "T07": {"T12", "T02"},
    "T12": {"T02"},
    "T13": {"T02", "T01"},
    "T06": {"T02", "T01"},
    "T11": {"T10", "T02"},
    "T08": {"T02", "T13", "T01"},  # v1.4 '이 메일 기한이 왜 금요일이야'
    "T15": {"T13", "T02", "T01"},  # v1.5 '캘린더에 넣어줘'는 기한 보기(캘린더 화면)가 아니라 등록이다
}
OPT_IN = {"T15"}  # v1.5 backend가 허용 목록에 넣었을 때만 규칙 후보가 되는 새 행동(analyze)
COMPOUND_WITH = {"T07", "T12"}  # v1.5 '회신 초안 쓰고 회의 잡아줘' — 두 행동을 한 번에 시킨 문장. 하나만 실행하지 않고 되묻는다

TITLES = r"팀장|책임|선임|차장|부장|과장|대리|사원|사업단장|담당|상무|전무|이사|매니저|프로"
SENDER = re.compile(rf"([가-힣]{{1,4}})\s?({TITLES})\s?님?")
CATEGORY = re.compile(r"(회신|요청|검토|공지|기타)\s*(?:메일|건|업무)|(회신|요청|검토|공지)\s*(?:은|는|도|들은?)?\s*(?:다|전부|모두|싹)(?:\s|$)")
# v1.4 지시어를 둘로 나눴다. 이 · 이거 · 선택한 → 지금 고른 메일, 그 N건 · 아까 · 방금 목록 → 직전 결과(없으면 고른 메일)
# '이 팀장님'은 성(이)이라 지시어가 아니다
SELECT_REF = re.compile(rf"(?<![가-힣])(?:이거|이것|이건|이걸|이게|요거|요것|요건|얘(?!기))|선택한|선택된|고른|체크한"  # '보이게'의 '이게'는 지시어가 아니다
                        rf"|(?:^|\s)이\s+(?!(?:{TITLES})(?:님)?(?:\s|$|[이가은는을를께한에]))(?=[가-힣\d])|(?:^|\s)저\s+(?:메일|건|거|것|뉴스레터|광고|공지)|(?<![가-힣])(?:저거|저것)")
LAST_REF_MANY = re.compile(r"그\s*\d+\s*(?:건|개|통)|(?:그|저)\s*(?:메일|것|거|건)들|(?<![가-힣])(?:그것들|그거들|걔네|걔들)|(?:방금|아까)\s*(?:목록|나온|본|뜬|보여\s*준|조회한|찾은)"
                           r"|(?:위|이전|직전)\s*목록|목록에\s*(?:있는|나온|뜬)|(?:그|위)\s*중(?:에|에서)?(?:\s|$)|거기\s*(?:있는|나온)")
LAST_REF_ONE = re.compile(r"(?<![가-힣])(?:그거|그것|그건|그걸|그게|걔(?![네들]))|(?:^|\s)그\s+(?:메일|건|거|것|사람|분|뉴스레터|광고|공지)|아까\s*그|위에\s*(?:거|것)")
KEYWORD = re.compile(r"([가-힣A-Za-z0-9]{2,})\s*(?:건(?:은|는|을|를|도|이|만)?|관련(?:해서|된|한|으로|하여)?)(?:\s|$)")  # v1.4 '계약서 관련해서'
NOT_KEYWORD = {"이번", "다음", "오늘", "내일", "방금", "모든", "전체", "남은", "그", "이", "공지", "회신", "요청", "검토", "기타",
               "어제", "아까", "메일", "업무", "처리", "완료", "미처리", "선택한"}
NUDGE = re.compile(r"재촉|독촉|다시\s*요청|팔로우\s*업|follow\s*up|리마인드\s*메일|리마인더\s*메일|1번\s*더\s*요청", re.I)
TEMPLATE_NAME = re.compile(r"['\"‘“]([^'\"’”]+)['\"’”]")
MORNING_DEFAULT = time(8, 30)  # 리마인드 기본 시각 (기획 detail 4.2, 문규남 11-02)

# ── v1.4 문장 구조: 행동 낱말이 주된 지시인지 본다 ──────────────────────────────────────────────
# 받침 ㅆ 음절(했 · 됐 · 냈 · 봤 …) = 과거. '있' · '겠'은 과거가 아니다. 받침 ㄴ 음절(한 · 된 · 낸 · 온 …) = 관형형
_PAST = "".join(chr(c) for c in range(0xAC00, 0xD7A4) if (c - 0xAC00) % 28 == 20 and chr(c) not in "있겠")
_JONG_N = "".join(chr(c) for c in range(0xAC00, 0xD7A4) if (c - 0xAC00) % 28 == 4)
_QUOTE = re.compile(r"['\"‘“][^'\"’”]*['\"’”]")  # 따옴표 안은 템플릿 이름 · 주제(데이터)다 — "'처리 완료했습니다' 템플릿"
_ACT_NOUN = r"(?:완료|처리|제외|연기|취소|등록|지정|설정|변경|전송|발송|재촉|독촉|표시|요청|답장|회신)"
# 문장 안의 부정 서술어 — 서술어 낱말만 가린다(목적어는 뒤 지시와 같이 쓸 수 있다: '보고서 건은 미루지 말고 오늘 완료 처리해')
NEG_PRED = re.compile(rf"(?:{_ACT_NOUN}\s*)?\S*지\s*(?:는|도|를)?\s*(?:말고|말구|마|말아|말자|마세요|마요|마라|않고|않아도)\S*"
                      rf"|(?:{_ACT_NOUN}\s*)?\S*면\s*안\s*(?:되|돼|됨|된)\S*|(?:{_ACT_NOUN}\s*){{0,2}}안\s*\S*도\s*(?:돼|되|됨|된다|괜찮)\S*"
                      r"|\S+\s*(?:필요\s*(?:는|가)?\s*없)\S*|그만\s*\S*")
# 문장 끝 서술어가 금지 · 불필요 · 그대로 두라는 말이면 상태 변경 지시가 아니다
PROHIBIT_END = re.compile(r"(?:지\s*(?:는|도|를)?\s*(?:마|말아|말라|말자|마세요|마요|마라|맙시다|말아\s*(?:줘|주세요|요))|면\s*안\s*(?:돼|된다|됩니다|되|됨|돼요|되지)"
                          r"|안\s*\S*도\s*(?:돼|된다|됩니다|되|됨|돼요|괜찮아)|지\s*않아도\s*(?:돼|된다|됩니다|되|됨|괜찮아)|필요\s*(?:는|가)?\s*없\S*"
                          r"|그만\s*(?:\S+\s*)?(?:해|둬|해요|하세요|보내|하자)?|(?:그냥|그대로)\s*(?:둬|놔\s*둬|놔둬|냅둬|놔|두세요|놔두세요|둬요))\s*[.!~ㅎㅋ]*$")
# 'X 말고 Y' · 'X 빼고 Y' — X는 거르는 조건이다. 절 처음부터 표지까지 가린다('오늘 요약 말고 이번 주 기한 보여줘')
CONTRAST = re.compile(r"(\S+)\s*(?:말고|말구|빼고|제외하고|대신)(?=\s|$)")
# 과거 서술 — 대과거 · 전해 들은 말 · 경험 · 과거 + 이음 어미. 이 절 안의 행동 낱말은 지시가 아니다('완료했다고 표시해줘'는 지시라서 뺀다)
PAST_NARR = re.compile(rf"\S*(?:[{_PAST}]었|[{_PAST}](?:대|댔|다고(?!\s*(?:표시|체크|기록|바꿔|해\s*줘|해줘|처리|해$))|다는|다던|단다|다네|답니다|대요)|[{_PAST}](?:는데|던데|더니|지만|으니까|으니|고서|는지|던)"
                       rf"|[{_JONG_N}]\s*적\s*(?:이|은|도)?\s*(?:있|없))\S*")
# 관형절('완료 처리한 거' · '제외된 메일' · '재촉 메일 보낸 사람') — 꾸미는 말이라 지시가 아니다
ADNOMINAL = re.compile(rf"\S*(?:[{_JONG_N}]|는|던)(?=\s*(?:거|것|건|메일|애들?|사람|분|분들|목록|내역|이력|리스트|방법|법|기능|뜻)(?:들)?(?:\s|$|[은는이가을를도만에]))")
_PARTICLE_END = re.compile(r"(?:은|는|을|를|이|가|에|에서|로|으로|한테|에게|께|도|만|하고|랑)$")
# 의문: 부탁형('~줄래?' · '~줄 수 있어?')은 지시다. 그 밖의 물음은 상태를 바꾸지 않는다
REQUEST_FORM = re.compile(r"줘|줄래|줄\s*수|주실|주시|주세요|주라|주겠|줄까|할까|할래|하자|부탁|해\s*봐")
WH = re.compile(r"뭐|무엇|무슨|뭔|어떻게|어떤|어디|어느|언제|왜|누가|누구|몇")
YN_END = re.compile(rf"(?:맞아|맞나|맞지|맞죠|맞니|맞냐|맞나요|맞아요|맞는지|맞음|인가|인가요|인지|건가|건가요|건지|나요|니|냐|는지|던가|더라|[{_PAST}]나|[{_PAST}]니"
                    rf"|뭐야|뭐지|뭔데|뭐예요|뭐에요|(?:있|맞|거|건|[{_PAST}])(?:지|죠))$")  # v1.4 '설정돼 있지' · '다 했지' — 확인하는 물음
RULE_SETTING = re.compile(r"매일|매번|항상|기본\s*(?:알림|시간)|(?:기한|마감)\s*\d+\s*(?:시간|일)\s*전|(?:알림|브리핑|리마인드|리마인더)\s*(?:시간|시각|주기)")
HESITATE = re.compile(r"(?:할까|볼까|낼까|뺄까|미룰까)\s*말까|할지\s*말지|고민\s*(?:중|이야|돼|되네)|(?:만약|만일)\s.*면(?:\s|$)")
IMPERATIVE_END = re.compile(r"(?:줘|줘요|주세요|주라|해|해요|해라|하세요|하자|봐|봐요|놔|둬|자|라|세요|게|래|쏴|빼|보내|바꿔|올려|띄워|알려|부탁|할게)$")
# 사용법 · 뜻을 묻는 말 — 어떤 행동도 실행하지 않는다('회신 초안은 어떻게 쓰는 거야?' · '일괄 완료가 뭐야?' · '스누즈가 뭐야')
HOWTO = re.compile(r"(?:어떻게|어케|어디서|어디에서|어디로|어디에)\s*(?:\S+\s+){0,3}?\S*(?:는\s*(?:거|건|지|법|방법)|나요|하나|해야|하면\s*(?:돼|되|됨)|해요\s*\?|해\s*\?"
                   r"|써\s*\?|써요\s*\?|보내\s*\?|쓰니|하니|하지\s*\?)"
                   r"|(?:하는|쓰는|보내는|빼는|바꾸는|미루는|설정하는|등록하는|지정하는|취소하는|되돌리는)\s*(?:법|방법)"
                   r"|(?:이란|란|이라는\s*(?:게|건|거)|라는\s*(?:게|건|거))\s*(?:뭐|무엇|무슨|어떤)|(?:뭐|무슨)\s*(?:뜻|의미)|(?:무슨|어떤)\s*기능"
                   r"|(?:완료|처리|취소|제외|초안|설정|지정|전송|발송|재촉|독촉|스누즈|리마인드|리마인더|템플릿|발신자|무응답|되돌리기|기능|버튼|모드)"
                   r"\s*(?:이|가|은|는|란|이란)\s*(?:뭐|무엇)(?:야|예요|에요|지|냐|니|임|죠|인가|\s*\?|$)")
# 메일이 아닌 대상(회의 · 일정 · 약속 …)에 붙은 행동 낱말 — '회의 다음 주로 미뤄줘' · '회의 끝났어'. '회의 취소 메일'처럼 메일 낱말이 끼면 보지 않는다
_EVENT = (r"(?<![가-힣])(?:회의|미팅|일정|약속|예약|출장|휴가|연차|반차|식사|점심|저녁|회식|운동|면접|발표|수업|강의|교육|행사|통화|세미나|워크숍)"
          r"(?:을|를|은|는|도|이|가|에서)?(?=\s|$)")
_GAP = r"\s*(?:(?!\S*(?:메일|건|관련|공지|답장|회신|초안))\S+\s+){0,2}?"
NON_MAIL = {
    "T03": re.compile(rf"{_EVENT}{_GAP}(?:좀\s*|다\s*|전부\s*)?(?:끝|마쳤|마치|다\s*했|완료|처리\s*했|갔다\s*왔|다녀왔)"),
    "T05": re.compile(rf"{_EVENT}{_GAP}(?:좀\s*)?(?:미뤄|미루|미룰|연기|옮겨|다시\s*알려|리마인드|리마인더|나중에|보류|넘겨|스누즈)"),
    "T10": re.compile(rf"{_EVENT}{_GAP}(?:좀\s*)?(?:빼|제외|숨겨|숨기)"),
    "T09": re.compile(r"(?:회의|미팅|일정|약속|캘린더|휴대폰|폰|앱|푸시)\s*알림"),
}
# 행동이 하나도 안 걸린 말 조각('김 팀장 건' · '아까 그거' · '완료') — 서술어 어미로 끝나지 않으면 되묻는다
_PRED_END = set("다요죠지까니냐래게자네어아야해줘봐와워둬놔셈음함됨임듯데나고라군걸쇼여렴든면려대삼당서오소세며유용염"
                "내꺼켜써펴쳐껴져뤄겨꿔춰쏴돼빼")  # 줄여 쓴 반말 명령(보내 · 꺼 · 바꿔 · 미뤄 · 옮겨)
# 대상이 있는지 — 메일 · 업무 낱말이나 '~은/는/을/를'이 붙은 명사(목적어 · 주제)
OBJ = re.compile(r"메일|(?<![가-힣])건(?:들)?(?:은|는|을|를|도|만|이)?(?![가-힣])|업무|할\s*일|공지|회신|요청|검토|기타|답장|답변|뉴스레터|광고|스팸|프로모션|홍보"
                 r"|안내|초대|청구|견적|보고|계약|자료|문서|발주|목록|리스트|(?<![가-힣])(?:거|것)(?:들)?(?:은|는|을|를|도|만)?(?![가-힣])")
_OBJ_TOPIC = re.compile(r"([가-힣A-Za-z0-9]{2,})(?:은|는|을|를|도|만)(?=\s|$)")
NOT_OBJ = {"앞으로", "오늘", "내일", "이번", "다음", "지금", "나중", "아까", "방금", "일단", "그냥", "정말", "진짜", "이제", "요즘", "항상",
           "우선", "먼저", "제발", "이따", "모레", "어제", "평소", "이거", "그거", "저거", "이건", "그건"}
QUANTIFIER = re.compile(r"(?:^|\s)(?:다|싹|전부|모두|몽땅|싹다)(?:\s|$)")


@dataclass
class Analysis:
    hits: list[str]
    dropped: dict[str, str] = field(default_factory=dict)  # 지운 행동 → 사유(negation · question · howto · past(과거 서술 · 관형절) · non_mail · no_date)
    reason: str | None = None  # 후보가 다 지워졌을 때 규칙이 바로 정한 사유(없으면 모델이 판단)


def _blank(text: str, spans) -> str:
    chars = list(text)
    for s, e in spans:
        for i in range(s, e):
            chars[i] = " "
    return "".join(chars)


def _clause_start(text: str, pos: int) -> int:
    cut = max(text.rfind(c, 0, pos) for c in ",.!?;")
    return cut + 1


def _rel_start(text: str, start: int) -> int:
    """관형절 시작: 앞쪽 낱말을 두 개까지 붙이되 조사로 끝나거나 서술어로 끝나는 낱말에서 멈춘다."""
    words = [(m.start(), m[0]) for m in re.finditer(r"\S+", text[:start])]
    begin = start
    for s, w in reversed(words[-2:]):
        if _PARTICLE_END.search(w) or re.search(rf"[{_PAST}]|(?:어|요|다|음|고|서)$", w) or re.search(r"[,.!?]$", w):
            break
        begin = s
    return begin


def views(text: str) -> tuple[str, str]:
    """(q, m): q는 따옴표 · 'X 말고' · 부정 서술어를 가린 글자(모든 행동), m은 q에서 과거 서술 · 관형절까지 가린 글자(상태 변경 행동)."""
    t = normalize(text)
    q = _blank(t, [m.span() for m in _QUOTE.finditer(t)])
    spans = []
    for m in CONTRAST.finditer(q):
        if m[1].endswith("지"):  # '빼지 말고'는 부정 서술어(NEG_PRED)다
            continue
        spans.append((_clause_start(q, m.start()), m.end()))
    q = _blank(q, spans + [m.span() for m in NEG_PRED.finditer(q)])
    spans = [(_clause_start(q, m.start()), m.end()) for m in PAST_NARR.finditer(q)]
    spans += [(_rel_start(q, m.start()), m.end()) for m in ADNOMINAL.finditer(q)]
    return q, _blank(q, spans)


def _last_clause(text: str) -> str:
    t = text.strip()
    cuts = list(re.finditer(r"[,.!?;]+(?=\s*\S)", t))
    return t[cuts[-1].end():].strip() if cuts else t


def _final_word(clause: str) -> str:
    words = re.sub(r"[\s.!?~…ㅎㅋㅠㅜ^;:)(]+$", "", clause).split()
    return words[-1] if words else ""


def info_question(text: str) -> bool:
    """마지막 절이 정보를 묻는 말인가('~맞아?' · '~했나' · '언제 ~돼 있어'). 부탁형 물음('~줄래?')은 지시라서 아니다."""
    last = _last_clause(text)
    if REQUEST_FORM.search(last):
        return False
    fw = _final_word(last)
    return "?" in last or bool(YN_END.search(fw)) or (bool(WH.search(last)) and not IMPERATIVE_END.search(fw))


def _past_final(text: str) -> bool:
    fw = _final_word(_last_clause(text))
    return bool(re.search(f"[{_PAST}]", fw)) and not IMPERATIVE_END.search(fw)


def _neg_done(text: str) -> bool:
    """'아직 안 끝났어' · '다 못 끝냈어' · '처리 안 됐어' — 완료를 부정한 보고."""
    words = _last_clause(text).split()
    if not words or not re.search(f"[{_PAST}]", words[-1]):
        return False
    return bool(re.match(r"(?:안|못)\s*(?:했|됐|끝|마쳤|보냈|냈)", words[-1])) or (len(words) >= 2 and words[-2] in ("안", "못"))  # '안내했어'는 아니다


def analyze(text: str, now: datetime, allowed: set[str] | None = None) -> Analysis:
    """allowed: backend 허용 목록. v1.5에 새로 넣은 행동(OPT_IN, 지금은 T15)은 허용됐을 때만 후보에 넣는다 — 허용 전에는
    충돌 규칙(BEATS)으로 T13 · T02 · T01을 지우지 않아 v1.4와 결과가 같다. 기존 행동(T01~T14)은 이전처럼 걸린 뒤 plan이 거른다
    ('재촉 메일 보내줘'에서 T14가 허용되지 않았다고 T06 조회로 바꿔 실행하지 않는다)."""
    t = normalize(text)
    plain = _blank(t, [m.span() for m in _QUOTE.finditer(t)])
    q, m = views(text)
    raw = [aid for aid, pat in PATTERNS.items()
           if not (aid in OPT_IN and allowed is not None and aid not in allowed) and pat.search(plain)]
    hits = [aid for aid in raw if PATTERNS[aid].search(m if aid in MUTATING else q)]
    dropped: dict[str, str] = {}
    for aid in raw:
        if aid not in hits:
            dropped[aid] = "negation" if not PATTERNS[aid].search(q) else "past"  # 부정 서술어 · 'X 말고' 안 / 과거 서술 · 관형절 안

    def drop(aids, why):
        for aid in [h for h in hits if h in aids]:
            hits.remove(aid)
            dropped[aid] = why

    if HOWTO.search(q):  # 사용법 · 뜻 질문은 조회도 실행하지 않는다
        drop(set(PATTERNS), "howto")
    if PROHIBIT_END.search(q.rstrip()) or PROHIBIT_END.search(t.rstrip()):  # 금지로 끝나는 문장은 초안 · 조회도 시키는 말이 아니다
        drop(set(PATTERNS), "negation")
    if info_question(q):
        drop(MUTATING, "question")
    if HESITATE.search(q):  # v1.4 '완료할까 말까' · '만약 답장 안 오면 ~' — 정하지 않은 말 · 조건은 지금 실행할 지시가 아니다
        drop(MUTATING, "question")
    if _past_final(q):  # '재촉 메일 보냈어' · '알림 9시로 설정했어'는 한 일을 말한 것이다. 완료(T03)만 과거형이 지시다
        drop(MUTATING - {"T03"}, "past")
    if _neg_done(q):
        drop({"T03"}, "negation")
    for aid, pat in NON_MAIL.items():
        if aid in hits and pat.search(q):
            drop({aid}, "non_mail")
    if "T04" in hits and NOT_UNDO.search(q) and not re.search(r"되돌|원래대로|원상\s*복구|방금|아까", q):
        drop({"T04"}, "non_mail")
    if "T05" in hits and not (remind_at(q, now) or NO_DATE_OK.search(q)):
        drop({"T05"}, "no_date")
    if {"T05", "T09"} <= set(hits):  # v1.4 '매일 · 기한 N시간 전 · 알림 시간'은 설정(T09), 그 밖의 날짜 + 알려줘는 이 메일 미루기(T05)
        hits.remove("T05" if RULE_SETTING.search(q) else "T09")
    for winner in list(hits):
        for loser in BEATS.get(winner, ()):
            if loser in hits and winner in hits:
                hits.remove(loser)

    reason = None
    if not hits and dropped:
        whys = set(dropped.values())
        if "howto" in whys or ("negation" in whys and (PROHIBIT_END.search(q.rstrip()) or PROHIBIT_END.search(t.rstrip()))):
            reason = "unsupported"  # 지시가 아닌 말 — 금지 · 사용법 질문
        elif whys == {"no_date"}:
            reason = "ambiguous"  # '다시 알려줘' — 언제인지 되묻는다
    return Analysis(hits=hits, dropped=dropped, reason=reason)


def match(text: str, now: datetime) -> list[str]:
    return analyze(text, now).hits


def mail_refs(text: str, ctx) -> tuple[list[str], bool]:
    """(가리킨 메일 ID, 지시어가 있었나). v1.4: '이 · 이거'는 고른 메일, '그 N건 · 방금 목록'은 직전 결과, '그거'는 고른 메일 → 직전 결과 순."""
    if SELECT_REF.search(text):
        return list(ctx.selected_mail_ids), True
    if LAST_REF_MANY.search(text):
        return list(ctx.last_result_ids or ctx.selected_mail_ids), True
    if LAST_REF_ONE.search(text):
        return list(ctx.selected_mail_ids or ctx.last_result_ids), True
    return [], False


def extract_target(text: str, ctx) -> Target:
    t = Target()
    q, _ = views(text)  # v1.4 따옴표 · 'X 말고'로 거른 부분은 대상에서 뺀다
    m = SENDER.search(q)
    if m:
        t.sender = f"{m[1]} {m[2]}"
    m = CATEGORY.search(q)
    if m:
        t.category = m[1] or m[2]
    rng = parse_date_range(q, ctx.now)
    if rng:
        t.date_range = DateRange(start=rng[0], end=rng[1])
    t.mail_ids, _ = mail_refs(q, ctx)
    for m in KEYWORD.finditer(q):
        word = m[1]
        if word not in NOT_KEYWORD and not word.isdigit() and not re.search(rf"(?:{TITLES})님?$", word):
            t.keyword = word
            break
    return t


def _alarm_time(text: str) -> time | None:
    """v1.4 알림 시각은 업무 마감 규칙('3시까지' → 15시)을 쓰지 않는다. '7시 반'은 07:30, 오후 · 저녁 · 밤이 있을 때만 12시간을 더한다."""
    m = re.search(r"(오전|오후|아침|저녁|밤|새벽)?\s*(\d{1,2})\s*(?:시(?!간)\s*(?:(\d{1,2})\s*분|(반))?|:(\d{2}))", text)
    if not m:
        return None
    h, mi = int(m[2]), int(m[3] or m[5] or (30 if m[4] else 0))
    if h > 24 or mi > 59:
        return None
    if m[1] in ("오후", "저녁", "밤") and h < 12:
        h += 12
    return time(h % 24, mi)


def _relative_due(text: str, now: datetime) -> datetime | None:
    """v1.4 'N분 · N시간 · N일 · N주 · N달 뒤' (dates 코드에 없는 상대 시점)."""
    m = re.search(r"(\d+)\s*(분|시간|일|주|달|개월)\s*(반\s*)?(?:뒤|후|있다가|지나서)", text)
    if not m:
        return None
    n, unit = int(m[1]), m[2]
    if unit in ("분", "시간"):
        minutes = n if unit == "분" else n * 60 + (30 if m[3] else 0)
        return (now + timedelta(minutes=minutes)).replace(second=0, microsecond=0)
    if unit in ("달", "개월"):
        y, mo = divmod(now.month - 1 + n, 12)
        d = now.date().replace(year=now.year + y, month=mo + 1, day=min(now.day, 28))
    else:
        d = now.date() + timedelta(days=n * (7 if unit == "주" else 1))
    clock = _find_time(text) or MORNING_DEFAULT
    return datetime.combine(d, clock)


def _week_or_month(text: str, now: datetime) -> datetime | None:
    """v1.4 요일 없는 '다음 주에' → 다음 주 월요일, '다음 달에' → 다음 달 1일, '주말에' → 이번 토요일 (아침 알림 시각)."""
    b = now.date()
    if re.search(r"다음\s*주(?!\s*(?:[월화수목금토일]요일|초|중|말))|차주(?!\s*[월화수목금토일])", text):
        d = b - timedelta(days=b.weekday()) + timedelta(days=7)
    elif re.search(r"다음\s*달|내달", text):
        d = date(b.year + (b.month == 12), b.month % 12 + 1, 1)
    elif re.search(r"주말", text):
        d = b + timedelta(days=(5 - b.weekday()) % 7 or 7)
    else:
        return None
    return datetime.combine(d, MORNING_DEFAULT)


def remind_at(text: str, now: datetime) -> datetime | None:
    """T05 다시 알릴 시각. 시각 낱말이 하나도 없으면 아침 알림 시각(08:30), '오후 · 저녁'처럼 때를 말했으면 dates 규칙을 따른다."""
    rel = _relative_due(text, now)
    if rel:
        return rel
    due = parse_due(text, now)
    if due is None:
        clock = _find_time(text)
        if clock and not _week_or_month(text, now):  # v1.4 '오후 3시에 다시 알려줘' — 날짜 없이 시각만: 오늘, 지났으면 내일
            at = datetime.combine(now.date(), clock)
            return at if at > now else at + timedelta(days=1)
        return _week_or_month(text, now)
    at = due.due_at
    if _find_time(text) is None and not re.search(r"오전|오후|점심|정오|저녁|밤|퇴근", text):  # v1.4 '내일 오후에'를 08:30으로 당기지 않는다
        at = at.replace(hour=MORNING_DEFAULT.hour, minute=MORNING_DEFAULT.minute)
    return at


def extract_params(action: str, text: str, ctx, target: Target) -> dict:
    now = ctx.now
    raw = text
    text, _ = views(text)
    if action == "T01":
        return {"date": (now.date() + timedelta(days=1 if "내일" in text else 0)).isoformat()}
    if action == "T05":
        until = remind_at(text, now)
        return {"until": until.isoformat() if until else None}
    if action == "T06":
        m = re.search(r"(\d+)\s*(일|주)\s*(?:이상|넘|지난|째|동안)", text)  # v1.4 '일주일 넘게' · '사흘째'
        return {"min_days": int(m[1]) * (7 if m[2] == "주" else 1) if m else 3}
    if action == "T09":
        m = re.search(r"(\d+)\s*(시간|일)\s*전", text)  # v1.4 '기한 하루 전' → 24시간
        if m:
            return {"rule": "before_due", "hours": int(m[1]) * (24 if m[2] == "일" else 1)}
        t = _alarm_time(text)
        return {"rule": "morning", "time": t.strftime("%H:%M") if t else None}
    if action == "T11":
        return {"level": "superior" if re.search(r"상급자|윗분|상사", text) else "favorite"}
    if action == "T14":
        nudge = bool(NUDGE.search(text))
        name = TEMPLATE_NAME.search(raw)
        if nudge and not target.mail_ids and not mail_refs(text, ctx)[1]:
            target.awaiting_reply = True  # '재촉 메일 보내줘' → 직전 무응답 목록(3일 이상). v1.4 '그 사람한테'처럼 못 푼 지시어가 있으면 전체로 넓히지 않는다
        return {"template_kind": "nudge" if nudge else "send", "template_name": name[1] if name else None}
    if action == "T07":
        tone = "short" if re.search(r"짧게|간단", text) else "polite"
        return {"tone": tone}
    if action == "T15":
        # 대상은 고른 메일뿐이다. 이름 · 날짜는 일정 내용이지 메일을 찾는 조건이 아니다
        target.sender, target.category, target.keyword, target.date_range = None, None, None, None
        return event_params(text, now)
    if action == "T12":
        m = re.search(r"(?:한테|에게|께)\s*(.+?)\s*(?:관련|에\s*대한)?\s*(?:메일|초안|드래프트|draft)", text)
        if not m:  # v1.4 받는 사람 없이 주제만 있는 새 메일
            m = re.search(r"^\s*(.*?\S)\s*(?:관련|에\s*대한)?\s*(?:메일|초안|드래프트|draft)", text)
        return {"topic": m[1].strip() if m and m[1].strip() else None}
    return {}


# ── v1.5 T15 일정 등록 값 ─────────────────────────────────────────────────────────────────────────
_CAL_WORD = re.compile(r"(?:내\s*)?(?:캘린더|달력|일정표|스케줄러?)\s*(?:에|으로|로)?")
_EVENT_VERB = re.compile(r"\s*(?:을|를|도)?\s*(?:일정\s*(?:으로|로)\s*)?(?:좀\s*)?(?:새로\s*)?(?:잡아|등록|추가|넣어|저장|만들어|생성|올려)\S*(?:\s+\S+)?\s*[.!~?]*$")
_TIME_WORD = re.compile(r"(?:오전|오후|아침|저녁|밤|점심)(?:\s*에)?")


_REF_WORD = re.compile(r"^(?:이|그|저|이거|그거|저거|이번|해당|선택한|고른)\s+")
_GENERIC_TITLE = {"회의", "미팅", "일정", "약속", "회의 일정", "미팅 일정"}


def event_title(text: str) -> str | None:
    """일정 제목: 날짜 · 시각 · '캘린더에' · 시키는 말을 걷어 낸 나머지('내일 3시 김 팀장님이랑 예산 회의 잡아줘' → '김 팀장님이랑 예산 회의').
    남는 말이 없거나 고른 메일을 가리키는 말('이 회의')뿐이면 None — backend가 고른 메일 제목이나 '일정'으로 둔다."""
    t = _EVENT_VERB.sub("", text.strip())
    for pat in [_RANGE, RELATIVE_WHEN, *[p for _, p in _DATE_PATTERNS], _TIME, _TIME_WORD, _CAL_WORD]:
        t = pat.sub(" ", t)
    t = re.sub(r"(?<![가-힣])(?:에|에서|으로|로|부터|까지)(?![가-힣])", " ", t)  # 걷어 낸 날짜 · 시각 뒤에 남은 조사
    t = re.sub(r"\s+", " ", t).strip(" ,.~")
    pointed = bool(_REF_WORD.match(t))
    t = _REF_WORD.sub("", t)
    if not t or t == "일정" or (pointed and t in _GENERIC_TITLE):
        return None
    return t[:40]


def event_params(text: str, now: datetime) -> dict:
    """T15 params: start · end(시간대 없는 KST) · title. 날짜 · 시각은 메일 회의 시각과 같은 코드(dates.parse_event_at · parse_event_end)로 읽는다.
    시각 글자가 없거나('내일 회의' · '오전에') 날짜로 못 읽는 상대 시점('3일 뒤')이면 start는 null이다(slots_ok가 되묻는다).
    날짜 없이 시각만 있으면 오늘, 지났으면 내일(T05 '오후 3시에 다시 알려줘'와 같다)."""
    due = parse_event_at(text, now, roll_forward=True)
    start = due.due_at if due is not None and due.time_stated else None
    end = parse_event_end(text, start)
    return {"start": start.isoformat() if start else None, "end": end.isoformat() if end else None, "title": event_title(text)}


def guard(text: str, hits: list[str]) -> str | None:
    """규칙이 행동을 잡았어도 실행하면 안 되는 문장. 사유를 돌려준다(없으면 None).
    v1.3: 잡힌 행동보다 먼저 본다 — '날씨 보여줘'(T02) · '번역해서 답장 써줘'(T07).
    v1.4: 부정 · 의문 · 과거 서술은 analyze가 후보에서 지운다. 따옴표 · 'X 말고' 부분은 보지 않는다('삭제 말고 빼줘')."""
    q, _ = views(text)
    if OFF_TOPIC.search(q) and not MAIL_WORDS.search(q):
        return "unsupported"
    if UNSUPPORTED.search(q):
        return "unsupported"
    if NOT_MAIL_TASK.search(q) and not {"T07", "T12", "T15"} & set(hits):  # v1.4 캘린더 일정 등록 · 앱 설정(v1.5 T15가 허용되면 등록은 통과)
        return "unsupported"
    return None


def _fragment(text: str) -> bool:
    """서술어 어미로 끝나지 않는 말 조각('김 팀장 건' · '아까 그거' · '완료' · '중요한 거 위주로')."""
    fw = _final_word(text)
    return bool(fw) and "가" <= fw[-1] <= "힣" and fw[-1] not in _PRED_END


def reject_reason(text: str, an: Analysis | None = None) -> str | None:
    """규칙이 행동을 하나도 못 찾았을 때, 모델 없이 정할 수 있는 거절 사유. 없으면 None (모델로 넘긴다)."""
    q, _ = views(text)
    t = normalize(text)
    plain = _blank(t, [m.span() for m in _QUOTE.finditer(t)])
    if UNSUPPORTED.search(q) or NOT_MAIL_TASK.search(q) or (OFF_TOPIC.search(q) and not MAIL_WORDS.search(q)):
        return "unsupported"
    if PROHIBIT_END.search(plain.rstrip()) or HOWTO.search(plain):  # v1.4 '이 메일 완료하지 마' · '스누즈가 뭐야' — 지시가 아니다
        return "unsupported"
    if an is not None:
        if an.reason:
            return an.reason
        if an.dropped:  # 의문 · 과거 서술 · 메일 아닌 대상으로 지운 후보 — 모델이 고르되 안전장치(non_command)가 막는다
            return None
    if VAGUE.search(plain):
        return "ambiguous"
    if _fragment(plain):  # v1.4 행동 없는 말 조각은 되묻는다
        return "ambiguous"
    return None


def _has_object(q: str) -> bool:
    if OBJ.search(q):
        return True
    for m in _OBJ_TOPIC.finditer(q):
        if m[1] not in NOT_OBJ and not re.match(r"\s*(?:거|것|사람|분|메일|건|법|방법)(?:\s|$)", q[m.end():]):
            return True
    return False


def slots_ok(action: str, text: str, ctx, target: Target, params: dict) -> bool:
    """v1.4 행동에 필요한 대상 · 값이 있는가. 없으면 실행하지 않고 되묻는다('빼줘' · '알림 바꿔줘' · '초안 써줘').
    지시어가 있는데 고른 메일 · 직전 결과가 없으면 되묻는다('그거 빼줘'). 대상 낱말 없는 짧은 지시는 고른 메일,
    '다 · 전부'는 직전 결과를 대상으로 채운다."""
    q, _ = views(text)
    ids, had_ref = mail_refs(q, ctx)
    named = bool(target.sender or target.category or target.keyword or target.date_range)
    if had_ref and not ids and not named and action in MUTATING - {"T04", "T09"}:
        return False
    if action in ("T03", "T05", "T10"):
        if named or target.mail_ids or _has_object(q):
            return True
    elif action == "T11":
        if target.sender or target.mail_ids:
            return True
    elif action == "T09":
        return bool(params.get("time") or params.get("hours"))
    elif action == "T07":
        if target.mail_ids or target.sender or target.keyword or had_ref or "메일" in q:
            return True
    elif action == "T12":
        return bool(target.sender or params.get("topic"))
    elif action == "T14":
        if params.get("template_kind") == "nudge" or target.mail_ids or target.sender:
            return True
    elif action == "T15":
        # v1.5 시각이 있으면 그대로, 고른 메일이면 backend가 그 메일의 일정 시각(시각이 적힌 것만)으로 채운다.
        # 날짜만 말하고 시각이 없으면('내일 회의 잡아줘' · '금요일 오전에') 지어내지 않고 되묻는다 — 고른 메일로 넘기지 않는다
        if params.get("start") or target.mail_ids:
            return True
        if parse_due_plain(q, ctx.now) is not None or _find_time(q) is not None or RELATIVE_WHEN.search(q):
            return False
    else:
        return True
    if ctx.selected_mail_ids:
        target.mail_ids = list(ctx.selected_mail_ids)
        return True
    if ctx.last_result_ids and QUANTIFIER.search(q):
        target.mail_ids = list(ctx.last_result_ids)
        return True
    return False


def non_command(text: str, action: str) -> bool:
    """v1.4 모델 경로 안전장치: 부정 · 의문 · 과거 표지가 있는 문장. 규칙이 못 잡은 상태 변경 행동을 모델이 내도 실행하지 않는다.
    완료(T03)는 과거형이 지시라서 문장 끝 과거형만으로는 막지 않는다('다 처리했어')."""
    t = normalize(text)
    if NEGATION.search(t) or NEG_PRED.search(t) or PROHIBIT_END.search(t.rstrip()) or _neg_done(t):
        return True
    if HOWTO.search(t) or info_question(t) or PAST_NARR.search(t) or HESITATE.search(t):
        return True
    return action != "T03" and _past_final(t)
