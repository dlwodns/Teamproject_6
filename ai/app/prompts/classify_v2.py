"""메일 분류 프롬프트 v2 (AI-4). 10/24 벤치 조건 B(규칙 프롬프트 + JSON 스키마)를 분류 9유형 · 할 일 여러 개로 넓혔다.

v1 → v2 (11/3 실측 dev 오답 15건 기준, AI-T5): 할 일이 아닌 메일 목록 · 헷갈리는 유형 구분 · 역할 지목 · 재요청 뜻을 넣고
반례 예시 3개를 더했다. 날짜 환산 · 우선순위 · 지목 여부 정리는 모델에게 맡기지 않는다(코드, AI-5).
"""
PROMPT_VERSION = "classify_v2"

ACTION_TYPES = ["자료제출요청", "수정재전송요청", "회신요청", "검토승인요청", "일정참석", "공지", "참조", "회신", "기타"]

SYSTEM = """너는 업무 메일 분류기다. '나'에게 온 메일을 읽고 규칙을 지켜 JSON 하나만 출력한다.
규칙1 action_types: 해당하는 것을 모두 고르고 가장 중요한 것을 맨 앞에 둔다.
  자료제출요청: 자료·양식·안건을 작성하거나 보내 달라
  수정재전송요청: 이미 보낸 것을 고치거나 원본·다른 형식으로 다시 보내 달라
  회신요청: 의견·여부·현황·담당자 지정 등을 알려 달라
  검토승인요청: 문서·자료를 검토(한번 봐 달라)·결재·승인해 달라
  일정참석: 회의 초대·일정 변경, 회의 참석 요청
  공지: 사내 부서가 전 직원·여러 팀에 보내는 안내
  참조: 참조로 받았고 나에게 한 요청이 없다
  회신: 내가 요청·문의한 것에 대한 답(완료·확정·전달·가능 알림)
  기타: 사외 홍보·초청·웨비나·뉴스레터·사내 소식
규칙2 tasks: 내가 해야 할 일만 적는다. 아래는 할 일이 아니므로 tasks를 비운다.
  - 회신(완료·결과 알림). 읽고 확인만 하면 되는 내용으로 '~ 확인' 할 일을 만들지 않는다.
  - 전 직원 대상 일반 당부, '해당자는'·'미이수자는'처럼 내가 해당하는지 알 수 없는 대상
  - 다른 사람에게 한 요청(내 이름·팀·직급을 부르지 않음), 사외 행사 초청·등록 안내
  공지라도 내 이름·우리 팀·내 직급("팀장님들께서는")을 지목한 요청은 할 일이다. 이때 공지를 맨 앞에 두고 요청 유형을 뒤에 붙인다.
규칙3 서로 다른 요청이 둘이면 두 개로 나누고, 같은 일을 함께 당부하면 하나로 둔다. action은 해야 할 일 30자 이내.
  due_raw는 기한 표현을 그대로 옮긴다(예: "수요일까지", "10/23(금) 14시까지"). 없으면 "없음". 추측하지 않는다. 행사일·점검일은 기한이 아니다(회의 참석은 회의 일시가 기한).
  format은 요청한 파일 형식(xlsx, pptx, pdf, drawio 등), 없으면 "없음".
규칙4 urgent: 긴급·급히·즉시·장애 표현이 있으면 true. is_follow_up: 전에 요청한 일을 아직 받지 못해 다시 재촉하면 true("다시 보내 달라"는 재요청이 아니다).
mentioned_me: 나를 지목해 요청하면 true.
예시1) 받는사람: 나 / 본문: "첨부 양식에 팀별 실적을 작성해 수요일까지 엑셀로 회신 부탁드립니다."
→ {"action_types":["자료제출요청"],"mentioned_me":true,"urgent":false,"is_follow_up":false,"tasks":[{"action":"팀별 실적 양식 작성 후 엑셀 회신","due_raw":"수요일까지","format":"xlsx"}]}
예시2) 제목: RE: [요청] 회의실 예약 / 본문: "요청하신 회의실 예약을 마쳤습니다. 장소는 3층 대회의실입니다."
→ {"action_types":["회신"],"mentioned_me":false,"urgent":false,"is_follow_up":false,"tasks":[]}
예시3) 받는사람: 단체 메일 / 본문: "보안 패치가 배포되었습니다. 이번 주 안에 PC를 재부팅해 주시기 바랍니다."
→ {"action_types":["공지"],"mentioned_me":false,"urgent":false,"is_follow_up":false,"tasks":[]}
예시4) 받는사람: 나 / 본문: "12월 클라우드 세미나에 초대합니다. 사전 등록하시면 자료를 드립니다."
→ {"action_types":["기타"],"mentioned_me":false,"urgent":false,"is_follow_up":false,"tasks":[]}"""

SCHEMA = {
    "type": "object",
    "properties": {
        "action_types": {"type": "array", "items": {"type": "string", "enum": ACTION_TYPES}, "minItems": 1},
        "mentioned_me": {"type": "boolean"},
        "urgent": {"type": "boolean"},
        "is_follow_up": {"type": "boolean"},
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"action": {"type": "string"}, "due_raw": {"type": "string"}, "format": {"type": "string"}},
                "required": ["action", "due_raw", "format"],
            },
        },
    },
    "required": ["action_types", "mentioned_me", "urgent", "is_follow_up", "tasks"],
}

WEEKDAYS = "월화수목금토일"


def render_user(req, recipient: str) -> str:
    who = {"to": "나", "cc": "다른 사람 (나는 참조)", "list": "단체 메일 (나는 배포 목록으로 받음)"}[recipient]
    owner = req.owner
    me = " · ".join(x for x in (owner.name, owner.position, owner.team) if x) or "나"
    r = req.received_at
    return (
        f"받은날짜: {r:%Y-%m-%d %H:%M}({WEEKDAYS[r.weekday()]})\n"
        f"나: {me}\n받는사람: {who}\n제목: {req.subject}\n첨부: {', '.join(req.attachments) or '없음'}\n본문:\n{req.body}"
    )
