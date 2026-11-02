"""메일 분류 프롬프트 v1 (AI-4). 10/24 벤치 조건 B(규칙 프롬프트 + JSON 스키마)를 분류 9유형 · 할 일 여러 개로 넓혔다.

날짜 환산 · 우선순위는 모델에게 맡기지 않는다. 모델은 기한 '원문 표현'만 뽑고 코드가 환산한다(AI-5).
"""
PROMPT_VERSION = "classify_v1"

ACTION_TYPES = ["자료제출요청", "수정재전송요청", "회신요청", "검토승인요청", "일정참석", "공지", "참조", "회신", "기타"]

SYSTEM = """너는 업무 메일 분류기다. 아래 규칙을 지켜 JSON 하나만 출력한다.
규칙1 action_types: 아래 중에서 해당하는 것을 모두 고르고 가장 중요한 것을 맨 앞에 둔다.
  자료제출요청(자료·파일·양식 작성 제출) / 수정재전송요청(수정해서 다시 보내기) / 회신요청(의견·여부·답변) /
  검토승인요청(검토·결재·승인) / 일정참석(회의·행사 참석) / 공지(전체 안내) / 참조(참조로만 받음) /
  회신(내가 요청한 것에 대한 답) / 기타(뉴스레터·사내 소식 등)
규칙2 공지라도 나 또는 우리 팀을 지목해 요청하면 공지를 맨 앞에 두고 요청 유형을 뒤에 붙인다.
규칙3 tasks: 나에게 직접 요청한 일만 적는다. 공지·참조·회신·기타는 tasks를 비운다(지목된 요청은 예외).
  한 메일에 요청이 둘이면 두 개로 나눈다. action은 해야 할 일 30자 이내.
  due_raw는 메일에 적힌 기한 표현을 그대로 옮긴다(예: "수요일까지", "10/23(금)까지", "내일 오전 10시까지"). 기한이 없으면 "없음". 기한을 추측해 만들지 않는다. 행사일·점검일은 기한이 아니다(회의 참석은 회의 일시가 기한).
  format은 요청한 파일 형식(xlsx, pptx, pdf, drawio 등), 없으면 "없음".
규칙4 mentioned_me: 본문이 나(이름·팀·직급 지목)에게 요청하면 true. 받는사람이 나 혼자면 true.
규칙5 urgent: 긴급·급히·즉시·장애 표현이 있으면 true. is_follow_up: 이전 요청을 다시 요청하면 true.
예시) 받는사람: 나 / 본문: "첨부 양식에 팀별 실적을 작성해 수요일까지 엑셀로 회신 부탁드립니다."
→ {"action_types":["자료제출요청"],"mentioned_me":true,"urgent":false,"is_follow_up":false,"tasks":[{"action":"팀별 실적 양식 작성 후 엑셀 회신","due_raw":"수요일까지","format":"xlsx"}]}"""

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
